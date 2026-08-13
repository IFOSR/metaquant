from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from quant_platform.factor_executor import (
    FactorExecutionError,
    FactorInputRow,
    FactorTable,
    execute_factor,
)
from quant_platform.factor_ir import compile_factor_ir


def at(day: int) -> datetime:
    return datetime(2026, 8, day, 15, tzinfo=UTC)


def spec(
    expression: Mapping[str, object],
    *,
    aliases: tuple[str, ...] = ("x",),
    postprocess: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "factor-ir/v1",
        "factor_id": "test.factor",
        "version": "1.0.0",
        "market_scope": {
            "market": "CN_A",
            "frequency": "1d",
            "universe_ref": "universe://test/pit/v1",
        },
        "decision_clock": {
            "signal_time": "T_CLOSE+30m",
            "earliest_trade_time": "T+1_OPEN",
        },
        "inputs": [
            {
                "alias": alias,
                "field_ref": f"test.{alias}",
                "data_type": "ScalarSeries",
                "unit": "1",
                "available_time_rule": "T_CLOSE+20m",
            }
            for alias in aliases
        ],
        "expression": expression,
        "validation_policy_ref": "policy://test/v1",
    }
    if postprocess is not None:
        payload["postprocess"] = postprocess
    return payload


def table(
    values: dict[str, list[float | int | None]],
    *,
    instruments: tuple[str, ...] = ("600000.SSE",),
) -> FactorTable:
    rows = []
    for instrument in instruments:
        for index in range(len(next(iter(values.values())))):
            rows.append(
                FactorInputRow(
                    timestamp=at(index + 1),
                    instrument_id=instrument,
                    values={name: series[index] for name, series in values.items()},
                )
            )
    return FactorTable(tuple(rows))


def output_values(
    expression: Mapping[str, object],
    inputs: FactorTable,
    *,
    aliases: tuple[str, ...] = ("x",),
) -> list[float | None]:
    result = execute_factor(
        compile_factor_ir(spec(expression, aliases=aliases)), inputs
    )
    return [item.value for item in result.observations]


def test_algebra_propagates_null_and_handles_divide_by_zero_explicitly() -> None:
    expression = {
        "op": "safe_div",
        "args": [{"ref": "x"}, {"ref": "y"}],
        "params": {"zero_policy": "null"},
    }

    assert output_values(
        expression,
        table({"x": [4, None, 6], "y": [2, 1, 0]}),
        aliases=("x", "y"),
    ) == [2.0, None, None]

    zero_expression = {
        "op": "safe_div",
        "args": [{"ref": "x"}, {"ref": "y"}],
        "params": {"zero_policy": "zero"},
    }
    assert output_values(
        zero_expression,
        table({"x": [4], "y": [0]}),
        aliases=("x", "y"),
    ) == [0.0]


def test_window_operators_group_by_instrument_and_apply_min_periods() -> None:
    expression = {
        "op": "rolling_mean",
        "args": [{"ref": "x"}],
        "params": {"window": 3, "min_periods": 2},
    }
    rows = (
        FactorInputRow(at(1), "A.SSE", {"x": 1}),
        FactorInputRow(at(1), "B.SSE", {"x": 100}),
        FactorInputRow(at(2), "A.SSE", {"x": None}),
        FactorInputRow(at(2), "B.SSE", {"x": 200}),
        FactorInputRow(at(3), "A.SSE", {"x": 3}),
        FactorInputRow(at(3), "B.SSE", {"x": 300}),
    )

    result = execute_factor(
        compile_factor_ir(spec(expression)),
        FactorTable(rows),
    )

    assert [
        (item.instrument_id, item.timestamp.day, item.value)
        for item in result.observations
    ] == [
        ("A.SSE", 1, None),
        ("B.SSE", 1, None),
        ("A.SSE", 2, None),
        ("B.SSE", 2, 150.0),
        ("A.SSE", 3, 2.0),
        ("B.SSE", 3, 200.0),
    ]


def test_lag_delta_returns_and_correlation_never_cross_instruments() -> None:
    returns = {
        "op": "returns",
        "args": [{"ref": "x"}],
        "params": {"periods": 1},
    }
    rows = FactorTable(
        (
            FactorInputRow(at(1), "A.SSE", {"x": 10}),
            FactorInputRow(at(1), "B.SSE", {"x": 100}),
            FactorInputRow(at(2), "A.SSE", {"x": 12}),
            FactorInputRow(at(2), "B.SSE", {"x": 50}),
        )
    )

    assert [
        item.value
        for item in execute_factor(
            compile_factor_ir(spec(returns)),
            rows,
        ).observations
    ] == [None, None, 0.2, -0.5]

    correlation = {
        "op": "ts_corr",
        "args": [{"ref": "x"}, {"ref": "y"}],
        "params": {"window": 3, "min_periods": 3},
    }
    assert output_values(
        correlation,
        table({"x": [1, 2, 3, 4], "y": [2, 4, 6, None]}),
        aliases=("x", "y"),
    ) == [None, None, 1.0, None]


def test_cross_section_pipeline_is_per_timestamp_and_ignores_missing_values() -> None:
    compiled = compile_factor_ir(
        spec(
            {"ref": "x"},
            postprocess={
                "steps": [
                    {
                        "op": "winsorize",
                        "params": {"method": "mad", "limit": 1.0},
                    },
                    {"op": "zscore"},
                    {"op": "cs_rank"},
                ]
            },
        )
    )
    rows = FactorTable(
        (
            FactorInputRow(at(1), "A.SSE", {"x": 1}),
            FactorInputRow(at(1), "B.SSE", {"x": 2}),
            FactorInputRow(at(1), "C.SSE", {"x": 100}),
            FactorInputRow(at(1), "D.SSE", {"x": None}),
            FactorInputRow(at(2), "A.SSE", {"x": 5}),
            FactorInputRow(at(2), "B.SSE", {"x": 5}),
        )
    )

    result = execute_factor(compiled, rows)

    assert [item.value for item in result.observations] == [
        0.0,
        0.5,
        1.0,
        None,
        0.5,
        0.5,
    ]


def test_executor_requires_exact_input_columns_and_rejects_tampered_ir() -> None:
    compiled = compile_factor_ir(spec({"ref": "x"}))
    with pytest.raises(FactorExecutionError, match="missing input"):
        execute_factor(
            compiled,
            FactorTable((FactorInputRow(at(1), "A.SSE", {"y": 1}),)),
        )

    tampered = compile_factor_ir(spec({"ref": "x"}))
    object.__setattr__(tampered.ast, "alias", "future_return")
    with pytest.raises(FactorExecutionError, match="integrity"):
        execute_factor(
            tampered,
            FactorTable((FactorInputRow(at(1), "A.SSE", {"x": 1}),)),
        )
