"""Tests for factor extraction (agent output is mocked)."""

from __future__ import annotations

import json

import pytest

from quant_platform.research.factor_extract import (
    FactorExtractionError,
    _build_factor_ir,
    _extract_json,
    _normalize_expression,
    extract_factor_from_paper,
)
from quant_platform.research.schemas import BriefDirection

_VALID = {
    "factor_id": "classic.cn_a.momentum_5d",
    "factor_name": "5日动量",
    "inputs": [
        {
            "alias": "close",
            "field_ref": "market.eod.close",
            "available_time_rule": "T_CLOSE+20m",
        }
    ],
    "expression": {
        "op": "returns",
        "args": [{"ref": "close"}],
        "params": {"periods": 5},
    },
    "brief": {
        "hypothesis": "过去 5 日上涨的股票未来 5 日继续上涨。",
        "economic_mechanism": "趋势追随资金推动价格惯性。",
        "expected_direction": "POSITIVE",
        "falsification_conditions": ["未来 5 日收益与过去 5 日收益秩相关不显著为正。"],
        "allowed_data_domains": ["formal.market.eod"],
        "forbidden_data_domains": [],
        "constraints": ["仅主板股票"],
        "evidence_ref_ids": [],
        "uncertainties": ["震荡市中动量可能失效"],
    },
    "explanation": "过去 5 日累计收益作为动量因子。",
}


def _complete_ok(_prompt: str) -> str:
    return json.dumps(_VALID, ensure_ascii=False)


def test_build_factor_ir_fills_market_scaffold() -> None:
    ir = _build_factor_ir(_VALID, "CN_COMMODITY_FUTURES")
    assert ir["factor_id"] == "classic.cn_a.momentum_5d"
    assert ir["schema_version"] == "factor-ir/v1"
    scope = ir["market_scope"]
    assert scope["market"] == "CN_COMMODITY_FUTURES"
    assert scope["universe_ref"] == "futures:liquid-initial"
    assert scope["contract_chain_ref"] == "chain://shfe-rb/v1"
    assert ir["validation_policy_ref"] == "policy://cn-futures-daily-factor/v1"
    assert ir["decision_clock"]["signal_time"] == "T_CLOSE+30m"


def test_build_factor_ir_rejects_bad_field_ref() -> None:
    bad = dict(_VALID)
    bad["inputs"] = [{"alias": "x", "field_ref": "illegal.field"}]
    with pytest.raises(FactorExtractionError):
        _build_factor_ir(bad, "CN_A")


def test_extract_factor_from_paper() -> None:
    result = extract_factor_from_paper(
        "some report", "CN_A", runner=_complete_ok
    )
    assert result.brief.expected_direction is BriefDirection.POSITIVE
    assert result.factor_ir["market_scope"]["market"] == "CN_A"
    assert result.explanation


def test_extract_factor_retries_on_invalid() -> None:
    calls: list[str] = []

    def flaky(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return '{"not": "valid"}'
        return json.dumps(_VALID, ensure_ascii=False)

    result = extract_factor_from_paper("report", "CN_A", runner=flaky)
    assert result.brief.expected_direction is BriefDirection.POSITIVE
    assert len(calls) == 2


def test_extract_json_markdown_fence() -> None:
    data = _extract_json(f"```json\n{json.dumps(_VALID)}\n```")
    assert data["factor_id"] == "classic.cn_a.momentum_5d"


def test_normalize_expression_returns_window_to_periods() -> None:
    expr = _normalize_expression(
        {"op": "returns", "args": [{"ref": "close"}], "params": {"window": 5}}
    )
    assert expr["params"] == {"periods": 5}


def test_extract_json_rejects_non_object() -> None:
    with pytest.raises(FactorExtractionError):
        _extract_json("[1, 2, 3]")
