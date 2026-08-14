from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_platform.agent.contracts import (
    CandidateFactor,
    DataRequest,
    FalsificationTest,
    ResearchProposal,
    Uncertainty,
)
from quant_platform.agent.gateway import (
    AgentRole,
    AgentTrace,
    prompt_hash,
    require_structured_output,
)


def proposal() -> ResearchProposal:
    return ResearchProposal(
        job_id="job-1",
        hypothesis="Momentum persists in CN_A large caps.",
        mechanism="Underreaction to earnings news.",
        expected_sign="positive",
        candidate_factors=(
            CandidateFactor(
                factor_id="factor-1",
                economic_mechanism="momentum",
                inputs=("close_adjusted",),
                formula="returns(20d)",
                direction="positive",
                lookback_days=20,
            ),
        ),
        falsification_tests=(
            FalsificationTest(
                test_id="t1",
                description="reversed signal loses",
                expected_if_true="positive IC",
                expected_if_false="negative IC",
            ),
        ),
        data_requests=(
            DataRequest(dataset_id="market-eod", fields=("close_adjusted",)),
        ),
        evidence_refs=("paper://momentum-1993",),
        uncertainty=(Uncertainty(description="small sample", severity="medium"),),
    )


def trace() -> AgentTrace:
    return AgentTrace(
        trace_id="trace-1",
        role=AgentRole.HYPOTHESIS,
        provider="deepseek",
        model="deepseek-v4",
        prompt="propose momentum factors",
        temperature=0.0,
        token_count=120,
        tools=("catalog",),
        corpus_refs=("corpus://papers",),
        created_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
    )


def test_proposal_content_hash_is_stable() -> None:
    assert proposal().content_hash() == proposal().content_hash()


def test_proposal_rejects_duplicate_factor_ids() -> None:
    factor = CandidateFactor(
        factor_id="dup",
        economic_mechanism="m",
        inputs=("x",),
        formula="f",
        direction="positive",
        lookback_days=5,
    )
    with pytest.raises(ValueError):
        ResearchProposal(
            job_id="j",
            hypothesis="h",
            mechanism="m",
            expected_sign="positive",
            candidate_factors=(factor, factor),
            falsification_tests=(),
            data_requests=(),
            evidence_refs=(),
            uncertainty=(),
        )


def test_trace_prompt_hash_is_deterministic() -> None:
    assert prompt_hash("hello") == prompt_hash("hello")
    assert prompt_hash("hello") != prompt_hash("world")


def test_trace_rejects_bad_temperature() -> None:
    with pytest.raises(ValueError):
        AgentTrace(
            trace_id="t",
            role=AgentRole.CRITIC,
            provider="p",
            model="m",
            prompt="x",
            temperature=3.0,
            token_count=0,
            tools=(),
            corpus_refs=(),
            created_at=datetime(2026, 8, 14, tzinfo=UTC),
        )


def test_require_structured_output_accepts_proposal() -> None:
    require_structured_output(proposal())


def test_require_structured_output_rejects_plain_value() -> None:
    with pytest.raises(TypeError):
        require_structured_output("plain string")


def test_require_structured_output_rejects_none() -> None:
    with pytest.raises(ValueError):
        require_structured_output(None)
