"""Shadow and paper runtime contracts (G15-003).

Shadow and paper runtimes turn target positions into order suggestions without
sending real orders. A suggestion is a deterministic delta between the target
and current positions; nothing is transmitted to a broker at this layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform.markets.cn_a import OrderSide


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


@dataclass(frozen=True, slots=True)
class OrderSuggestion:
    instrument_id: str
    side: OrderSide
    quantity: int
    reason: str

    def __post_init__(self) -> None:
        _require_identifier(self.instrument_id, "instrument_id")
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide(self.side))
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not self.reason:
            raise ValueError("reason must not be empty")

    def payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "side": self.side.value,
            "quantity": self.quantity,
            "reason": self.reason,
        }


def shadow_rebalance(
    target: dict[str, int], current: dict[str, int]
) -> tuple[OrderSuggestion, ...]:
    """Produce the order suggestions that reconcile current to target.

    Returns an empty tuple when the portfolios already match. This is the
    shadow/paper output: suggestions only, never real orders.
    """
    if any(quantity < 0 for quantity in target.values()):
        raise ValueError("target quantities must be non-negative")
    if any(quantity < 0 for quantity in current.values()):
        raise ValueError("current quantities must be non-negative")

    suggestions: list[OrderSuggestion] = []
    for instrument_id in sorted(set(target) | set(current)):
        delta = target.get(instrument_id, 0) - current.get(instrument_id, 0)
        if delta > 0:
            suggestions.append(
                OrderSuggestion(instrument_id, OrderSide.BUY, delta, "rebalance")
            )
        elif delta < 0:
            suggestions.append(
                OrderSuggestion(instrument_id, OrderSide.SELL, -delta, "rebalance")
            )
    return tuple(suggestions)
