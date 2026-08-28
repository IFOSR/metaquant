"""Paper runtime monitoring: heartbeat, data staleness, kill switch binding.

The runner consults the monitor every cycle:
1. If the global kill switch is TRIPPED, no bars are pushed and no orders flow.
2. Heartbeats record when the runner last completed a cycle; health payloads
   surface staleness (no fresh bar within the expected window) so operators —
   and the future auto-pause policy — can react.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.research.models import ExecutionStateModel


def kill_switch_tripped(sessions: sessionmaker[Session]) -> bool:
    """Read the global execution-state kill switch without heavy imports."""
    with sessions() as session:
        model = session.scalars(
            select(ExecutionStateModel).where(ExecutionStateModel.state_id == "cn-a")
        ).first()
        if model is None:
            return False
        return str(model.kill_switch_state).upper() == "TRIPPED"


class PaperMonitor:
    """Per-account runtime health tracker (in-process)."""

    def __init__(
        self,
        *,
        account_id: str,
        expected_interval_seconds: int,
        stale_multiplier: int = 3,
    ) -> None:
        self._account_id = account_id
        self._expected = max(1, expected_interval_seconds)
        self._stale_after = self._expected * stale_multiplier
        self._last_cycle_at: datetime | None = None
        self._last_bar_at: datetime | None = None
        self._last_error: str | None = None
        self._cycles_total = 0
        self._bars_total = 0

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def cycles_total(self) -> int:
        return self._cycles_total

    @property
    def bars_total(self) -> int:
        return self._bars_total

    @property
    def last_cycle_at(self) -> datetime | None:
        return self._last_cycle_at

    @property
    def last_bar_at(self) -> datetime | None:
        return self._last_bar_at

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def record_cycle(self, *, at: datetime | None = None) -> None:
        self._cycles_total += 1
        self._last_cycle_at = at or datetime.now(UTC)

    def record_bars(self, *, count: int, at: datetime | None = None) -> None:
        if count > 0:
            self._bars_total += count
            self._last_bar_at = at or datetime.now(UTC)

    def record_error(self, message: str) -> None:
        self._last_error = message

    def is_stale(self, *, now: datetime | None = None) -> bool:
        if self._last_bar_at is None:
            # 从未收到过行情：只要跑过至少一轮且超时即视为 stale。
            if self._last_cycle_at is None:
                return False
            reference = now or datetime.now(UTC)
            return reference - self._last_cycle_at > timedelta(
                seconds=self._stale_after
            )
        reference = now or datetime.now(UTC)
        return reference - self._last_bar_at > timedelta(seconds=self._stale_after)

    def health_payload(self, *, now: datetime | None = None) -> dict[str, Any]:
        return {
            "account_id": self._account_id,
            "expected_interval_seconds": self._expected,
            "stale_after_seconds": self._stale_after,
            "last_cycle_at": (
                self._last_cycle_at.isoformat() if self._last_cycle_at else None
            ),
            "last_bar_at": self._last_bar_at.isoformat() if self._last_bar_at else None,
            "stale": self.is_stale(now=now),
            "last_error": self._last_error,
            "cycles_total": self._cycles_total,
            "bars_total": self._bars_total,
        }
