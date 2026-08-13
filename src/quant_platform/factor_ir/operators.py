from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class OperatorDefinition:
    name: str
    category: str
    min_args: int
    max_args: int
    required_params: frozenset[str] = frozenset()
    optional_params: frozenset[str] = frozenset()
    bounded_lookback: bool = True
    allowed_in_factor: bool = True
    availability_rule: str = "max_inputs"
    type_rule: str = "same_series"
    unit_rule: str = "preserve"
    lookback_rule: str = "max_inputs"


def _operator(
    name: str,
    category: str,
    min_args: int,
    max_args: int,
    *,
    required_params: frozenset[str] = frozenset(),
    optional_params: frozenset[str] = frozenset(),
    type_rule: str = "same_series",
    unit_rule: str = "preserve",
    lookback_rule: str = "max_inputs",
) -> OperatorDefinition:
    return OperatorDefinition(
        name=name,
        category=category,
        min_args=min_args,
        max_args=max_args,
        required_params=required_params,
        optional_params=optional_params,
        type_rule=type_rule,
        unit_rule=unit_rule,
        lookback_rule=lookback_rule,
    )


_OPERATORS = (
    _operator("neg", "algebra", 1, 1),
    _operator("abs", "algebra", 1, 1),
    _operator("add", "algebra", 2, 2, unit_rule="same"),
    _operator("sub", "algebra", 2, 2, unit_rule="same"),
    _operator("mul", "algebra", 2, 2, unit_rule="multiply"),
    _operator(
        "div",
        "algebra",
        2,
        2,
        optional_params=frozenset({"zero_policy"}),
        unit_rule="divide",
    ),
    _operator(
        "safe_div",
        "algebra",
        2,
        2,
        required_params=frozenset({"zero_policy"}),
        unit_rule="divide",
    ),
    _operator("log", "algebra", 1, 1, unit_rule="dimensionless"),
    _operator(
        "signed_power",
        "algebra",
        1,
        1,
        required_params=frozenset({"exponent"}),
        unit_rule="power",
    ),
    _operator(
        "clip",
        "conditional",
        1,
        1,
        required_params=frozenset({"lower", "upper"}),
    ),
    _operator(
        "lag",
        "time_series",
        1,
        1,
        required_params=frozenset({"periods"}),
        lookback_rule="periods",
    ),
    _operator(
        "delta",
        "time_series",
        1,
        1,
        required_params=frozenset({"periods"}),
        lookback_rule="periods",
    ),
    _operator(
        "returns",
        "time_series",
        1,
        1,
        required_params=frozenset({"periods"}),
        unit_rule="dimensionless_output",
        lookback_rule="periods",
    ),
    _operator(
        "rolling_mean",
        "time_series",
        1,
        1,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        lookback_rule="window",
    ),
    _operator(
        "rolling_std",
        "time_series",
        1,
        1,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        lookback_rule="window",
    ),
    _operator(
        "rolling_min",
        "time_series",
        1,
        1,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        lookback_rule="window",
    ),
    _operator(
        "rolling_max",
        "time_series",
        1,
        1,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        lookback_rule="window",
    ),
    _operator(
        "ts_rank",
        "time_series",
        1,
        1,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        unit_rule="dimensionless_output",
        lookback_rule="window",
    ),
    _operator(
        "ts_corr",
        "time_series",
        2,
        2,
        required_params=frozenset({"window"}),
        optional_params=frozenset({"min_periods"}),
        unit_rule="dimensionless_output",
        lookback_rule="window",
    ),
    _operator(
        "cs_rank",
        "cross_section",
        1,
        1,
        type_rule="cross_section_output",
        unit_rule="dimensionless_output",
    ),
    _operator(
        "zscore",
        "cross_section",
        1,
        1,
        type_rule="cross_section_output",
        unit_rule="dimensionless_output",
    ),
    _operator(
        "winsorize",
        "cross_section",
        1,
        1,
        required_params=frozenset({"method", "limit"}),
        type_rule="cross_section_output",
    ),
)

DEFAULT_OPERATOR_REGISTRY: Mapping[str, OperatorDefinition] = MappingProxyType(
    {operator.name: operator for operator in _OPERATORS}
)

FORBIDDEN_OPERATOR_CODES: Mapping[str, str] = MappingProxyType(
    {
        "backfill": "IR_FORWARD_FILL_FORBIDDEN",
        "bfill": "IR_FORWARD_FILL_FORBIDDEN",
        "forward_fill": "IR_FORWARD_FILL_FORBIDDEN",
        "eval": "IR_FORBIDDEN_OPERATOR",
        "exec": "IR_FORBIDDEN_OPERATOR",
        "open": "IR_FORBIDDEN_OPERATOR",
        "read_csv": "IR_FORBIDDEN_OPERATOR",
        "read_file": "IR_FORBIDDEN_OPERATOR",
        "request": "IR_FORBIDDEN_OPERATOR",
        "shell": "IR_FORBIDDEN_OPERATOR",
        "sql": "IR_FORBIDDEN_OPERATOR",
        "udf": "IR_FORBIDDEN_OPERATOR",
    }
)
