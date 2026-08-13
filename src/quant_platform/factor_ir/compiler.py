from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from .model import (
    CallNode,
    CompiledFactorIR,
    Diagnostic,
    ExpressionNode,
    FactorIRCompileError,
    LiteralNode,
    PostprocessStep,
    RefNode,
    SeriesKind,
    ValueType,
)
from .operators import (
    DEFAULT_OPERATOR_REGISTRY,
    FORBIDDEN_OPERATOR_CODES,
    OperatorDefinition,
)

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_CLOCK = re.compile(
    r"^T(?:_CLOSE|_OPEN)?(?:(?P<sign>[+-])(?P<count>\d+)(?P<unit>m|h))?$"
)
_NEXT_DAY_CLOCK = re.compile(r"^T\+\d+_(?:OPEN|CLOSE)(?:\+\d+(?:m|h))?$")
_FUTURES_EXCHANGES = frozenset({"SHFE", "INE", "DCE", "CZCE", "GFEX"})
_MARKETS = frozenset({"CN_A", "CN_COMMODITY_FUTURES"})
_POSTPROCESS_OPERATORS = frozenset({"winsorize", "zscore", "cs_rank"})
_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "factor_id",
        "version",
        "origin",
        "economic_thesis",
        "market_scope",
        "decision_clock",
        "inputs",
        "expression",
        "postprocess",
        "missing_policy",
        "validation_policy_ref",
        "tags",
    }
)


@dataclass(frozen=True)
class _Input:
    alias: str
    value_type: ValueType
    available_time: str


@dataclass(frozen=True)
class _Analysis:
    value_type: ValueType
    lookback: int
    available_time: str
    operators: frozenset[str]


def compile_factor_ir(
    payload: Mapping[str, Any],
    *,
    operator_registry: Mapping[str, OperatorDefinition] = DEFAULT_OPERATOR_REGISTRY,
) -> CompiledFactorIR:
    document = _copy_json_object(payload)
    _validate_top_level(document)
    _validate_auxiliary_sections(document)
    _validate_market_scope(_object(document, "market_scope", "$"))
    decision_clock = _object(document, "decision_clock", "$")
    signal_time = _string(decision_clock, "signal_time", "$.decision_clock")
    _validate_clock(signal_time, "$.decision_clock.signal_time")
    _validate_clock(
        _string(decision_clock, "earliest_trade_time", "$.decision_clock"),
        "$.decision_clock.earliest_trade_time",
        allow_next_day=True,
    )
    inputs = _parse_inputs(document.get("inputs"), signal_time)
    ast = _parse_expression(
        document.get("expression"),
        "$.expression",
        operator_registry,
    )
    analysis = _analyze(ast, inputs, operator_registry, "$.expression")
    postprocess_steps, analysis = _parse_postprocess(
        document.get("postprocess"),
        analysis,
    )

    canonical_document = _canonical_document(document, ast, postprocess_steps)
    canonical_json = _canonical_json(canonical_document)
    canonical_expression_json = _canonical_json(_node_json(ast))
    return CompiledFactorIR(
        factor_id=_string(document, "factor_id", "$"),
        canonical_json=canonical_json,
        canonical_expression_json=canonical_expression_json,
        expression_hash=_sha256(canonical_expression_json),
        ir_hash=_sha256(canonical_json),
        ast=ast,
        output_type=analysis.value_type,
        lookback=analysis.lookback,
        available_time=analysis.available_time,
        operator_names=tuple(sorted(analysis.operators)),
        input_aliases=tuple(sorted(inputs)),
        postprocess_steps=postprocess_steps,
    )


def _copy_json_object(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        _fail("IR_NOT_JSON", f"IR must contain only finite JSON values: {exc}", "$")
    if not isinstance(decoded, dict):
        _fail("IR_SCHEMA", "IR root must be an object", "$")
    return cast(dict[str, Any], decoded)


def _validate_top_level(document: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "factor_id",
        "version",
        "market_scope",
        "decision_clock",
        "inputs",
        "expression",
        "validation_policy_ref",
    }
    missing = sorted(required - document.keys())
    if missing:
        _fail("IR_SCHEMA", f"missing required field {missing[0]}", f"$.{missing[0]}")
    unknown = sorted(document.keys() - _TOP_LEVEL_KEYS)
    if unknown:
        _fail("IR_SCHEMA", f"unknown top-level field {unknown[0]}", f"$.{unknown[0]}")
    if document["schema_version"] != "factor-ir/v1":
        _fail(
            "IR_SCHEMA_VERSION",
            "schema_version must be factor-ir/v1",
            "$.schema_version",
        )
    factor_id = _string(document, "factor_id", "$")
    if not _IDENTIFIER.fullmatch(factor_id):
        _fail("IR_SCHEMA", "factor_id is not a normalized identifier", "$.factor_id")
    version = _string(document, "version", "$")
    if not _SEMVER.fullmatch(version):
        _fail("IR_SCHEMA", "version must be semantic x.y.z", "$.version")
    policy = _string(document, "validation_policy_ref", "$")
    if "://" not in policy:
        _fail(
            "IR_SCHEMA",
            "validation_policy_ref must be a versioned reference",
            "$.validation_policy_ref",
        )


def _validate_auxiliary_sections(document: dict[str, Any]) -> None:
    missing_policy = document.get("missing_policy")
    if missing_policy is not None:
        if not isinstance(missing_policy, dict):
            _fail("IR_SCHEMA", "missing_policy must be an object", "$.missing_policy")
        allowed = {
            "max_missing_ratio",
            "min_observations",
            "imputation",
            "stale_limit",
        }
        unknown = set(missing_policy) - allowed
        if unknown:
            field = sorted(unknown)[0]
            _fail(
                "IR_SCHEMA",
                f"unknown missing policy field {field}",
                f"$.missing_policy.{field}",
            )
        imputation = missing_policy.get("imputation")
        if imputation in {"forward_fill", "ffill", "backfill", "bfill"}:
            _fail(
                "IR_FORWARD_FILL_FORBIDDEN",
                "forward/backward filling is forbidden in Factor IR",
                "$.missing_policy.imputation",
            )
        if imputation is not None and imputation not in {
            "none",
            "zero",
            "cross_section_median",
            "group_median",
        }:
            _fail(
                "IR_SCHEMA",
                "unsupported deterministic imputation policy",
                "$.missing_policy.imputation",
            )


def _validate_market_scope(scope: dict[str, Any]) -> None:
    market = _string(scope, "market", "$.market_scope")
    if market not in _MARKETS:
        _fail(
            "IR_UNSUPPORTED_MARKET",
            f"market {market!r} is not supported by Factor IR v1",
            "$.market_scope.market",
        )
    frequency = _string(scope, "frequency", "$.market_scope")
    if frequency != "1d":
        _fail(
            "IR_UNSUPPORTED_FREQUENCY",
            "Factor IR v1 only supports 1d",
            "$.market_scope.frequency",
        )
    _string(scope, "universe_ref", "$.market_scope")
    if market == "CN_COMMODITY_FUTURES":
        for field in ("exchange_scope", "contract_chain_ref", "roll_policy_ref"):
            if field not in scope or scope[field] in ("", [], None):
                _fail(
                    "IR_FUTURES_SCOPE_REQUIRED",
                    f"commodity futures scope requires {field}",
                    f"$.market_scope.{field}",
                )
        exchanges = scope["exchange_scope"]
        if not isinstance(exchanges, list) or any(
            not isinstance(item, str) for item in exchanges
        ):
            _fail(
                "IR_INVALID_EXCHANGE_SCOPE",
                "exchange_scope must be a non-empty array of exchange identifiers",
                "$.market_scope.exchange_scope",
            )
        invalid = sorted(set(exchanges) - _FUTURES_EXCHANGES)
        if invalid or len(exchanges) != len(set(exchanges)):
            _fail(
                "IR_INVALID_EXCHANGE_SCOPE",
                (
                    "exchange_scope must contain unique supported Chinese "
                    "futures exchanges"
                ),
                "$.market_scope.exchange_scope",
            )
        _string(scope, "contract_chain_ref", "$.market_scope")
        _string(scope, "roll_policy_ref", "$.market_scope")


def _parse_inputs(raw: Any, signal_time: str) -> dict[str, _Input]:
    if not isinstance(raw, list) or not raw:
        _fail("IR_SCHEMA", "inputs must be a non-empty array", "$.inputs")
    parsed: dict[str, _Input] = {}
    for index, item in enumerate(raw):
        path = f"$.inputs[{index}]"
        if not isinstance(item, dict):
            _fail("IR_SCHEMA", "input must be an object", path)
        alias = _string(item, "alias", path)
        if not _IDENTIFIER.fullmatch(alias):
            _fail("IR_SCHEMA", "input alias is not normalized", f"{path}.alias")
        if alias in parsed:
            _fail(
                "IR_DUPLICATE_INPUT",
                f"duplicate input alias {alias}",
                f"{path}.alias",
            )
        _string(item, "field_ref", path)
        type_name = _string(item, "data_type", path)
        try:
            kind = SeriesKind(type_name)
        except ValueError:
            _fail(
                "IR_UNKNOWN_TYPE",
                f"unsupported input data_type {type_name!r}",
                f"{path}.data_type",
            )
        if kind is SeriesKind.LABEL_SERIES:
            _fail(
                "IR_LABEL_SERIES_FORBIDDEN",
                "LabelSeries is reserved for validation and cannot enter Factor IR",
                f"{path}.data_type",
            )
        unit = _string(item, "unit", path)
        availability = _string(item, "available_time_rule", path)
        _validate_clock(availability, f"{path}.available_time_rule")
        if _clock_order(availability) > _clock_order(signal_time):
            _fail(
                "IR_FUTURE_AVAILABLE_TIME",
                (
                    f"input is available at {availability}, "
                    f"after signal time {signal_time}"
                ),
                f"{path}.available_time_rule",
            )
        parsed[alias] = _Input(alias, ValueType(kind, unit), availability)
    return parsed


def _parse_expression(
    raw: Any,
    path: str,
    registry: Mapping[str, OperatorDefinition],
) -> ExpressionNode:
    if not isinstance(raw, dict):
        _fail("IR_SCHEMA", "expression node must be an object", path)
    if "ref" in raw:
        if set(raw) != {"ref"} or not isinstance(raw["ref"], str):
            _fail("IR_SCHEMA", "reference node only permits string ref", path)
        return RefNode(raw["ref"])
    if "literal" in raw:
        if set(raw) - {"literal", "unit"}:
            _fail("IR_SCHEMA", "literal node has unknown fields", path)
        value = raw["literal"]
        if isinstance(value, bool) or not isinstance(value, int | float):
            _fail("IR_SCHEMA", "literal must be a finite number", f"{path}.literal")
        if isinstance(value, float) and not math.isfinite(value):
            _fail("IR_SCHEMA", "literal must be finite", f"{path}.literal")
        unit = raw.get("unit", "1")
        if not isinstance(unit, str) or not unit:
            _fail("IR_SCHEMA", "literal unit must be a string", f"{path}.unit")
        return LiteralNode(value, unit)
    if "op" not in raw or not isinstance(raw["op"], str):
        _fail("IR_SCHEMA", "expression node requires ref, literal, or op", path)

    operator_name = raw["op"]
    if operator_name in FORBIDDEN_OPERATOR_CODES:
        _fail(
            FORBIDDEN_OPERATOR_CODES[operator_name],
            f"operator {operator_name!r} is forbidden in Factor IR",
            f"{path}.op",
        )
    definition = registry.get(operator_name)
    if definition is None:
        _fail(
            "IR_UNKNOWN_OPERATOR",
            f"operator {operator_name!r} is not registered",
            f"{path}.op",
        )
    if not definition.allowed_in_factor:
        _fail(
            "IR_FORBIDDEN_OPERATOR",
            f"operator {operator_name!r} is not allowed in factors",
            f"{path}.op",
        )
    unknown = set(raw) - {"op", "args", "params"}
    if unknown:
        field = sorted(unknown)[0]
        _fail("IR_SCHEMA", f"unknown expression field {field}", f"{path}.{field}")
    args = raw.get("args")
    if not isinstance(args, list):
        _fail("IR_SCHEMA", "operator args must be an array", f"{path}.args")
    if not definition.min_args <= len(args) <= definition.max_args:
        _fail(
            "IR_ARITY",
            (
                f"{operator_name} expects "
                f"{definition.min_args}..{definition.max_args} args"
            ),
            f"{path}.args",
        )
    params = raw.get("params", {})
    if not isinstance(params, dict):
        _fail("IR_SCHEMA", "operator params must be an object", f"{path}.params")
    missing = definition.required_params - params.keys()
    if missing:
        parameter = sorted(missing)[0]
        code = (
            "IR_UNBOUNDED_WINDOW" if parameter == "window" else "IR_MISSING_PARAMETER"
        )
        _fail(
            code,
            f"{operator_name} requires bounded parameter {parameter}",
            f"{path}.params.{parameter}",
        )
    unknown_params = params.keys() - (
        definition.required_params | definition.optional_params
    )
    if unknown_params:
        parameter = sorted(unknown_params)[0]
        _fail(
            "IR_UNKNOWN_PARAMETER",
            f"{operator_name} does not accept parameter {parameter}",
            f"{path}.params.{parameter}",
        )
    _validate_parameters(operator_name, params, path)
    return CallNode(
        operator=operator_name,
        args=tuple(
            _parse_expression(arg, f"{path}.args[{index}]", registry)
            for index, arg in enumerate(args)
        ),
        params=tuple(sorted(params.items())),
    )


def _parse_postprocess(
    raw: Any,
    analysis: _Analysis,
) -> tuple[tuple[PostprocessStep, ...], _Analysis]:
    if raw is None:
        return (), analysis
    if not isinstance(raw, dict):
        _fail("IR_SCHEMA", "postprocess must be an object", "$.postprocess")
    for field in sorted(set(raw) - {"steps"}):
        path = f"$.postprocess.{field}"
        if field.startswith("exposure"):
            _fail(
                "IR_POSTPROCESS_EXPOSURE_UNSUPPORTED",
                "exposure-based postprocessing is not supported in Factor IR v1",
                path,
            )
        _fail("IR_SCHEMA", f"unknown postprocess field {field}", path)

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        _fail(
            "IR_SCHEMA",
            "postprocess steps must be a non-empty array",
            "$.postprocess.steps",
        )

    steps: list[PostprocessStep] = []
    current = analysis
    for index, item in enumerate(raw_steps):
        path = f"$.postprocess.steps[{index}]"
        if not isinstance(item, dict):
            _fail("IR_SCHEMA", "postprocess step must be an object", path)
        for field in sorted(set(item) - {"op", "params"}):
            field_path = f"{path}.{field}"
            if field.startswith("exposure"):
                _fail(
                    "IR_POSTPROCESS_EXPOSURE_UNSUPPORTED",
                    "exposure-based postprocessing is not supported in Factor IR v1",
                    field_path,
                )
            _fail(
                "IR_SCHEMA",
                f"unknown postprocess step field {field}",
                field_path,
            )
        operator_name = _string(item, "op", path)
        if operator_name not in _POSTPROCESS_OPERATORS:
            _fail(
                "IR_UNSUPPORTED_POSTPROCESS_OPERATOR",
                f"postprocess operator {operator_name!r} is not supported",
                f"{path}.op",
            )
        definition = DEFAULT_OPERATOR_REGISTRY[operator_name]
        if definition.min_args > 1 or definition.max_args < 1:
            _fail(
                "IR_UNSUPPORTED_POSTPROCESS_OPERATOR",
                f"postprocess operator {operator_name!r} is not unary",
                f"{path}.op",
            )
        params = item.get("params", {})
        if not isinstance(params, dict):
            _fail("IR_SCHEMA", "operator params must be an object", f"{path}.params")
        _validate_operator_params(definition, params, path)
        current = _analyze_postprocess_step(definition, params, current, path)
        steps.append(
            PostprocessStep(
                operator=operator_name,
                params=tuple(sorted(params.items())),
            )
        )
    return tuple(steps), current


def _validate_operator_params(
    definition: OperatorDefinition,
    params: dict[str, Any],
    path: str,
) -> None:
    missing = definition.required_params - params.keys()
    if missing:
        parameter = sorted(missing)[0]
        _fail(
            "IR_MISSING_PARAMETER",
            f"{definition.name} requires parameter {parameter}",
            f"{path}.params.{parameter}",
        )
    unknown_params = params.keys() - (
        definition.required_params | definition.optional_params
    )
    if unknown_params:
        parameter = sorted(unknown_params)[0]
        _fail(
            "IR_UNKNOWN_PARAMETER",
            f"{definition.name} does not accept parameter {parameter}",
            f"{path}.params.{parameter}",
        )
    _validate_parameters(definition.name, params, path)


def _validate_parameters(operator_name: str, params: dict[str, Any], path: str) -> None:
    for name in ("periods", "window", "min_periods"):
        if name not in params:
            continue
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(
                "IR_INVALID_PARAMETER",
                f"{name} must be an integer",
                f"{path}.params.{name}",
            )
        if name == "periods" and operator_name == "lag" and value < 0:
            _fail(
                "IR_NEGATIVE_LAG",
                "lag periods cannot be negative",
                f"{path}.params.periods",
            )
        if value <= 0 and not (
            name == "periods" and operator_name == "lag" and value == 0
        ):
            code = "IR_UNBOUNDED_WINDOW" if name == "window" else "IR_INVALID_PARAMETER"
            _fail(code, f"{name} must be positive", f"{path}.params.{name}")
    if "window" in params and params.get("min_periods", 1) > params["window"]:
        _fail(
            "IR_INVALID_PARAMETER",
            "min_periods cannot exceed window",
            f"{path}.params.min_periods",
        )
    if (
        operator_name in {"safe_div", "div"}
        and "zero_policy" in params
        and params["zero_policy"] not in {"null", "zero"}
    ):
        _fail(
            "IR_INVALID_PARAMETER",
            "zero_policy must be null or zero",
            f"{path}.params.zero_policy",
        )
    if operator_name == "winsorize":
        if params.get("method") != "mad":
            _fail(
                "IR_INVALID_PARAMETER",
                "winsorize method must be mad",
                f"{path}.params.method",
            )
        limit = params.get("limit")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int | float)
            or not math.isfinite(limit)
            or limit <= 0
        ):
            _fail(
                "IR_INVALID_PARAMETER",
                "winsorize limit must be a positive finite number",
                f"{path}.params.limit",
            )


def _analyze(
    node: ExpressionNode,
    inputs: Mapping[str, _Input],
    registry: Mapping[str, OperatorDefinition],
    path: str,
) -> _Analysis:
    if isinstance(node, RefNode):
        input_definition = inputs.get(node.alias)
        if input_definition is None:
            _fail(
                "IR_UNKNOWN_INPUT",
                f"expression references undeclared input {node.alias!r}",
                f"{path}.ref",
            )
        return _Analysis(
            input_definition.value_type,
            0,
            input_definition.available_time,
            frozenset(),
        )
    if isinstance(node, LiteralNode):
        return _Analysis(
            ValueType(SeriesKind.SCALAR_SERIES, node.unit),
            0,
            "T",
            frozenset(),
        )

    definition = registry[node.operator]
    children = tuple(
        _analyze(child, inputs, registry, f"{path}.args[{index}]")
        for index, child in enumerate(node.args)
    )
    kind = _infer_kind(definition, children, path)
    unit = _infer_unit(definition, children, dict(node.params), path)
    lookback = _infer_lookback(definition, children, dict(node.params))
    available_time = max(
        (child.available_time for child in children),
        key=_clock_order,
        default="T",
    )
    operators = frozenset({node.operator}).union(
        *(child.operators for child in children)
    )
    return _Analysis(ValueType(kind, unit), lookback, available_time, operators)


def _analyze_postprocess_step(
    definition: OperatorDefinition,
    params: dict[str, Any],
    child: _Analysis,
    path: str,
) -> _Analysis:
    children = (child,)
    kind = _infer_kind(definition, children, path)
    unit = _infer_unit(definition, children, params, path)
    lookback = _infer_lookback(definition, children, params)
    return _Analysis(
        value_type=ValueType(kind, unit),
        lookback=lookback,
        available_time=child.available_time,
        operators=child.operators | {definition.name},
    )


def _infer_kind(
    definition: OperatorDefinition,
    children: tuple[_Analysis, ...],
    path: str,
) -> SeriesKind:
    kinds = {child.value_type.kind for child in children}
    if len(kinds) > 1:
        _fail(
            "IR_TYPE_MISMATCH",
            f"{definition.name} arguments have incompatible series kinds",
            f"{path}.args",
        )
    kind = children[0].value_type.kind
    if kind in {
        SeriesKind.EVENT_SERIES,
        SeriesKind.UNIVERSE_MASK,
        SeriesKind.EXPOSURE_MATRIX,
    }:
        _fail(
            "IR_TYPE_MISMATCH",
            f"{definition.name} does not accept {kind.value}",
            f"{path}.args",
        )
    if definition.type_rule == "cross_section_output":
        return SeriesKind.CROSS_SECTION
    return kind


def _infer_unit(
    definition: OperatorDefinition,
    children: tuple[_Analysis, ...],
    params: dict[str, Any],
    path: str,
) -> str:
    units = tuple(child.value_type.unit for child in children)
    if definition.unit_rule == "same":
        if len(set(units)) != 1:
            _fail(
                "IR_UNIT_MISMATCH",
                f"{definition.name} requires identical units, got {units}",
                f"{path}.args",
            )
        return units[0]
    if definition.unit_rule == "dimensionless":
        if units[0] != "1":
            _fail(
                "IR_UNIT_MISMATCH",
                f"{definition.name} requires dimensionless input",
                f"{path}.args[0]",
            )
        return "1"
    if definition.unit_rule == "dimensionless_output":
        return "1"
    if definition.unit_rule == "multiply":
        return _multiply_units(units[0], units[1])
    if definition.unit_rule == "divide":
        return _divide_units(units[0], units[1])
    if definition.unit_rule == "power":
        exponent = params["exponent"]
        if not isinstance(exponent, int | float) or isinstance(exponent, bool):
            _fail(
                "IR_INVALID_PARAMETER",
                "exponent must be numeric",
                f"{path}.params.exponent",
            )
        if units[0] == "1":
            return "1"
        return f"{units[0]}^{exponent}"
    return units[0]


def _infer_lookback(
    definition: OperatorDefinition,
    children: tuple[_Analysis, ...],
    params: dict[str, Any],
) -> int:
    child_lookback = max((child.lookback for child in children), default=0)
    if definition.lookback_rule == "periods":
        return child_lookback + int(params["periods"])
    if definition.lookback_rule == "window":
        return child_lookback + int(params["window"]) - 1
    return child_lookback


def _multiply_units(left: str, right: str) -> str:
    if left == "1":
        return right
    if right == "1":
        return left
    return f"{left}*{right}"


def _divide_units(left: str, right: str) -> str:
    if left == right:
        return "1"
    if right == "1":
        return left
    return f"{left}/{right}"


def _validate_clock(value: str, path: str, *, allow_next_day: bool = False) -> None:
    if _CLOCK.fullmatch(value):
        return
    if allow_next_day and _NEXT_DAY_CLOCK.fullmatch(value):
        return
    _fail(
        "IR_INVALID_AVAILABLE_TIME",
        f"unsupported deterministic clock expression {value!r}",
        path,
    )


def _clock_order(value: str) -> int:
    match = _CLOCK.fullmatch(value)
    if match is None:
        _fail(
            "IR_INVALID_AVAILABLE_TIME",
            f"unsupported deterministic clock expression {value!r}",
            "$",
        )
    base = 24 * 60 if "_CLOSE" in value else 0
    count = int(match.group("count") or 0)
    if match.group("unit") == "h":
        count *= 60
    if match.group("sign") == "-":
        count = -count
    return base + count


def _object(mapping: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        _fail("IR_SCHEMA", f"{key} must be an object", f"{path}.{key}")
    return cast(dict[str, Any], value)


def _string(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        _fail(
            "IR_SCHEMA",
            f"{key} must be a non-empty normalized string",
            f"{path}.{key}",
        )
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_document(
    document: dict[str, Any],
    ast: ExpressionNode,
    postprocess_steps: tuple[PostprocessStep, ...],
) -> dict[str, Any]:
    canonical = dict(document)
    canonical["inputs"] = sorted(
        document["inputs"],
        key=lambda item: item["alias"],
    )
    market_scope = dict(document["market_scope"])
    if "exchange_scope" in market_scope:
        market_scope["exchange_scope"] = sorted(market_scope["exchange_scope"])
    canonical["market_scope"] = market_scope
    canonical["expression"] = _node_json(ast)
    if postprocess_steps:
        canonical["postprocess"] = {
            "steps": [
                {
                    "op": step.operator,
                    **({"params": dict(step.params)} if step.params else {}),
                }
                for step in postprocess_steps
            ]
        }
    return canonical


def _node_json(node: ExpressionNode) -> dict[str, Any]:
    if isinstance(node, RefNode):
        return {"ref": node.alias}
    if isinstance(node, LiteralNode):
        result: dict[str, Any] = {"literal": node.value}
        if node.unit != "1":
            result["unit"] = node.unit
        return result
    result = {
        "op": node.operator,
        "args": [_node_json(child) for child in node.args],
    }
    if node.params:
        result["params"] = dict(node.params)
    return result


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fail(code: str, message: str, path: str) -> NoReturn:
    raise FactorIRCompileError((Diagnostic(code, message, path),))
