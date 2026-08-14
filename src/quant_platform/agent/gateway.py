"""Agent trace and gateway contracts (G12-002).

Every Agent invocation records an immutable ``AgentTrace`` (role, provider,
model, prompt hash, temperature, token count, tools, corpus refs) so research
outputs can be audited back to the exact model and prompt that produced them.
The ``AgentGateway`` is a structural boundary: it only returns structured
outputs and never exposes write access to the deterministic kernel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from quant_platform.agent.contracts import ResearchProposal
from quant_platform.experiments import canonical_hash

_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a non-empty normalized identifier")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(ch not in _HEX_DIGITS for ch in value):
        raise ValueError(f"{name} must be a 64-character hex digest")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class AgentRole(StrEnum):
    INTAKE = "INTAKE"
    HYPOTHESIS = "HYPOTHESIS"
    CRITIC = "CRITIC"
    PAPER = "PAPER"
    FORMULA = "FORMULA"
    MAPPING = "MAPPING"
    RESULT_ANALYST = "RESULT_ANALYST"
    REPORT = "REPORT"


def prompt_hash(prompt: str) -> str:
    if not prompt:
        raise ValueError("prompt must not be empty")
    return hashlib.sha256(prompt.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentTrace:
    trace_id: str
    role: AgentRole
    provider: str
    model: str
    prompt: str
    temperature: float
    token_count: int
    tools: tuple[str, ...]
    corpus_refs: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.trace_id, "trace_id")
        if not isinstance(self.role, AgentRole):
            object.__setattr__(self, "role", AgentRole(self.role))
        _require_identifier(self.provider, "provider")
        _require_identifier(self.model, "model")
        if not self.prompt:
            raise ValueError("prompt must not be empty")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be within [0, 2]")
        if self.token_count < 0:
            raise ValueError("token_count must be non-negative")
        _require_aware(self.created_at, "created_at")

    def prompt_hash_value(self) -> str:
        return prompt_hash(self.prompt)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "agent-trace/v1",
            "trace_id": self.trace_id,
            "role": self.role.value,
            "provider": self.provider,
            "model": self.model,
            "prompt_hash": self.prompt_hash_value(),
            "temperature": self.temperature,
            "token_count": self.token_count,
            "tools": list(self.tools),
            "corpus_refs": list(self.corpus_refs),
            "created_at": self.created_at.isoformat(),
        }

    def content_hash(self) -> str:
        return canonical_hash(self.payload())


class AgentGateway(Protocol):
    """Structural boundary between the Agent layer and the deterministic kernel.

    Returns only structured outputs; never exposes write access to the kernel,
    PostgreSQL, GateDecision, the Alpha Pool, or StrategyPackage.
    """

    def propose(
        self, *, role: AgentRole, brief: str, trace: AgentTrace
    ) -> ResearchProposal: ...

    def critique(
        self, *, proposal: ResearchProposal, trace: AgentTrace
    ) -> tuple[str, ...]: ...


def require_structured_output(value: object) -> None:
    """Guard: Agent output must be a structured, content-addressable value."""
    if value is None:
        raise ValueError("agent output must not be None")
    if not hasattr(value, "content_hash"):
        raise TypeError("agent output must be a structured, content-addressable value")
