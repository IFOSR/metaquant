"""Execution contracts (G15-001).

The execution boundary defines the order instruction that paper/live runtimes
emit and the adapter protocol that brokers implement. Adapters only submit
orders and read positions; they never write to the research kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quant_platform.markets.cn_a import OrderSide


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


@dataclass(frozen=True, slots=True)
class OrderInstruction:
    order_id: str
    instrument_id: str
    side: OrderSide
    quantity: int
    idempotency_key: str

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.instrument_id, "instrument_id")
        if not isinstance(self.side, OrderSide):
            object.__setattr__(self, "side", OrderSide(self.side))
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        _require_identifier(self.idempotency_key, "idempotency_key")

    def payload(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "instrument_id": self.instrument_id,
            "side": self.side.value,
            "quantity": self.quantity,
            "idempotency_key": self.idempotency_key,
        }


class ExecutionAdapter(Protocol):
    """Broker adapter boundary.

    ``submit`` sends an order and returns a broker order id. ``positions``
    returns the current (instrument_id, quantity) map. Adapters never write to
    the research kernel, the database, a GateDecision, the Alpha Pool, or a
    StrategyPackage.
    """

    def submit(self, order: OrderInstruction) -> str: ...

    def positions(self) -> dict[str, int]: ...

    def cancel(self, order_id: str) -> bool: ...
