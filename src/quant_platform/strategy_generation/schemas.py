"""Schema contracts for natural-language strategy drafting (G19-P1).

A strategy draft is a multi-turn conversation between a user and the agent that
converges on (1) an executable NautilusTrader Python strategy and (2) a plain
language explanation. The agent is an amplifier, not an authority: it proposes
code + explanation, the user confirms and freezes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.research.schemas import MarketId


class StrategyDraftState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    FROZEN = "FROZEN"


# 研究形态：因子与策略同为「研究」，由对话自然判定（可被对话改写）。
ResearchKind = Literal["factor", "strategy"]

# 研究生命周期（任意步骤可保存；由证据字段派生，见 api._research_stage）。
ResearchStage = Literal[
    "CREATING", "READY", "CODE_TESTED", "BACKTESTED", "PAPER_LINKED"
]


Role = Literal["user", "assistant"]

Frequency = Literal["1d", "1w", "5m", "15m", "30m", "60m"]
FREQUENCY_SET = frozenset({"1d", "1w", "5m", "15m", "30m", "60m"})


class StrategyMessage(BaseModel):
    """One conversation message (user text or agent's human-facing reply)."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    content: str = Field(min_length=1)


class Attachment(BaseModel):
    """对话附件：文本直接抽取内容；图片记录引用（视觉/OCR 见抽取器降级）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: Literal["text", "image"] = "text"
    extracted_text: str = Field(default="")
    object_key: str = Field(default="")


class BacktestPlan(BaseModel):
    """Agent 建议的回测方案：周期、时间段与理由。"""

    model_config = ConfigDict(extra="forbid")

    timeframes: list[str] = Field(min_length=1)
    trend_timeframe: str | None = None
    exec_timeframe: str
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    rationale: str = Field(default="")


class AgentOutput(BaseModel):
    """Structured output the agent produces on each turn."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="")
    explanation: str = Field(min_length=1)
    question: str = Field(default="")
    code: str | None = None
    ready: bool = False
    instrument_ids: list[str] = Field(default_factory=list)
    frequency: Frequency = "1d"
    backtest_plan: BacktestPlan | None = None
    kind: ResearchKind = "strategy"


class CreateStrategyDraftCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: MarketId
    first_message: str = Field(min_length=3)
    attachments: list[Attachment] = Field(default_factory=list)


class PostStrategyMessageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    attachments: list[Attachment] = Field(default_factory=list)


class StrategyDraftRecord(BaseModel):
    """Public snapshot of a strategy draft."""

    id: str
    market: MarketId
    state: StrategyDraftState
    title: str
    explanation: str
    question: str
    code: str | None
    ready: bool
    instrument_ids: list[str]
    frequency: str
    backtest_plan: dict[str, Any] | None
    resource_version: int
    created_at: datetime
    updated_at: datetime
