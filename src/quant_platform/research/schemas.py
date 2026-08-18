from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarketId(StrEnum):
    CN_A = "CN_A"
    CN_COMMODITY_FUTURES = "CN_COMMODITY_FUTURES"


Frequency = Literal["1d", "1m", "5m", "15m", "30m", "60m"]
FREQUENCIES: frozenset[str] = frozenset({"1d", "1m", "5m", "15m", "30m", "60m"})

EnvironmentId = Literal["RESEARCH", "PAPER", "LIVE"]


class ResearchJobState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class BriefDirection(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NON_MONOTONIC = "NON_MONOTONIC"
    UNKNOWN = "UNKNOWN"


class BriefStatus(StrEnum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"
    SUPERSEDED = "SUPERSEDED"


class Budget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_limit: int = Field(ge=1)
    llm_token_limit: int = Field(default=0, ge=0)
    cpu_hours: float = Field(default=0, ge=0)
    wall_clock_minutes: int = Field(ge=1)


class CommandMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3)
    parent_artifact_id: str | None
    budget: Budget
    schema_version: str


class BriefContent(BaseModel):
    hypothesis: str = Field(min_length=3)
    economic_mechanism: str = Field(min_length=3)
    expected_direction: BriefDirection
    falsification_conditions: list[str] = Field(min_length=1)
    allowed_data_domains: list[str]
    forbidden_data_domains: list[str] = Field(default_factory=list)
    constraints: list[str]
    evidence_ref_ids: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CreateResearchJobCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    market: MarketId
    environment: EnvironmentId = "RESEARCH"
    universe_ref: str
    frequency: Frequency
    decision_clock: str
    trade_clock: str
    settlement_clock: str | None = None
    exchange_scope: list[str] = Field(default_factory=list)
    contract_selection: Literal["ACTUAL_CONTRACTS_ONLY"] | None = None
    roll_policy: str | None = None
    horizon: str
    research_brief_version_id: str

    @model_validator(mode="after")
    def validate_market_fields(self) -> CreateResearchJobCommand:
        if self.market is MarketId.CN_COMMODITY_FUTURES:
            missing = [
                name
                for name, value in (
                    ("settlement_clock", self.settlement_clock),
                    ("exchange_scope", self.exchange_scope),
                    ("contract_selection", self.contract_selection),
                    ("roll_policy", self.roll_policy),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "commodity futures require " + ", ".join(sorted(missing))
                )
        return self


class CreateResearchBriefVersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CommandMetadata
    brief: BriefContent


class UpdateResearchBriefVersionCommand(CreateResearchBriefVersionCommand):
    pass


class ParsePaperCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_text: str = Field(min_length=50)
    market: MarketId


class ResearchJobRecord(BaseModel):
    id: str
    project_id: str
    resource_version: int
    title: str
    market: MarketId
    environment: EnvironmentId = "RESEARCH"
    state: ResearchJobState
    owner: str
    universe_ref: str
    frequency: Frequency
    decision_clock: str
    trade_clock: str
    settlement_clock: str | None
    exchange_scope: list[str]
    contract_selection: str | None
    roll_policy: str | None
    horizon: str
    research_brief_version_id: str
    budget: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ResearchBriefRecord(BriefContent):
    id: str
    job_id: str
    version: int
    resource_version: int
    status: BriefStatus
    content_hash: str | None
    created_at: datetime
    created_by: str
    frozen_at: datetime | None
    frozen_by: str | None


class CommandReceipt(BaseModel):
    command_id: str
    status: Literal["ACCEPTED"] = "ACCEPTED"
    resource_id: str
    submitted_at: datetime
