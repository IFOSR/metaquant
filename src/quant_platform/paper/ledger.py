"""Paper ledger: reconcile runtime execution reports into the PG ledger.

The node runner periodically reads the trader's order-fills report and the
position state, mapping them into the paper tables with deterministic ids so
reconciliation can run repeatedly without double counting. Equity is marked
to market with the latest pushed bar closes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from quant_platform.paper.repository import SqlAlchemyPaperRepository


def fill_key(client_order_id: str, ts_last: str, filled_qty: str, avg_px: str) -> str:
    digest = hashlib.sha256(
        f"{client_order_id}|{ts_last}|{filled_qty}|{avg_px}".encode()
    ).hexdigest()
    return f"pfk_{digest[:32]}"


def _money_amount(value: object) -> float:
    """NautilusTrader Money 形如 ``"12.34 CNY"``。"""
    text = str(value)
    amount, _, _ = text.partition(" ")
    return float(amount.replace(",", "").replace("_", ""))


def reconcile_fills(
    *,
    repository: SqlAlchemyPaperRepository,
    account_id: str,
    fills_report: list[dict[str, Any]],
) -> int:
    """Upsert fills from a ``generate_order_fills_report()`` snapshot.

    Returns the number of newly persisted fill events. Orders are keyed by
    the runtime's client_order_id; fills by a deterministic content key.
    """
    inserted = 0
    for row in fills_report:
        client_order_id = str(row["client_order_id"])
        instrument_id = str(row["instrument_id"])
        side = "BUY" if str(row["side"]).upper().startswith("BUY") else "SELL"
        quantity = int(float(str(row["filled_qty"])))
        price = Decimal(str(row["avg_px"]))
        commissions = row.get("commissions") or ()
        fee = Decimal(str(sum(_money_amount(item) for item in commissions)))
        ts_raw = row.get("ts_last")
        if isinstance(ts_raw, datetime):
            trade_ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=UTC)
        else:
            trade_ts = datetime.now(UTC)
        order_id = repository.record_order(
            account_id=account_id,
            idempotency_key=client_order_id,
            instrument_id=instrument_id,
            side=side,
            # 订单名义数量以成交为准（NETTING 撮合回报按事件行给出）。
            quantity=quantity,
            order_clock="RUNTIME",
            status="FILLED",
        )
        result = repository.record_fill(
            order_id=order_id,
            account_id=account_id,
            trade_ts=trade_ts,
            price=price,
            quantity=quantity,
            fee=fee,
            fill_id=fill_key(
                client_order_id,
                str(ts_raw),
                str(row["filled_qty"]),
                str(row["avg_px"]),
            ),
        )
        if result is not None:
            inserted += 1
    return inserted


@dataclass(frozen=True, slots=True)
class EquitySnapshot:
    equity: float
    cash: float
    margin_used: float
    drawdown: float

    def payload(self) -> dict[str, float]:
        return {
            "equity": self.equity,
            "cash": self.cash,
            "margin_used": self.margin_used,
            "drawdown": self.drawdown,
        }


def mark_to_market(
    *,
    initial_cash: float,
    realized_pnl: float,
    positions: dict[str, int],
    marks: dict[str, float],
    entries: dict[str, float] | None = None,
    multipliers: dict[str, int] | None = None,
    margin_account: bool = False,
) -> EquitySnapshot:
    """Equity = initial + realized + Σ qty × (最新价 − 开仓均价) × 乘数。

    现金账户：cash = equity − 持仓市值（占用在持仓里的资金）；
    保证金账户：cash = equity − 保证金占用（近似可用资金）。
    """
    multiplier_map = multipliers or {}
    entry_map = entries or {}
    unrealized = 0.0
    market_value = 0.0
    margin_used = 0.0
    for instrument_id, quantity in positions.items():
        close = marks.get(instrument_id)
        if close is None or quantity == 0:
            continue
        multiplier = multiplier_map.get(instrument_id, 1)
        value = quantity * close * multiplier
        market_value += abs(value)
        entry = entry_map.get(instrument_id, close)
        unrealized += quantity * (close - entry) * multiplier
        margin_used += abs(quantity) * close * multiplier
    equity = initial_cash + realized_pnl + unrealized
    drawdown = 0.0
    peak = max(initial_cash, equity)
    if peak > 0:
        drawdown = (peak - equity) / peak
    reserved = margin_used if margin_account else market_value
    return EquitySnapshot(
        equity=round(equity, 4),
        cash=round(equity - reserved, 4),
        margin_used=round(margin_used if margin_account else 0.0, 4),
        drawdown=round(drawdown, 8),
    )
