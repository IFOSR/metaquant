"""Factor build spec (build-spec/v1).

The agent's first-stage artifact: an auditable, non-executable "research intent"
that describes *how* to build a deep-learning factor (features, label,
architecture, style neutralization, sample weighting) rather than a closed-form
factor formula.  It is the input to code generation and the audit trail for the
whole 研报 -> 规格 -> 代码 -> 权重 -> 因子值 lineage.

Canonical hashing follows the research brief convention (``sha256:<hex>``) so
the spec can be content-addressed and frozen.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Architecture(StrEnum):
    MLP = "MLP"
    LSTM = "LSTM"
    TRANSFORMER = "TRANSFORMER"
    LINEAR = "LINEAR"


class SampleWeighting(StrEnum):
    EQUAL = "EQUAL"
    INVERSE_SIZE = "INVERSE_SIZE"
    CAP_WEIGHTED = "CAP_WEIGHTED"


class LabelSpec(BaseModel):
    """Training label definition.

    ``style_neutralize`` captures the StableAlpha insight: the raw forward return
    label is polluted by style exposures (size/volatility/reversal/liquidity), so
    the label is residualized against those styles *before* training, forcing the
    model to predict pure alpha instead of a style shortcut.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    price_field: str = Field(min_length=1)
    horizon: int = Field(ge=1)
    return_type: str = "simple"
    style_neutralize: list[str] = Field(default_factory=list)


class FactorBuildSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_version: str = "build-spec/v1"
    factor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.]*$")
    factor_name: str = Field(min_length=1)
    market: str = Field(min_length=1)
    universe_ref: str = Field(min_length=1)
    frequency: str = "1d"
    inputs: list[str] = Field(min_length=1)
    label: LabelSpec
    architecture: Architecture
    style_neutralize: list[str] = Field(default_factory=list)
    sample_weighting: SampleWeighting = SampleWeighting.EQUAL
    expected_direction: str = "POSITIVE"
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    brief: dict[str, Any] = Field(default_factory=dict)
    evidence_ref_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _label_field_in_inputs(self) -> FactorBuildSpec:
        if self.label.price_field not in self.inputs:
            raise ValueError("label.price_field must be in inputs")
        return self


def build_spec_hash(spec: FactorBuildSpec) -> str:
    canonical = json.dumps(
        spec.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
