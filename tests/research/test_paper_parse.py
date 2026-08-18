"""Tests for the paper-to-brief parser (LLM output is mocked)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from quant_platform.research.paper_parse import (
    PaperParseError,
    _extract_json,
    parse_paper_to_brief,
)
from quant_platform.research.schemas import BriefDirection

_VALID_BRIEF = {
    "hypothesis": "过去 5 日上涨的股票未来 5 日继续上涨。",
    "economic_mechanism": "趋势追随资金推动价格惯性。",
    "expected_direction": "POSITIVE",
    "falsification_conditions": ["未来 5 日收益与过去 5 日收益的秩相关不显著为正。"],
    "allowed_data_domains": ["formal.market.eod"],
    "forbidden_data_domains": [],
    "constraints": ["仅覆盖主板股票"],
    "evidence_ref_ids": [],
    "uncertainties": ["震荡市中动量可能失效"],
}


def _complete_ok(_text: str, _hint: str | None) -> str:
    return json.dumps(_VALID_BRIEF, ensure_ascii=False)


def test_extract_json_plain() -> None:
    data = _extract_json(json.dumps(_VALID_BRIEF))
    assert data["hypothesis"].startswith("过去 5 日")


def test_extract_json_markdown_fence() -> None:
    data = _extract_json(f"```json\n{json.dumps(_VALID_BRIEF)}\n```")
    assert data["expected_direction"] == "POSITIVE"


def test_extract_json_rejects_non_object() -> None:
    with pytest.raises(PaperParseError):
        _extract_json("[1, 2, 3]")


def test_extract_json_rejects_invalid() -> None:
    with pytest.raises(PaperParseError):
        _extract_json("not json at all")


def test_parse_paper_to_brief_success() -> None:
    brief = parse_paper_to_brief("some paper text", complete=_complete_ok)
    assert brief.hypothesis.startswith("过去 5 日")
    assert brief.expected_direction is BriefDirection.POSITIVE
    assert brief.falsification_conditions


def test_parse_paper_to_brief_retries_on_invalid() -> None:
    calls: list[str | None] = []

    def flaky(_text: str, hint: str | None) -> str:
        calls.append(hint)
        if hint is None:
            return '{"not": "the schema"}'
        return json.dumps(_VALID_BRIEF, ensure_ascii=False)

    brief = parse_paper_to_brief("paper", complete=flaky)
    assert brief.expected_direction is BriefDirection.POSITIVE
    assert len(calls) == 2
    assert calls[1] is not None


def test_parse_paper_to_brief_raises_after_retry() -> None:
    def always_bad(_text: str, _hint: str | None) -> str:
        return '{"wrong": "shape"}'

    with pytest.raises(ValidationError):
        parse_paper_to_brief("paper", complete=always_bad)
