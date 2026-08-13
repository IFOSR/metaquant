from __future__ import annotations

from datetime import datetime
from typing import Any

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


class LabelObservationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    event_time: datetime
    value: float | None


class LabelCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_id: str
    market: str
    horizon: int
    field_ref: str
    return_definition: str = "close_to_close"
    observations: list[LabelObservationCommand] = Field(min_length=1)


class ValidateExperimentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    policy_id: str
    label: LabelCommand
    label_available_time: datetime
