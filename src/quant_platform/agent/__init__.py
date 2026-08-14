"""Research Agent layer (G12)."""

from quant_platform.agent.contracts import (
    CandidateFactor,
    DataRequest,
    FalsificationTest,
    ResearchProposal,
    Uncertainty,
)
from quant_platform.agent.gateway import (
    AgentGateway,
    AgentRole,
    AgentTrace,
    prompt_hash,
    require_structured_output,
)

__all__ = [
    "AgentGateway",
    "AgentRole",
    "AgentTrace",
    "CandidateFactor",
    "DataRequest",
    "FalsificationTest",
    "ResearchProposal",
    "Uncertainty",
    "prompt_hash",
    "require_structured_output",
]
