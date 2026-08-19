"""API schemas for the factor construction control plane."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.factor_construction.spec import FactorBuildSpec
from quant_platform.research.schemas import CommandMetadata


class FactorBuildSpecState(StrEnum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"


class FactorBuildSpecRecord(BaseModel):
    id: str
    project_id: str
    research_job_id: str | None
    brief_version_id: str | None
    spec_hash: str
    spec: FactorBuildSpec
    state: FactorBuildSpecState
    resource_version: int
    created_at: datetime
    created_by: str
    frozen_at: datetime | None
    frozen_by: str | None


class FactorCodeBundleRecord(BaseModel):
    id: str
    spec_hash: str
    bundle_hash: str
    manifest: dict[str, Any]
    created_at: datetime
    created_by: str


class CreateFactorBuildSpecCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    spec: FactorBuildSpec


class FreezeFactorBuildSpecCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata


class GenerateCodeBundleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    spec_hash: str
    bundle_hash: str
    manifest: dict[str, Any]


class ExtractBuildSpecCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_text: str = Field(min_length=20)
    market: str = Field(min_length=1)
    user_prompt: str | None = None


class GenerateCodeDraftCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: FactorBuildSpec
