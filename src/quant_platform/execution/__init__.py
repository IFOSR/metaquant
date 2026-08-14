"""Execution layer (G15): adapter boundary, safety controls, shadow/paper."""

from quant_platform.execution.contracts import (
    ExecutionAdapter,
    OrderInstruction,
)
from quant_platform.execution.runtime import (
    OrderSuggestion,
    shadow_rebalance,
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
    "OrderSuggestion",
    "SafetyCheck",
    "SafetyLimits",
    "check_order_safety",
    "reconcile",
    "shadow_rebalance",
]
