"""Execution safety controls (G15-002).

Notional caps, kill switch, and position reconciliation are the last line of
defense before live orders. They are deterministic and fail closed: any breach
blocks the order, and the kill switch overrides everything.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from quant_platform.experiments import canonical_hash
from quant_platform.markets.cn_a import OrderSide


@dataclass(frozen=True, slots=True)
class SafetyLimits:
    notional_cap: Decimal
    kill_switch: bool = False
    max_order_quantity: int | None = None

    def __post_init__(self) -> None:
        if self.notional_cap <= Decimal("0"):
            raise ValueError("notional_cap must be positive")
        if self.max_order_quantity is not None and self.max_order_quantity < 1:
            raise ValueError("max_order_quantity must be positive when provided")

    def payload(self) -> dict[str, object]:
        return {
            "notional_cap": str(self.notional_cap),
            "kill_switch": self.kill_switch,
            "max_order_quantity": self.max_order_quantity,
        }


@dataclass(frozen=True, slots=True)
class SafetyCheck:
    allowed: bool
    reason: str

    def payload(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason}


def check_order_safety(
    *,
    side: OrderSide,
    quantity: int,
    price: Decimal,
    limits: SafetyLimits,
) -> SafetyCheck:
    """Fail-closed safety check for a single order."""
    if limits.kill_switch:
        return SafetyCheck(allowed=False, reason="kill_switch")
    if quantity <= 0:
        return SafetyCheck(allowed=False, reason="non_positive_quantity")
    if price <= Decimal("0"):
        return SafetyCheck(allowed=False, reason="non_positive_price")
    if limits.max_order_quantity is not None and quantity > limits.max_order_quantity:
        return SafetyCheck(allowed=False, reason="order_quantity_exceeded")
    notional = price * quantity
    if notional > limits.notional_cap:
        return SafetyCheck(allowed=False, reason="notional_cap_exceeded")
    return SafetyCheck(allowed=True, reason="allowed")


def reconcile(expected: dict[str, int], actual: dict[str, int]) -> dict[str, int]:
    """Return per-instrument expected-minus-actual quantity differences.

    An empty result means the broker positions match the expected positions.
    """
    instruments = set(expected) | set(actual)
    return {
        instrument: expected.get(instrument, 0) - actual.get(instrument, 0)
        for instrument in sorted(instruments)
        if expected.get(instrument, 0) != actual.get(instrument, 0)
    }


class KillSwitchState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"


@dataclass(frozen=True, slots=True)
class KillSwitch:
    """Persistent, auditable kill switch (G16-008, FR-604).

    Unlike the per-request boolean, this state is content-addressed and records
    who tripped or reset it, when, and why. A tripped switch blocks every
    order until explicitly reset.
    """

    switch_id: str
    state: KillSwitchState
    tripped_by: str | None
    tripped_at: datetime | None
    reason: str | None

    def __post_init__(self) -> None:
        if not self.switch_id or self.switch_id.strip() != self.switch_id:
            raise ValueError("switch_id must be a non-empty normalized identifier")
        if not isinstance(self.state, KillSwitchState):
            object.__setattr__(self, "state", KillSwitchState(self.state))
        if self.state is KillSwitchState.TRIPPED:
            if self.tripped_by is None or self.tripped_at is None or not self.reason:
                raise ValueError("a tripped switch requires actor, time, and reason")
            if self.tripped_at.tzinfo is None:
                raise ValueError("tripped_at must be timezone-aware")

    def blocks(self) -> bool:
        return self.state is KillSwitchState.TRIPPED

    def trip(self, actor: str, reason: str, at: datetime) -> KillSwitch:
        if not actor or actor.strip() != actor:
            raise ValueError("actor must be a non-empty normalized identifier")
        if not reason:
            raise ValueError("reason must not be empty")
        if at.tzinfo is None:
            raise ValueError("at must be timezone-aware")
        return replace(
            self,
            state=KillSwitchState.TRIPPED,
            tripped_by=actor,
            tripped_at=at,
            reason=reason,
        )

    def reset(self, actor: str, at: datetime) -> KillSwitch:
        if not actor or actor.strip() != actor:
            raise ValueError("actor must be a non-empty normalized identifier")
        if at.tzinfo is None:
            raise ValueError("at must be timezone-aware")
        return replace(
            self,
            state=KillSwitchState.ARMED,
            tripped_by=None,
            tripped_at=None,
            reason=None,
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "kill-switch/v1",
            "switch_id": self.switch_id,
            "state": self.state.value,
            "tripped_by": self.tripped_by,
            "tripped_at": self.tripped_at.isoformat() if self.tripped_at else None,
            "reason": self.reason,
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())
