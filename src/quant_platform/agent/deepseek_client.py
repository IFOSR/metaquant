"""DeepSeek non-interactive Agent client (G16-010, FR-005/006).

Runs the ``deepseek`` CLI in non-interactive mode (``deepseek -p``) to produce
structured Agent outputs. The gateway only returns content-addressed,
validated objects; it never exposes write access to the deterministic kernel.
A hard token budget is enforced across invocations (FR-006).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

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
    require_structured_output,
)

Runner = Callable[[str], str]


class DeepSeekRunner:
    """Invoke the ``deepseek`` CLI in non-interactive mode."""

    def __init__(self, timeout_seconds: int = 120) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def run(self, prompt: str) -> str:
        result = subprocess.run(
            ["deepseek", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"deepseek exited {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout.strip()


class BudgetExceededError(RuntimeError):
    """Raised when the agent token budget is exhausted (FR-006)."""


@dataclass
class DeepSeekAgentGateway:
    """Agent gateway backed by the non-interactive DeepSeek CLI."""

    runner: Runner
    model: str = "deepseek-v4-pro"
    provider: str = "deepseek"
    temperature: float = 0.0
    max_tokens: int = 100_000

    _consumed_tokens: int = 0

    def _complete(self, prompt: str) -> str:
        response = self.runner(prompt)
        self._consumed_tokens += max(1, len(prompt) // 4 + len(response) // 4)
        if self._consumed_tokens > self.max_tokens:
            raise BudgetExceededError("agent token budget exceeded")
        return response

    def propose(
        self, *, role: AgentRole, brief: str, trace: AgentTrace
    ) -> ResearchProposal:
        prompt = _proposal_prompt(role, brief)
        raw = self._complete(prompt)
        data = _parse_json(raw)
        proposal = _proposal_from_payload(data)
        require_structured_output(proposal)
        return proposal

    def critique(
        self, *, proposal: ResearchProposal, trace: AgentTrace
    ) -> tuple[str, ...]:
        prompt = _critique_prompt(proposal)
        raw = self._complete(prompt)
        data = _parse_json(raw)
        criticisms = data.get("criticisms")
        if not isinstance(criticisms, list) or not all(
            isinstance(item, str) and item for item in criticisms
        ):
            raise ValueError("critique output must be a list of non-empty strings")
        return tuple(criticisms)

    def extract_paper_claims(self, page_text: str) -> tuple[dict[str, object], ...]:
        """Extract page-locatable claims from a paper page (PAPER role)."""
        prompt = _paper_prompt(page_text)
        raw = self._complete(prompt)
        data = _parse_json(raw)
        claims = data.get("claims")
        if not isinstance(claims, list):
            raise ValueError("paper output must contain a claims list")
        return tuple(item for item in claims if isinstance(item, dict))


def _parse_json(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("agent output is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("agent output must be a JSON object")
    return data


def _proposal_prompt(role: AgentRole, brief: str) -> str:
    return (
        f"Role: {role.value}. You are a quantitative research agent. "
        "Propose candidate factors for the research brief below. "
        "Respond with ONLY a JSON object matching: "
        '{"job_id": "...", "hypothesis": "...", "mechanism": "...", '
        '"expected_sign": "positive|negative|unknown", '
        '"candidate_factors": [{"factor_id": "...", "economic_mechanism": "...", '
        '"inputs": ["..."], "formula": "...", "direction": '
        '"positive|negative|unknown", '
        '"lookback_days": 20}], "falsification_tests": [{"test_id": "...", '
        '"description": "...", "expected_if_true": "...", '
        '"expected_if_false": "..."}], '
        '"data_requests": [{"dataset_id": "...", "fields": ["..."]}], '
        '"evidence_refs": ["..."], "uncertainty": [{"description": "...", '
        '"severity": "low|medium|high"}]}. '
        f"Brief: {brief}"
    )


def _critique_prompt(proposal: ResearchProposal) -> str:
    return (
        "You are a critical quantitative researcher. Review the proposal and "
        "list concrete falsification risks and data pitfalls. Respond with ONLY "
        'a JSON object of the form {"criticisms": ["...", "..."]}. '
        f"Proposal: {json.dumps(proposal.payload(), ensure_ascii=False)}"
    )


def _paper_prompt(page_text: str) -> str:
    return (
        "Extract page-locatable claims from this paper page. Respond with ONLY "
        'a JSON object of the form {"claims": [{"page": 1, "claim": "...", '
        '"formula": "...", "variables": {"x": "..."}}]}. '
        f"Page text: {page_text[:8000]}"
    )


def _proposal_from_payload(data: dict[str, object]) -> ResearchProposal:
    job_id = _str_field(data, "job_id")
    hypothesis = _str_field(data, "hypothesis")
    mechanism = _str_field(data, "mechanism")
    expected_sign = _str_field(data, "expected_sign")
    candidate_factors = tuple(
        CandidateFactor(
            factor_id=_str_field(item, "factor_id"),
            economic_mechanism=_str_field(item, "economic_mechanism"),
            inputs=tuple(_str_list(item, "inputs")),
            formula=_str_field(item, "formula"),
            direction=_str_field(item, "direction"),
            lookback_days=_int_field(item, "lookback_days"),
        )
        for item in _dict_list(data, "candidate_factors")
    )
    falsification_tests = tuple(
        FalsificationTest(
            test_id=_str_field(item, "test_id"),
            description=_str_field(item, "description"),
            expected_if_true=_str_field(item, "expected_if_true"),
            expected_if_false=_str_field(item, "expected_if_false"),
        )
        for item in _dict_list(data, "falsification_tests")
    )
    data_requests = tuple(
        DataRequest(
            dataset_id=_str_field(item, "dataset_id"),
            fields=tuple(_str_list(item, "fields")),
        )
        for item in _dict_list(data, "data_requests")
    )
    uncertainty = tuple(
        Uncertainty(
            description=_str_field(item, "description"),
            severity=_str_field(item, "severity"),
        )
        for item in _dict_list(data, "uncertainty")
    )
    return ResearchProposal(
        job_id=job_id,
        hypothesis=hypothesis,
        mechanism=mechanism,
        expected_sign=expected_sign,
        candidate_factors=candidate_factors,
        falsification_tests=falsification_tests,
        data_requests=data_requests,
        evidence_refs=tuple(_str_list(data, "evidence_refs")),
        uncertainty=uncertainty,
    )


def _dict_list(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _str_list(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _str_field(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _int_field(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


class TraceFactory(Protocol):
    def __call__(self, *, role: AgentRole, prompt: str) -> AgentTrace: ...


def default_trace_factory(now: datetime) -> TraceFactory:
    def build(*, role: AgentRole, prompt: str) -> AgentTrace:
        return AgentTrace(
            trace_id=f"trace_{now.timestamp()}",
            role=role,
            provider="deepseek",
            model="deepseek-v4-pro",
            prompt=prompt,
            temperature=0.0,
            token_count=0,
            tools=(),
            corpus_refs=(),
            created_at=now,
        )

    return build
