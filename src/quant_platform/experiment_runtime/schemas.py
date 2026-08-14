from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.research.schemas import CommandMetadata


class ResourceBudgetCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_seconds: int = Field(gt=0)
    wall_clock_seconds: int = Field(gt=0)
    memory_mb: int = Field(gt=0)
    max_observations: int = Field(gt=0)


class PreregisterExperimentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    research_job_id: str
    brief_version_id: str
    decision_time: datetime
    random_seed: int
    resource_budget: ResourceBudgetCommand
    factor_ir: dict[str, Any]
    snapshot_id: str
    snapshot_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunExperimentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata


class ValidateExperimentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    policy_id: str
    label_snapshot_id: str
    label_snapshot_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AssessRobustnessCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    policy_id: str
    label_snapshot_id: str
    label_snapshot_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    n_shuffles: int = Field(default=20, gt=0)
    seed: int = Field(default=0, ge=0)


class AssessIndependenceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    policy_id: str
    label_snapshot_id: str
    label_snapshot_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    pool_run_ids: tuple[str, ...] = ()


class CandidateEvidenceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage: float | None
    observations: int | None
    oos_ic: float | None
    expected_direction: str
    fdr_qvalue: float | None
    capacity_aum: float | None
    sharpe: float | None
    effect_score: float | None
    stability_score: float | None
    independence_score: float | None
    cost_value_score: float | None
    interpretability_score: float | None


class PromoteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    policy_id: str
    direction: str
    universe: str
    horizon: int = Field(gt=0)
    risk_premium: bool = False
    evidence: CandidateEvidenceCommand


class SignApprovalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=1)
