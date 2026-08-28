"""Paper account contracts and state machine.

An account binds one frozen strategy artifact and runs until closed. The
state machine is deliberately small:

    ACTIVE -> PAUSED -> ACTIVE   (resume)
    ACTIVE | PAUSED -> CLOSED    (terminal)

Every transition goes through the service layer; the repository only persists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class PaperAccountState(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class PaperAccountError(ValueError):
    """Raised on invalid account lifecycle operations."""


_ALLOWED_TRANSITIONS: dict[PaperAccountState, frozenset[PaperAccountState]] = {
    PaperAccountState.ACTIVE: frozenset(
        {PaperAccountState.PAUSED, PaperAccountState.CLOSED}
    ),
    PaperAccountState.PAUSED: frozenset(
        {PaperAccountState.ACTIVE, PaperAccountState.CLOSED}
    ),
    PaperAccountState.CLOSED: frozenset(),
}

MARKETS = ("CN_A", "CN_COMMODITY_FUTURES")
FREQUENCIES = ("1d", "5m", "15m", "30m", "60m")


def next_state(current: PaperAccountState, action: str) -> PaperAccountState:
    """Resolve the state after ``action`` ("pause"/"resume"/"close")."""
    mapping = {
        "pause": PaperAccountState.PAUSED,
        "resume": PaperAccountState.ACTIVE,
        "close": PaperAccountState.CLOSED,
    }
    if action not in mapping:
        raise PaperAccountError(f"unknown lifecycle action: {action}")
    target = mapping[action]
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise PaperAccountError(f"cannot {action} account in state {current.value}")
    return target


@dataclass(frozen=True, slots=True)
class PaperAccount:
    """One persistent simulated trading account."""

    id: str
    owner: str
    draft_id: str
    artifact_address: str  # content address of the frozen strategy artifact
    content_hash: str  # draft freeze hash; must match the artifact payload
    market: str
    instrument_ids: tuple[str, ...]
    frequency: str
    initial_cash: Decimal
    state: PaperAccountState
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.id or not self.draft_id:
            raise ValueError("account requires id and draft_id")
        if self.market not in MARKETS:
            raise ValueError(f"unsupported market: {self.market}")
        if self.frequency not in FREQUENCIES:
            raise ValueError(f"unsupported frequency: {self.frequency}")
        if not self.instrument_ids:
            raise ValueError("account requires at least one instrument")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not isinstance(self.state, PaperAccountState):
            object.__setattr__(self, "state", PaperAccountState(self.state))

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "owner": self.owner,
            "draft_id": self.draft_id,
            "artifact_address": self.artifact_address,
            "content_hash": self.content_hash,
            "market": self.market,
            "instrument_ids": list(self.instrument_ids),
            "frequency": self.frequency,
            "initial_cash": float(self.initial_cash),
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
