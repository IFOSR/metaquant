"""Persistence for paper trading accounts and their ledgers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from quant_platform.paper.contracts import PaperAccount, PaperAccountState
from quant_platform.paper.models import (
    PaperAccountModel,
    PaperEquityModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
    PaperRunStateModel,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _to_account(model: PaperAccountModel) -> PaperAccount:
    return PaperAccount(
        id=model.id,
        owner=model.owner,
        draft_id=model.draft_id,
        artifact_address=model.artifact_address,
        content_hash=model.content_hash,
        market=model.market,
        instrument_ids=tuple(model.instrument_ids),
        frequency=model.frequency,
        initial_cash=model.initial_cash,
        state=PaperAccountState(model.state),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyPaperRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    # -- accounts -----------------------------------------------------------

    def create_account(
        self,
        *,
        owner: str,
        draft_id: str,
        artifact_address: str,
        content_hash: str,
        market: str,
        instrument_ids: tuple[str, ...],
        frequency: str,
        initial_cash: Decimal,
    ) -> PaperAccount:
        timestamp = _now()
        model = PaperAccountModel(
            id=f"pa_{uuid4().hex}",
            owner=owner,
            draft_id=draft_id,
            artifact_address=artifact_address,
            content_hash=content_hash,
            market=market,
            instrument_ids=list(instrument_ids),
            frequency=frequency,
            initial_cash=initial_cash,
            state=PaperAccountState.ACTIVE.value,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._sessions.begin() as session:
            session.add(model)
        return _to_account(model)

    def get_account(self, account_id: str) -> PaperAccount | None:
        with self._sessions.begin() as session:
            model = session.get(PaperAccountModel, account_id)
            return None if model is None else _to_account(model)

    def list_accounts(self, *, owner: str | None = None) -> list[PaperAccount]:
        with self._sessions.begin() as session:
            query = select(PaperAccountModel).order_by(PaperAccountModel.created_at)
            if owner is not None:
                query = query.where(PaperAccountModel.owner == owner)
            return [_to_account(m) for m in session.scalars(query).all()]

    def update_state(self, account_id: str, state: PaperAccountState) -> PaperAccount:
        with self._sessions.begin() as session:
            model = session.get(PaperAccountModel, account_id)
            if model is None:
                raise KeyError(f"account not found: {account_id}")
            model.state = state.value
            model.updated_at = _now()
            return _to_account(model)

    # -- orders / fills -----------------------------------------------------

    def record_order(
        self,
        *,
        account_id: str,
        idempotency_key: str,
        instrument_id: str,
        side: str,
        quantity: int,
        order_clock: str,
        status: str,
        reject_reason: str | None = None,
        filled_qty: int = 0,
        avg_px: Decimal | None = None,
    ) -> str:
        """Insert an order; returns its id. Idempotent per (account, key)."""
        timestamp = _now()
        with self._sessions.begin() as session:
            existing = session.scalars(
                select(PaperOrderModel).where(
                    PaperOrderModel.account_id == account_id,
                    PaperOrderModel.idempotency_key == idempotency_key,
                )
            ).first()
            if existing is not None:
                return existing.id
            model = PaperOrderModel(
                id=f"po_{uuid4().hex}",
                account_id=account_id,
                idempotency_key=idempotency_key,
                instrument_id=instrument_id,
                side=side,
                quantity=quantity,
                order_clock=order_clock,
                status=status,
                reject_reason=reject_reason,
                filled_qty=filled_qty,
                avg_px=avg_px,
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(model)
            return model.id

    def record_fill(
        self,
        *,
        order_id: str,
        account_id: str,
        trade_ts: datetime,
        price: Decimal,
        quantity: int,
        fee: Decimal,
        fill_id: str | None = None,
    ) -> str | None:
        """Insert a fill; returns its id, or None when already recorded.

        Pass a deterministic ``fill_id`` (e.g. derived from broker fill keys)
        to make reconciliation against the runtime idempotent.
        """
        resolved_id = fill_id or f"pf_{uuid4().hex}"
        with self._sessions.begin() as session:
            existing = session.get(PaperFillModel, resolved_id)
            if existing is not None:
                return None
            order = session.get(PaperOrderModel, order_id)
            if order is None:
                raise KeyError(f"order not found: {order_id}")
            order.filled_qty += quantity
            if order.filled_qty >= order.quantity:
                order.status = "FILLED"
            else:
                order.status = "PARTIAL"
            total = order.filled_qty
            prior = (order.avg_px or Decimal("0")) * (total - quantity)
            order.avg_px = (prior + price * quantity) / total
            order.updated_at = _now()
            session.add(
                PaperFillModel(
                    id=resolved_id,
                    order_id=order_id,
                    account_id=account_id,
                    trade_ts=trade_ts,
                    price=price,
                    quantity=quantity,
                    fee=fee,
                    notional=price * quantity,
                )
            )
        return resolved_id

    def list_orders(self, account_id: str) -> list[dict[str, object]]:
        with self._sessions.begin() as session:
            rows = session.scalars(
                select(PaperOrderModel)
                .where(PaperOrderModel.account_id == account_id)
                .order_by(PaperOrderModel.created_at)
            ).all()
            return [
                {
                    "id": row.id,
                    "instrument_id": row.instrument_id,
                    "side": row.side,
                    "quantity": row.quantity,
                    "order_clock": row.order_clock,
                    "status": row.status,
                    "reject_reason": row.reject_reason,
                    "filled_qty": row.filled_qty,
                    "avg_px": float(row.avg_px) if row.avg_px is not None else None,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def list_fills(self, account_id: str) -> list[dict[str, object]]:
        with self._sessions.begin() as session:
            rows = session.scalars(
                select(PaperFillModel)
                .where(PaperFillModel.account_id == account_id)
                .order_by(PaperFillModel.trade_ts)
            ).all()
            return [
                {
                    "id": row.id,
                    "order_id": row.order_id,
                    "trade_ts": row.trade_ts.isoformat(),
                    "price": float(row.price),
                    "quantity": row.quantity,
                    "fee": float(row.fee),
                    "notional": float(row.notional),
                }
                for row in rows
            ]

    # -- positions / equity -------------------------------------------------

    def upsert_position(
        self,
        *,
        account_id: str,
        instrument_id: str,
        quantity: int,
        avg_px: Decimal | None,
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(PaperPositionModel, (account_id, instrument_id))
            timestamp = _now()
            if row is None:
                session.add(
                    PaperPositionModel(
                        account_id=account_id,
                        instrument_id=instrument_id,
                        quantity=quantity,
                        avg_px=avg_px,
                        updated_at=timestamp,
                    )
                )
            else:
                row.quantity = quantity
                row.avg_px = avg_px
                row.updated_at = timestamp

    def list_positions(self, account_id: str) -> list[dict[str, object]]:
        with self._sessions.begin() as session:
            rows = session.scalars(
                select(PaperPositionModel).where(
                    PaperPositionModel.account_id == account_id
                )
            ).all()
            return [
                {
                    "instrument_id": row.instrument_id,
                    "quantity": row.quantity,
                    "avg_px": float(row.avg_px) if row.avg_px is not None else None,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in rows
            ]

    def record_equity(
        self,
        *,
        account_id: str,
        trade_date: str,
        equity: Decimal,
        cash: Decimal,
        margin_used: Decimal = Decimal("0"),
        drawdown: Decimal = Decimal("0"),
    ) -> None:
        with self._sessions.begin() as session:
            row = session.get(PaperEquityModel, (account_id, trade_date))
            timestamp = _now()
            if row is None:
                session.add(
                    PaperEquityModel(
                        account_id=account_id,
                        trade_date=trade_date,
                        equity=equity,
                        cash=cash,
                        margin_used=margin_used,
                        drawdown=drawdown,
                        updated_at=timestamp,
                    )
                )
            else:
                row.equity = equity
                row.cash = cash
                row.margin_used = margin_used
                row.drawdown = drawdown
                row.updated_at = timestamp

    def list_equity(self, account_id: str) -> list[dict[str, object]]:
        with self._sessions.begin() as session:
            rows = session.scalars(
                select(PaperEquityModel)
                .where(PaperEquityModel.account_id == account_id)
                .order_by(PaperEquityModel.trade_date)
            ).all()
            return [
                {
                    "trade_date": row.trade_date,
                    "equity": float(row.equity),
                    "cash": float(row.cash),
                    "margin_used": float(row.margin_used),
                    "drawdown": float(row.drawdown),
                }
                for row in rows
            ]

    def record_run_state(
        self,
        *,
        account_id: str,
        status: str,
        cycles_total: int,
        bars_total: int,
        last_cycle_at: datetime | None,
        last_bar_at: datetime | None,
        last_error: str | None,
    ) -> None:
        """节点每周期写入运行进度（幂等 upsert，按 account_id）。"""
        now = _now()
        with self._sessions.begin() as session:
            model = session.get(PaperRunStateModel, account_id)
            if model is None:
                model = PaperRunStateModel(account_id=account_id, updated_at=now)
                session.add(model)
            model.status = status
            model.cycles_total = cycles_total
            model.bars_total = bars_total
            model.last_cycle_at = last_cycle_at
            model.last_bar_at = last_bar_at
            model.last_error = last_error
            model.updated_at = now

    def get_run_state(self, account_id: str) -> dict[str, object] | None:
        with self._sessions.begin() as session:
            model = session.get(PaperRunStateModel, account_id)
            if model is None:
                return None
            return {
                "account_id": model.account_id,
                "status": model.status,
                "cycles_total": model.cycles_total,
                "bars_total": model.bars_total,
                "last_cycle_at": (
                    model.last_cycle_at.isoformat() if model.last_cycle_at else None
                ),
                "last_bar_at": (
                    model.last_bar_at.isoformat() if model.last_bar_at else None
                ),
                "last_error": model.last_error,
                "updated_at": model.updated_at.isoformat(),
            }
