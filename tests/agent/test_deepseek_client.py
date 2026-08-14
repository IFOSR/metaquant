from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from quant_platform.agent.contracts import ResearchProposal
from quant_platform.agent.deepseek_client import (
    BudgetExceededError,
    DeepSeekAgentGateway,
)
from quant_platform.agent.gateway import AgentRole, AgentTrace


def trace() -> AgentTrace:
    return AgentTrace(
        trace_id="trace_1",
        role=AgentRole.HYPOTHESIS,
        provider="deepseek",
        model="deepseek-v4-pro",
        prompt="test",
        temperature=0.0,
        token_count=0,
        tools=(),
        corpus_refs=(),
        created_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )


def proposal_json() -> dict[str, object]:
    return {
        "job_id": "job_1",
        "hypothesis": "medium-term momentum persists",
        "mechanism": "slow information diffusion",
        "expected_sign": "positive",
        "candidate_factors": [
            {
                "factor_id": "momentum_20d",
                "economic_mechanism": "underreaction",
                "inputs": ["market.eod.close"],
                "formula": "returns(close, 20)",
                "direction": "positive",
                "lookback_days": 20,
            }
        ],
        "falsification_tests": [
            {
                "test_id": "ft_1",
                "description": "reversal dominates",
                "expected_if_true": "short-term IC positive",
                "expected_if_false": "short-term IC negative",
            }
        ],
        "data_requests": [{"dataset_id": "market-eod", "fields": ["market.eod.close"]}],
        "evidence_refs": ["evidence://momentum/1"],
        "uncertainty": [
            {"description": "corporate action timing", "severity": "medium"}
        ],
    }


def gateway(responses: list[str], max_tokens: int = 100_000) -> DeepSeekAgentGateway:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return DeepSeekAgentGateway(runner=runner, max_tokens=max_tokens)


def test_propose_returns_structured_proposal() -> None:
    g = gateway([json.dumps(proposal_json())])

    proposal = g.propose(role=AgentRole.HYPOTHESIS, brief="brief", trace=trace())

    assert isinstance(proposal, ResearchProposal)
    assert proposal.job_id == "job_1"
    assert proposal.candidate_factors[0].factor_id == "momentum_20d"
    assert proposal.content_hash()


def test_critique_returns_criticisms() -> None:
    proposal_gateway = gateway([json.dumps(proposal_json())])
    proposal = proposal_gateway.propose(
        role=AgentRole.HYPOTHESIS, brief="b", trace=trace()
    )

    critique_gateway = gateway(
        [json.dumps({"criticisms": ["data snooping", "survivorship bias"]})]
    )
    criticisms = critique_gateway.critique(proposal=proposal, trace=trace())

    assert criticisms == (
        "data snooping",
        "survivorship bias",
    )


def test_extract_paper_claims() -> None:
    g = gateway(
        [
            json.dumps(
                {"claims": [{"page": 1, "claim": "momentum works", "formula": "r"}]}
            )
        ]
    )

    claims = g.extract_paper_claims("page text")

    assert claims == ({"page": 1, "claim": "momentum works", "formula": "r"},)


def test_rejects_non_json_output() -> None:
    g = gateway(["this is not json"])

    with pytest.raises(ValueError, match="JSON"):
        g.propose(role=AgentRole.HYPOTHESIS, brief="b", trace=trace())


def test_rejects_invalid_proposal_structure() -> None:
    g = gateway([json.dumps({"job_id": "", "hypothesis": "h"})])

    with pytest.raises(ValueError):
        g.propose(role=AgentRole.HYPOTHESIS, brief="b", trace=trace())


def test_budget_is_enforced() -> None:
    g = gateway([json.dumps(proposal_json())] * 100, max_tokens=10)

    with pytest.raises(BudgetExceededError):
        for _ in range(50):
            g.propose(role=AgentRole.HYPOTHESIS, brief="b" * 100, trace=trace())


def test_parse_json_strips_fences() -> None:
    g = gateway([f"```json\n{json.dumps(proposal_json())}\n```"])

    proposal = g.propose(role=AgentRole.HYPOTHESIS, brief="b", trace=trace())

    assert proposal.job_id == "job_1"
