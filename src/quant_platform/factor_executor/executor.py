from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Callable
from typing import TypeGuard

from quant_platform.factor_executor.model import (
    FactorExecutionError,
    FactorExecutionResult,
    FactorObservation,
    FactorTable,
    canonical_observations,
)
from quant_platform.factor_ir import (
    CallNode,
    CompiledFactorIR,
    LiteralNode,
    RefNode,
)

Series = list[float | None]


def _numeric(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FactorExecutionError(f"{name} must be numeric")
    return float(value)


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FactorExecutionError(f"{name} must be an integer")
    return value


def _present(value: float | None) -> TypeGuard[float]:
    return value is not None


def _node_json(node: RefNode | LiteralNode | CallNode) -> dict[str, object]:
    if isinstance(node, RefNode):
        return {"ref": node.alias}
    if isinstance(node, LiteralNode):
        result: dict[str, object] = {"literal": node.value}
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


def _check_integrity(compiled: CompiledFactorIR) -> None:
    encoded = json.dumps(
        _node_json(compiled.ast),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if encoded != compiled.canonical_expression_json:
        raise FactorExecutionError("compiled IR integrity check failed")
    if hashlib.sha256(encoded.encode()).hexdigest() != compiled.expression_hash:
        raise FactorExecutionError("compiled IR integrity hash failed")
    if (
        hashlib.sha256(compiled.canonical_json.encode("utf-8")).hexdigest()
        != compiled.ir_hash
    ):
        raise FactorExecutionError("compiled IR integrity hash failed")


def execute_factor(
    compiled: CompiledFactorIR,
    table: FactorTable,
) -> FactorExecutionResult:
    _check_integrity(compiled)
    for alias in compiled.input_aliases:
        if any(alias not in row.values for row in table.rows):
            raise FactorExecutionError(f"missing input {alias}")

    by_instrument: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(table.rows):
        by_instrument[row.instrument_id].append(index)

    values = _evaluate(compiled.ast, compiled, table, by_instrument)
    for step in compiled.postprocess_steps:
        values = _cross_section(
            step.operator,
            dict(step.params),
            values,
            table,
        )
    observations = tuple(
        FactorObservation(row.timestamp, row.instrument_id, values[index])
        for index, row in enumerate(table.rows)
    )
    canonical, output_hash = canonical_observations(observations, "factor")
    return FactorExecutionResult(
        factor_id=compiled.factor_id,
        ir_hash=compiled.ir_hash,
        observations=observations,
        canonical_json=canonical,
        output_hash=output_hash,
    )


def _evaluate(
    node: RefNode | LiteralNode | CallNode,
    compiled: CompiledFactorIR,
    table: FactorTable,
    groups: dict[str, list[int]],
) -> Series:
    if isinstance(node, RefNode):
        if node.alias not in compiled.input_aliases:
            raise FactorExecutionError("compiled IR integrity references unknown input")
        return [row.values[node.alias] for row in table.rows]
    if isinstance(node, LiteralNode):
        return [float(node.value)] * len(table.rows)

    args = [_evaluate(child, compiled, table, groups) for child in node.args]
    params = dict(node.params)
    operator = node.operator
    if operator in {"neg", "abs", "log", "signed_power", "clip"}:
        return _unary(operator, params, args[0])
    if operator in {"add", "sub", "mul", "div", "safe_div"}:
        return _binary(operator, params, args[0], args[1])
    if operator in {
        "lag",
        "delta",
        "returns",
        "rolling_mean",
        "rolling_std",
        "rolling_min",
        "rolling_max",
        "ts_rank",
    }:
        return _time_series(operator, params, args[0], groups)
    if operator == "ts_corr":
        return _time_correlation(params, args[0], args[1], groups)
    if operator in {"cs_rank", "zscore", "winsorize"}:
        return _cross_section(operator, params, args[0], table)
    raise FactorExecutionError(f"operator {operator} has no executor")


def _unary(operator: str, params: dict[str, object], values: Series) -> Series:
    def apply(value: float) -> float | None:
        if operator == "neg":
            return -value
        if operator == "abs":
            return abs(value)
        if operator == "log":
            return math.log(value) if value > 0 else None
        if operator == "signed_power":
            exponent = _numeric(params["exponent"], "exponent")
            return math.copysign(abs(value) ** exponent, value)
        if operator == "clip":
            lower = _numeric(params["lower"], "lower")
            upper = _numeric(params["upper"], "upper")
            return min(max(value, lower), upper)
        raise AssertionError("unreachable")

    return [_safe_apply(apply, value) for value in values]


def _binary(
    operator: str,
    params: dict[str, object],
    left: Series,
    right: Series,
) -> Series:
    result: Series = []
    for first, second in zip(left, right, strict=True):
        if first is None or second is None:
            result.append(None)
            continue
        if operator == "add":
            result_value: float | None = first + second
        elif operator == "sub":
            result_value = first - second
        elif operator == "mul":
            result_value = first * second
        elif operator in {"div", "safe_div"}:
            if second == 0:
                policy = params.get("zero_policy", "null")
                result_value = 0.0 if policy == "zero" else None
            else:
                result_value = first / second
        else:
            raise AssertionError("unreachable")
        result.append(
            result_value
            if result_value is None or math.isfinite(result_value)
            else None
        )
    return result


def _time_series(
    operator: str,
    params: dict[str, object],
    values: Series,
    groups: dict[str, list[int]],
) -> Series:
    output: Series = [None] * len(values)
    for indices in groups.values():
        local = [values[index] for index in indices]
        for position, index in enumerate(indices):
            if operator in {"lag", "delta", "returns"}:
                periods = _integer(params["periods"], "periods")
                previous = position - periods
                if previous < 0:
                    continue
                current_value = local[position]
                previous_value = local[previous]
                if current_value is None or previous_value is None:
                    continue
                if operator == "lag":
                    output[index] = previous_value
                elif operator == "delta":
                    output[index] = current_value - previous_value
                elif previous_value != 0:
                    output[index] = (current_value - previous_value) / previous_value
                continue

            window = _integer(params["window"], "window")
            min_periods = _integer(params.get("min_periods", window), "min_periods")
            sample = [
                item
                for item in local[max(0, position - window + 1) : position + 1]
                if item is not None
            ]
            if len(sample) < min_periods:
                continue
            output[index] = _window_value(operator, sample)
    return output


def _window_value(operator: str, sample: list[float]) -> float | None:
    if operator == "rolling_mean":
        return statistics.fmean(sample)
    if operator == "rolling_std":
        return statistics.pstdev(sample)
    if operator == "rolling_min":
        return min(sample)
    if operator == "rolling_max":
        return max(sample)
    if operator == "ts_rank":
        return _rank(sample, sample[-1])
    raise AssertionError("unreachable")


def _time_correlation(
    params: dict[str, object],
    left: Series,
    right: Series,
    groups: dict[str, list[int]],
) -> Series:
    output: Series = [None] * len(left)
    window = _integer(params["window"], "window")
    min_periods = _integer(params.get("min_periods", window), "min_periods")
    for indices in groups.values():
        for position, index in enumerate(indices):
            start = max(0, position - window + 1)
            pairs = [
                (left[other], right[other])
                for other in indices[start : position + 1]
                if left[other] is not None and right[other] is not None
            ]
            if len(pairs) < min_periods:
                continue
            xs = [pair[0] for pair in pairs if _present(pair[0])]
            ys = [pair[1] for pair in pairs if _present(pair[1])]
            if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
                continue
            output[index] = statistics.correlation(xs, ys)
    return output


def _cross_section(
    operator: str,
    params: dict[str, object],
    values: Series,
    table: FactorTable,
) -> Series:
    output = list(values)
    by_time: dict[object, list[int]] = defaultdict(list)
    for index, row in enumerate(table.rows):
        by_time[row.timestamp].append(index)
    for indices in by_time.values():
        present = [
            (index, values[index]) for index in indices if values[index] is not None
        ]
        if not present:
            continue
        sample = [value for _, value in present if _present(value)]
        if operator == "winsorize":
            median = statistics.median(sample)
            mad = statistics.median(abs(value - median) for value in sample)
            limit = _numeric(params["limit"], "limit")
            low, high = median - limit * mad, median + limit * mad
            transformed = [min(max(value, low), high) for value in sample]
        elif operator == "zscore":
            mean = statistics.fmean(sample)
            std = statistics.pstdev(sample)
            transformed = (
                [(value - mean) / std for value in sample]
                if std
                else [0.0] * len(sample)
            )
        elif operator == "cs_rank":
            transformed = [_rank(sample, value) for value in sample]
        else:
            raise FactorExecutionError(f"unsupported cross-section operator {operator}")
        for (index, _), value in zip(present, transformed, strict=True):
            output[index] = value
    return output


def _rank(sample: list[float], value: float) -> float:
    if len(sample) == 1:
        return 0.5
    less = sum(item < value for item in sample)
    equal = sum(item == value for item in sample)
    average_index = less + (equal - 1) / 2
    return average_index / (len(sample) - 1)


def _safe_apply(
    operation: Callable[[float], float | None],
    value: float | None,
) -> float | None:
    if value is None:
        return None
    try:
        result = operation(value)
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    return result if result is None or math.isfinite(result) else None
