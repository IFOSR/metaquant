"""Execution state service: kill switch reads, tripping, and reset.

Extracted from the experiment repository so the execution safety state lives
in its own module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from quant_platform.execution.safety import KillSwitch, KillSwitchState
from quant_platform.research.models import ExecutionStateModel


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_execution_state(session: Session) -> ExecutionStateModel:
    model = session.get(ExecutionStateModel, "cn-a")
    if model is None:
        model = ExecutionStateModel(
            state_id="cn-a",
            kill_switch_state="ARMED",
            tripped_by=None,
            tripped_at=None,
            reason=None,
            shadow_positions={},
            paper_positions={},
            updated_at=_now(),
        )
        session.add(model)
    return model


def _kill_switch_from_model(model: ExecutionStateModel) -> KillSwitch:
    tripped_at = model.tripped_at
    if tripped_at is not None and tripped_at.tzinfo is None:
        tripped_at = tripped_at.replace(tzinfo=UTC)
    return KillSwitch(
        switch_id=model.state_id,
        state=KillSwitchState(model.kill_switch_state),
        tripped_by=model.tripped_by,
        tripped_at=tripped_at,
        reason=model.reason,
    )


def _apply_kill_switch(model: ExecutionStateModel, switch: KillSwitch) -> None:
    model.kill_switch_state = switch.state.value
    model.tripped_by = switch.tripped_by
    model.tripped_at = switch.tripped_at
    model.reason = switch.reason
    model.updated_at = _now()


def _execution_state_payload(model: ExecutionStateModel) -> dict[str, Any]:
    return {
        "state_id": model.state_id,
        "kill_switch_state": model.kill_switch_state,
        "tripped_by": model.tripped_by,
        "tripped_at": model.tripped_at.isoformat() if model.tripped_at else None,
        "reason": model.reason,
        "shadow_positions": model.shadow_positions,
        "paper_positions": model.paper_positions,
    }


class ExecutionStateService:
    """Handles execution state and kill switch lifecycle."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get_state(self) -> dict[str, Any]:
        with self._sessions() as session:
            model = session.get(ExecutionStateModel, "cn-a")
            if model is None:
                return {
                    "state_id": "cn-a",
                    "kill_switch_state": "ARMED",
                    "tripped_by": None,
                    "tripped_at": None,
                    "reason": None,
                    "shadow_positions": {},
                    "paper_positions": {},
                }
            return _execution_state_payload(model)

    def trip(self, *, actor_id: str, reason: str) -> dict[str, Any]:
        with self._sessions.begin() as session:
            model = _ensure_execution_state(session)
            switch = _kill_switch_from_model(model)
            updated = switch.trip(actor_id, reason, _now())
            _apply_kill_switch(model, updated)
            return _execution_state_payload(model)

    def reset(self, *, actor_id: str) -> dict[str, Any]:
        with self._sessions.begin() as session:
            model = _ensure_execution_state(session)
            switch = _kill_switch_from_model(model)
            updated = switch.reset(actor_id, _now())
            _apply_kill_switch(model, updated)
            return _execution_state_payload(model)
