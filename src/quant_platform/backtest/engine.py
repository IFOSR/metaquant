"""Deterministic backtest engine (G9-003).

Reconciles target weights into orders, applies per-market execution semantics
(T+1 sellability, price-limit and halt blocking, transaction costs), and
produces a fill-level ledger with a NAV history. Signals observed at T close
are executed at the T+1 open, so a signal can never fill at the price it
observed. The engine is a pure function over sealed inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_DOWN, Decimal

from quant_platform.backtest.ledger import Fill, Ledger, Order
from quant_platform.experiments import canonical_hash
from quant_platform.markets.clocks import SHANGHAI
from quant_platform.markets.cn_a import (
    FillCertainty,
    OrderSide,
    TradabilityAssessment,
)
from quant_platform.markets.cost import EquityCostModel

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class BlockedOrder:
    order_id: str
    instrument_id: str
    side: OrderSide
    reason: str

    def payload(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "instrument_id": self.instrument_id,
            "side": self.side.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class BacktestResult:
    ledger: Ledger
    orders: tuple[Order, ...]
    blocked: tuple[BlockedOrder, ...]

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "backtest-result/v1",
            "ledger": self.ledger.payload(),
            "orders": [
                {
                    "order_id": item.order_id,
                    "instrument_id": item.instrument_id,
                    "side": item.side.value,
                    "quantity": item.quantity,
                    "trade_date": item.trade_date.isoformat(),
                }
                for item in self.orders
            ],
            "blocked": [item.payload() for item in self.blocked],
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


def _target_quantities(
    weights: dict[str, Decimal],
    nav: Decimal,
    prices: dict[str, Decimal],
    lot_size: int,
) -> dict[str, int]:
    """Convert target weights into whole-lot quantities."""
    quantities: dict[str, int] = {}
    for instrument_id, weight in weights.items():
        price = prices.get(instrument_id)
        if price is None or price <= _ZERO:
            continue
        notional = nav * weight
        raw = notional / price
        lots = int((raw / lot_size).to_integral_value(rounding=ROUND_DOWN))
        if lots > 0:
            quantities[instrument_id] = lots * lot_size
    return quantities


def _transaction_cost(
    model: EquityCostModel, side: OrderSide, notional: Decimal
) -> Decimal:
    return Decimal(str(model.single_side_cost(side, float(notional))))


def _fill_time(next_date: date) -> datetime:
    return datetime.combine(next_date, time(9, 35), tzinfo=SHANGHAI)


def run_a_share_backtest(
    *,
    trading_dates: tuple[date, ...],
    close_prices: dict[date, dict[str, Decimal]],
    open_prices: dict[date, dict[str, Decimal]],
    target_weights: dict[date, dict[str, Decimal]],
    tradability: dict[date, dict[str, TradabilityAssessment]],
    cost_model: EquityCostModel,
    initial_cash: Decimal,
    lot_size: int = 100,
) -> BacktestResult:
    """Run the deterministic A-share daily backtest.

    Each session: (1) fills the previous session's orders at the open, (2)
    values positions at the close, and (3) generates the next session's orders
    from target weights. Buys on a session are not sellable that same session
    (T+1); price-limit-locked and halted names block the respective side; and
    transaction costs are applied via the equity cost model.
    """
    if not trading_dates:
        raise ValueError("trading_dates must not be empty")
    if len(set(trading_dates)) != len(trading_dates):
        raise ValueError("trading_dates must be unique")
    if any(
        second <= first
        for first, second in zip(trading_dates, trading_dates[1:], strict=False)
    ):
        raise ValueError("trading_dates must be strictly increasing")
    if initial_cash <= _ZERO:
        raise ValueError("initial_cash must be positive")
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")

    ledger = Ledger(cash=initial_cash, positions=(), fills=())
    orders: list[Order] = []
    blocked: list[BlockedOrder] = []
    pending: list[Order] = []

    for index, trade_date in enumerate(trading_dates):
        close = close_prices.get(trade_date, {})
        open_today = open_prices.get(trade_date, {})

        # 1. Open: fill the previous session's pending orders.
        today_buys: dict[str, int] = {}
        for order in pending:
            assessment = tradability.get(trade_date, {}).get(order.instrument_id)
            reason = _fill_block_reason(
                order, assessment, ledger, open_today, cost_model
            )
            if reason is not None:
                blocked.append(
                    BlockedOrder(
                        order_id=order.order_id,
                        instrument_id=order.instrument_id,
                        side=order.side,
                        reason=reason,
                    )
                )
                continue
            price = open_today[order.instrument_id]
            cost = _transaction_cost(cost_model, order.side, price * order.quantity)
            fill = Fill(
                fill_id=f"fill_{order.order_id}",
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=order.quantity,
                price=price,
                cost=cost,
                fill_time=_fill_time(trade_date),
                trade_date=trade_date,
            )
            try:
                ledger = ledger.apply_fill(fill)
            except ValueError as exc:
                blocked.append(
                    BlockedOrder(
                        order_id=order.order_id,
                        instrument_id=order.instrument_id,
                        side=order.side,
                        reason=str(exc),
                    )
                )
                continue
            if order.side is OrderSide.BUY:
                today_buys[order.instrument_id] = (
                    today_buys.get(order.instrument_id, 0) + order.quantity
                )
        pending = []

        # 2. Close: value positions held into the close.
        if ledger.positions:
            ledger = ledger.mark_to_market(close, trade_date)

        # 3. Signal: generate the next session's orders.
        if index + 1 >= len(trading_dates):
            continue
        current = {item.instrument_id: item.quantity for item in ledger.positions}
        nav = ledger.nav(close)
        targets = _target_quantities(
            target_weights.get(trade_date, {}), nav, close, lot_size
        )

        for instrument_id in sorted(set(current) | set(targets)):
            target_qty = targets.get(instrument_id, 0)
            current_qty = current.get(instrument_id, 0)
            delta = target_qty - current_qty
            if delta == 0:
                continue
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            quantity = abs(delta)

            if side is OrderSide.SELL:
                # T+1: shares bought at this session's open are not sellable.
                sellable = current_qty - today_buys.get(instrument_id, 0)
                if sellable < quantity:
                    blocked.append(
                        BlockedOrder(
                            order_id=f"order_{trade_date.isoformat()}_{instrument_id}",
                            instrument_id=instrument_id,
                            side=side,
                            reason="t_plus_1",
                        )
                    )
                    continue

            order = Order(
                order_id=f"order_{trade_date.isoformat()}_{instrument_id}",
                instrument_id=instrument_id,
                side=side,
                quantity=quantity,
                trade_date=trade_date,
            )
            orders.append(order)
            pending.append(order)

    return BacktestResult(ledger=ledger, orders=tuple(orders), blocked=tuple(blocked))


def _fill_block_reason(
    order: Order,
    assessment: TradabilityAssessment | None,
    ledger: Ledger,
    open_prices: dict[str, Decimal],
    cost_model: EquityCostModel,
) -> str | None:
    if assessment is not None and assessment.certainty is FillCertainty.BLOCKED:
        return f"tradability:{assessment.reason}"
    price = open_prices.get(order.instrument_id)
    if price is None or price <= _ZERO:
        return "no_open_price"
    if order.side is OrderSide.BUY:
        est_cost = _transaction_cost(cost_model, order.side, price * order.quantity)
        if ledger.cash < price * order.quantity + est_cost:
            return "insufficient_cash"
    return None
