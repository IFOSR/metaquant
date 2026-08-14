"""Execution safety controls (G15-002).

Notional caps, kill switch, and position reconciliation are the last line of
defense before live orders. They are deterministic and fail closed: any breach
blocks the order, and the kill switch overrides everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
