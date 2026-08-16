"""Execution layer (G15): adapter boundary and safety controls."""

from quant_platform.execution.contracts import (
    ExecutionAdapter,
    OrderInstruction,
)
from quant_platform.execution.safety import (
    KillSwitch,
    KillSwitchState,
    SafetyCheck,
    SafetyLimits,
    check_order_safety,
    reconcile,
)

__all__ = [
    "ExecutionAdapter",
    "KillSwitch",
    "KillSwitchState",
    "OrderInstruction",
    "SafetyCheck",
    "SafetyLimits",
    "check_order_safety",
    "reconcile",
]
