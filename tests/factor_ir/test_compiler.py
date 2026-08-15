from __future__ import annotations

import json
from copy import deepcopy

import pytest

from quant_platform.factor_ir import (
    DEFAULT_OPERATOR_REGISTRY,
    FactorIRCompileError,
    PostprocessStep,
    SeriesKind,
    compile_factor_ir,
)


def equity_spec() -> dict[str, object]:
    return {
        "schema_version": "factor-ir/v1",
        "factor_id": "price.momentum_20d",
        "version": "1.0.0",
        "market_scope": {
            "market": "CN_A",
            "frequency": "1d",
            "universe_ref": "universe://csi800_pit",
        },
        "decision_clock": {
            "signal_time": "T_CLOSE+30m",
            "earliest_trade_time": "T+1_OPEN",
        },
        "inputs": [
            {
                "alias": "close",
                "field_ref": "market.eod.close_adjusted",
                "data_type": "ScalarSeries",
                "unit": "CNY",
                "available_time_rule": "T_CLOSE+20m",
            }
        ],
        "expression": {
            "op": "returns",
            "args": [{"ref": "close"}],
            "params": {"periods": 20},
        },
        "validation_policy_ref": "policy://cn-a-daily-factor/v1",
    }


def compile_error(spec: dict[str, object]) -> FactorIRCompileError:
    with pytest.raises(FactorIRCompileError) as caught:
        compile_factor_ir(spec)
    return caught.value


def test_compiles_typed_factor_and_infers_dependencies() -> None:
    compiled = compile_factor_ir(equity_spec())

    assert compiled.factor_id == "price.momentum_20d"
    assert compiled.output_type.kind is SeriesKind.SCALAR_SERIES
    assert compiled.output_type.unit == "1"
    assert compiled.lookback == 20
    assert compiled.available_time == "T_CLOSE+20m"
    assert compiled.operator_names == ("returns",)
    assert compiled.input_aliases == ("close",)
    assert len(compiled.expression_hash) == 64
    assert len(compiled.ir_hash) == 64
    assert json.loads(compiled.canonical_json)["expression"] == {
        "args": [{"ref": "close"}],
        "op": "returns",
        "params": {"periods": 20},
    }


def test_canonical_json_and_hash_are_independent_of_mapping_order() -> None:
    first = equity_spec()
    second = {
        "validation_policy_ref": first["validation_policy_ref"],
        "expression": {
            "params": {"periods": 20},
            "args": [{"ref": "close"}],
            "op": "returns",
        },
        "inputs": first["inputs"],
        "decision_clock": first["decision_clock"],
        "market_scope": first["market_scope"],
        "version": first["version"],
        "factor_id": first["factor_id"],
        "schema_version": first["schema_version"],
    }

    left = compile_factor_ir(first)
    right = compile_factor_ir(second)

    assert left.canonical_json == right.canonical_json
    assert left.expression_hash == right.expression_hash
    assert left.ir_hash == right.ir_hash


def test_canonicalization_normalizes_empty_params_and_input_order() -> None:
    first = equity_spec()
    inputs = first["inputs"]
    assert isinstance(inputs, list)
    inputs.append(
        {
            "alias": "volume",
            "field_ref": "market.eod.volume",
            "data_type": "ScalarSeries",
            "unit": "SHARE",
            "available_time_rule": "T_CLOSE+20m",
        }
    )
    first["expression"] = {"op": "abs", "args": [{"ref": "close"}]}
    second = deepcopy(first)
    second_inputs = second["inputs"]
    assert isinstance(second_inputs, list)
    second_inputs.reverse()
    second["expression"] = {
        "op": "abs",
        "args": [{"ref": "close"}],
        "params": {},
    }

    left = compile_factor_ir(first)
    right = compile_factor_ir(second)

    assert left.canonical_json == right.canonical_json
    assert left.expression_hash == right.expression_hash
    assert left.ir_hash == right.ir_hash


def test_operator_registry_declares_static_semantics() -> None:
    returns = DEFAULT_OPERATOR_REGISTRY["returns"]
    rolling_mean = DEFAULT_OPERATOR_REGISTRY["rolling_mean"]

    assert returns.category == "time_series"
    assert returns.bounded_lookback is True
    assert returns.allowed_in_factor is True
    assert returns.availability_rule == "max_inputs"
    assert rolling_mean.required_params == frozenset({"window"})

    with pytest.raises(TypeError):
        DEFAULT_OPERATOR_REGISTRY["custom"] = returns  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda spec: spec.update(
                expression={
                    "op": "lag",
                    "args": [{"ref": "close"}],
                    "params": {"periods": -1},
                }
            ),
            "IR_NEGATIVE_LAG",
        ),
        (
            lambda spec: spec.update(
                expression={
                    "op": "rolling_mean",
                    "args": [{"ref": "close"}],
                    "params": {},
                }
            ),
            "IR_UNBOUNDED_WINDOW",
        ),
        (
            lambda spec: spec.update(
                expression={
                    "op": "forward_fill",
                    "args": [{"ref": "close"}],
                }
            ),
            "IR_FORWARD_FILL_FORBIDDEN",
        ),
        (
            lambda spec: spec.update(
                expression={"op": "eval", "args": [{"ref": "close"}]}
            ),
            "IR_FORBIDDEN_OPERATOR",
        ),
        (
            lambda spec: spec.update(
                expression={"op": "read_csv", "args": [{"ref": "close"}]}
            ),
            "IR_FORBIDDEN_OPERATOR",
        ),
        (
            lambda spec: spec.update(
                expression={"op": "my_udf", "args": [{"ref": "close"}]}
            ),
            "IR_UNKNOWN_OPERATOR",
        ),
    ],
)
def test_rejects_lookahead_unbounded_and_executable_constructs(
    mutation: object,
    code: str,
) -> None:
    spec = equity_spec()
    mutation(spec)  # type: ignore[operator]

    error = compile_error(spec)

    assert error.diagnostics[0].code == code
    assert error.diagnostics[0].path.startswith("$.expression")


def test_rejects_label_series_before_expression_analysis() -> None:
    spec = equity_spec()
    inputs = spec["inputs"]
    assert isinstance(inputs, list)
    inputs[0]["data_type"] = "LabelSeries"

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_LABEL_SERIES_FORBIDDEN"
    assert error.diagnostics[0].path == "$.inputs[0].data_type"


def test_rejects_forward_fill_in_missing_policy() -> None:
    spec = equity_spec()
    spec["missing_policy"] = {"imputation": "forward_fill"}

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_FORWARD_FILL_FORBIDDEN"
    assert error.diagnostics[0].path == "$.missing_policy.imputation"


def test_compiles_closed_postprocess_pipeline_into_typed_plan() -> None:
    spec = equity_spec()
    spec["postprocess"] = {
        "steps": [
            {
                "op": "winsorize",
                "params": {"method": "mad", "limit": 3.0},
            },
            {"op": "zscore"},
            {"op": "cs_rank"},
        ]
    }

    compiled = compile_factor_ir(spec)

    assert compiled.output_type.kind is SeriesKind.CROSS_SECTION
    assert compiled.output_type.unit == "1"
    assert compiled.lookback == 20
    assert compiled.available_time == "T_CLOSE+20m"
    assert compiled.operator_names == (
        "cs_rank",
        "returns",
        "winsorize",
        "zscore",
    )
    assert compiled.postprocess_steps == (
        PostprocessStep(
            operator="winsorize",
            params=(("limit", 3.0), ("method", "mad")),
        ),
        PostprocessStep(operator="zscore", params=()),
        PostprocessStep(operator="cs_rank", params=()),
    )


@pytest.mark.parametrize(
    ("postprocess", "code", "path"),
    [
        (
            {"steps": [{"op": "neutralize"}]},
            "IR_UNSUPPORTED_POSTPROCESS_OPERATOR",
            "$.postprocess.steps[0].op",
        ),
        (
            {"steps": [{"op": "rolling_mean", "params": {"window": 20}}]},
            "IR_UNSUPPORTED_POSTPROCESS_OPERATOR",
            "$.postprocess.steps[0].op",
        ),
        (
            {"steps": [{"op": "zscore", "args": [{"ref": "close"}]}]},
            "IR_SCHEMA",
            "$.postprocess.steps[0].args",
        ),
        (
            {"steps": [{"op": "zscore", "params": {"axis": "time"}}]},
            "IR_UNKNOWN_PARAMETER",
            "$.postprocess.steps[0].params.axis",
        ),
        (
            {"steps": [], "exposure": {"ref": "industry"}},
            "IR_POSTPROCESS_EXPOSURE_UNSUPPORTED",
            "$.postprocess.exposure",
        ),
        (
            {"steps": [{"op": "neutralize", "exposure_ref": "industry"}]},
            "IR_POSTPROCESS_EXPOSURE_UNSUPPORTED",
            "$.postprocess.steps[0].exposure_ref",
        ),
    ],
)
def test_postprocess_fails_closed_for_unsupported_constructs(
    postprocess: dict[str, object],
    code: str,
    path: str,
) -> None:
    spec = equity_spec()
    spec["postprocess"] = postprocess

    error = compile_error(spec)

    assert error.diagnostics[0].code == code
    assert error.diagnostics[0].path == path


@pytest.mark.parametrize(
    ("params", "path"),
    [
        ({"method": "stddev", "limit": 3.0}, "$.postprocess.steps[0].params.method"),
        ({"method": "mad", "limit": 0}, "$.postprocess.steps[0].params.limit"),
    ],
)
def test_postprocess_validates_operator_semantics(
    params: dict[str, object],
    path: str,
) -> None:
    spec = equity_spec()
    spec["postprocess"] = {"steps": [{"op": "winsorize", "params": params}]}

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_INVALID_PARAMETER"
    assert error.diagnostics[0].path == path


def test_rejects_input_available_after_signal_time() -> None:
    spec = equity_spec()
    inputs = spec["inputs"]
    assert isinstance(inputs, list)
    inputs[0]["available_time_rule"] = "T_CLOSE+45m"

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_FUTURE_AVAILABLE_TIME"
    assert "T_CLOSE+45m" in error.diagnostics[0].message


def test_rejects_incompatible_units() -> None:
    spec = equity_spec()
    inputs = spec["inputs"]
    assert isinstance(inputs, list)
    inputs.append(
        {
            "alias": "volume",
            "field_ref": "market.eod.volume",
            "data_type": "ScalarSeries",
            "unit": "SHARE",
            "available_time_rule": "T_CLOSE+20m",
        }
    )
    spec["expression"] = {
        "op": "add",
        "args": [{"ref": "close"}, {"ref": "volume"}],
    }

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_UNIT_MISMATCH"


def test_rejects_undeclared_input_reference() -> None:
    spec = equity_spec()
    spec["expression"] = {"op": "abs", "args": [{"ref": "future_return"}]}

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_UNKNOWN_INPUT"


def test_rejects_unsupported_market_or_frequency() -> None:
    spec = equity_spec()
    market_scope = spec["market_scope"]
    assert isinstance(market_scope, dict)
    market_scope["market"] = "US_EQUITY"

    assert compile_error(spec).diagnostics[0].code == "IR_UNSUPPORTED_MARKET"

    spec = equity_spec()
    market_scope = spec["market_scope"]
    assert isinstance(market_scope, dict)
    market_scope["frequency"] = "1w"

    assert compile_error(spec).diagnostics[0].code == "IR_UNSUPPORTED_FREQUENCY"


def test_accepts_minute_frequency_with_bar_clock() -> None:
    spec = equity_spec()
    market_scope = spec["market_scope"]
    assert isinstance(market_scope, dict)
    market_scope["frequency"] = "5m"
    clock = spec["decision_clock"]
    assert isinstance(clock, dict)
    clock["signal_time"] = "T_BAR+1m"
    clock["earliest_trade_time"] = "T_BAR+2m"
    inputs = spec["inputs"]
    assert isinstance(inputs, list)
    first_input = inputs[0]
    assert isinstance(first_input, dict)
    first_input["available_time_rule"] = "T_BAR+1m"

    compiled = compile_factor_ir(spec)

    assert compiled.factor_id == "price.momentum_20d"


@pytest.mark.parametrize(
    "missing_field",
    ["exchange_scope", "contract_chain_ref", "roll_policy_ref"],
)
def test_futures_scope_requires_contract_context(missing_field: str) -> None:
    spec = equity_spec()
    spec["market_scope"] = {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "1d",
        "universe_ref": "universe://liquid-commodity-futures-pit",
        "exchange_scope": ["SHFE", "DCE"],
        "contract_chain_ref": "chain://commodity/main-pit/v1",
        "roll_policy_ref": "policy://roll/volume-no-future/v1",
    }
    market_scope = spec["market_scope"]
    assert isinstance(market_scope, dict)
    del market_scope[missing_field]

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_FUTURES_SCOPE_REQUIRED"
    assert error.diagnostics[0].path == f"$.market_scope.{missing_field}"


def test_futures_scope_rejects_unknown_exchange() -> None:
    spec = equity_spec()
    spec["market_scope"] = {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "1d",
        "universe_ref": "universe://liquid-commodity-futures-pit",
        "exchange_scope": ["CME"],
        "contract_chain_ref": "chain://commodity/main-pit/v1",
        "roll_policy_ref": "policy://roll/volume-no-future/v1",
    }

    error = compile_error(spec)

    assert error.diagnostics[0].code == "IR_INVALID_EXCHANGE_SCOPE"


def test_nested_lookback_and_available_time_propagate() -> None:
    spec = equity_spec()
    inputs = spec["inputs"]
    assert isinstance(inputs, list)
    inputs.append(
        {
            "alias": "volume",
            "field_ref": "market.eod.volume",
            "data_type": "ScalarSeries",
            "unit": "SHARE",
            "available_time_rule": "T_CLOSE+25m",
        }
    )
    spec["expression"] = {
        "op": "ts_corr",
        "args": [
            {
                "op": "returns",
                "args": [{"ref": "close"}],
                "params": {"periods": 1},
            },
            {
                "op": "returns",
                "args": [{"ref": "volume"}],
                "params": {"periods": 1},
            },
        ],
        "params": {"window": 20},
    }

    compiled = compile_factor_ir(spec)

    assert compiled.lookback == 20
    assert compiled.available_time == "T_CLOSE+25m"
    assert compiled.operator_names == ("returns", "ts_corr")
    assert compiled.output_type.unit == "1"


def test_compiler_does_not_mutate_caller_payload() -> None:
    spec = equity_spec()
    original = deepcopy(spec)

    compile_factor_ir(spec)

    assert spec == original


def test_rejects_zero_policy_clip_not_supported_by_executor() -> None:
    spec = equity_spec()
    spec["expression"] = {
        "op": "safe_div",
        "args": [{"ref": "close"}, {"ref": "close"}],
        "params": {"zero_policy": "clip"},
    }

    error = compile_error(spec)

    assert "zero_policy" in str(error)
