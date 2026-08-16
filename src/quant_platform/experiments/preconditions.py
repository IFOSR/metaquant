from __future__ import annotations

import json
from dataclasses import dataclass

from quant_platform.data_gateway import (
    ArtifactClass,
    FrozenSnapshot,
    QueryPurpose,
)
from quant_platform.experiments.contracts import (
    ExperimentSpec,
    ExperimentSpecState,
)
from quant_platform.factor_ir import CompiledFactorIR
from quant_platform.research.schemas import (
    FREQUENCIES,
    BriefStatus,
    ResearchBriefRecord,
    ResearchJobRecord,
)


@dataclass(frozen=True, slots=True)
class FormalSnapshotBinding:
    snapshot_id: str
    snapshot_manifest_hash: str
    sealed: bool
    artifact_class: ArtifactClass
    market: str
    universe_ref: str
    frequency: str
    decision_clock: str
    trade_clock: str
    settlement_clock: str | None
    exchange_scope: tuple[str, ...]
    contract_chain_ref: str | None
    roll_policy_ref: str | None
    purpose: QueryPurpose
    allowed_license_tags: frozenset[str]


@dataclass(frozen=True, slots=True)
class PreconditionViolation:
    code: str
    detail: str


class FormalPreconditionError(ValueError):
    def __init__(self, violations: tuple[PreconditionViolation, ...]) -> None:
        self.violations = violations
        super().__init__(
            "; ".join(f"{item.code}: {item.detail}" for item in violations)
        )


@dataclass(frozen=True, slots=True)
class FormalExecutionBinding:
    experiment_id: str
    market: str
    universe_ref: str
    frequency: str
    snapshot_id: str
    snapshot_manifest_hash: str
    factor_ir_hash: str


def validate_formal_preconditions(
    *,
    spec: ExperimentSpec,
    research_job: ResearchJobRecord,
    research_brief: ResearchBriefRecord,
    frozen_snapshot: FrozenSnapshot,
    snapshot_binding: FormalSnapshotBinding,
    compiled_ir: CompiledFactorIR,
) -> FormalExecutionBinding:
    violations: list[PreconditionViolation] = []

    def require(condition: bool, code: str, detail: str) -> None:
        if not condition:
            violations.append(PreconditionViolation(code, detail))

    ir = json.loads(compiled_ir.canonical_json)
    scope = ir["market_scope"]
    clocks = ir["decision_clock"]
    policy = ir["validation_policy_ref"]
    input_fields = {item["field_ref"] for item in ir["inputs"]}

    require(
        spec.state is ExperimentSpecState.PREREGISTERED,
        "SPEC_NOT_PREREGISTERED",
        "ExperimentSpec must be preregistered",
    )
    require(
        spec.project_id == "local", "PROJECT_NOT_FORMAL", "v1 formal project is local"
    )
    require(
        research_job.environment == "RESEARCH",
        "ENVIRONMENT_NOT_RESEARCH",
        "formal execution is research-only",
    )
    require(
        research_job.id == spec.research_job_id,
        "JOB_ID_MISMATCH",
        "spec and job differ",
    )
    require(
        research_brief.status is BriefStatus.FROZEN,
        "BRIEF_NOT_FROZEN",
        "brief must be frozen",
    )
    require(
        research_brief.id == spec.brief_version_id,
        "BRIEF_ID_MISMATCH",
        "brief identity differs",
    )
    require(
        _digest(research_brief.content_hash) == spec.brief_content_hash,
        "BRIEF_HASH_MISMATCH",
        "brief hash differs",
    )
    require(
        "latest" not in snapshot_binding.snapshot_id.lower(),
        "SNAPSHOT_NOT_EXPLICIT",
        "latest is forbidden",
    )
    require(snapshot_binding.sealed, "SNAPSHOT_NOT_SEALED", "snapshot must be sealed")
    require(
        snapshot_binding.artifact_class is ArtifactClass.FORMAL,
        "SNAPSHOT_NOT_FORMAL",
        "binding is not formal",
    )
    require(
        frozen_snapshot.artifact_class is ArtifactClass.FORMAL,
        "SNAPSHOT_NOT_FORMAL",
        "snapshot is not formal",
    )
    require(
        spec.snapshot_id == snapshot_binding.snapshot_id == frozen_snapshot.snapshot_id,
        "SNAPSHOT_ID_MISMATCH",
        "snapshot identities differ",
    )
    require(
        spec.snapshot_manifest_hash == snapshot_binding.snapshot_manifest_hash,
        "SNAPSHOT_MANIFEST_HASH_MISMATCH",
        "snapshot manifest differs",
    )
    require(
        spec.factor_ir_hash == compiled_ir.ir_hash,
        "FACTOR_IR_HASH_MISMATCH",
        "compiled IR hash differs",
    )

    identities = (
        (
            spec.market,
            research_job.market.value,
            snapshot_binding.market,
            scope["market"],
        ),
        (
            spec.universe_ref,
            research_job.universe_ref,
            snapshot_binding.universe_ref,
            scope["universe_ref"],
        ),
    )
    require(len(set(identities[0])) == 1, "MARKET_MISMATCH", "market identities differ")
    require(
        len(set(identities[1])) == 1, "UNIVERSE_MISMATCH", "universe identities differ"
    )
    require(
        spec.frequency
        == research_job.frequency
        == snapshot_binding.frequency
        == scope["frequency"],
        "FREQUENCY_MISMATCH",
        "frequency identities differ",
    )
    require(
        spec.frequency in FREQUENCIES,
        "FREQUENCY_NOT_SUPPORTED",
        "frequency must be one of 1d/1m/5m/15m/30m/60m",
    )
    if scope["market"] == "CN_COMMODITY_FUTURES":
        require(
            tuple(spec.exchange_scope)
            == tuple(research_job.exchange_scope)
            == tuple(snapshot_binding.exchange_scope)
            == tuple(scope.get("exchange_scope", ())),
            "EXCHANGE_SCOPE_MISMATCH",
            "commodity futures exchange scope differs",
        )
        require(
            spec.contract_chain_ref
            == snapshot_binding.contract_chain_ref
            == scope.get("contract_chain_ref"),
            "CONTRACT_CHAIN_MISMATCH",
            "commodity futures contract chain differs",
        )
        require(
            spec.roll_policy_ref
            == snapshot_binding.roll_policy_ref
            == scope.get("roll_policy_ref"),
            "ROLL_POLICY_MISMATCH",
            "commodity futures roll policy differs",
        )
    require(
        spec.decision_clock
        == research_job.decision_clock
        == snapshot_binding.decision_clock
        == clocks["signal_time"]
        and spec.trade_clock
        == research_job.trade_clock
        == snapshot_binding.trade_clock
        == clocks["earliest_trade_time"],
        "CLOCK_MISMATCH",
        "decision or trade clocks differ",
    )
    require(
        spec.validation_policy_ref == policy,
        "VALIDATION_POLICY_MISMATCH",
        "validation policy differs",
    )
    require(
        str(getattr(spec.license_purpose, "value", spec.license_purpose))
        == snapshot_binding.purpose.value,
        "LICENSE_PURPOSE_MISMATCH",
        "license purpose differs",
    )

    declared_fields: dict[str, object] = {}
    for contract in frozen_snapshot.contracts.values():
        require(
            contract.source_class.is_formal,
            "DATASET_SOURCE_NOT_FORMAL",
            f"{contract.dataset_id} is exploratory",
        )
        for field in contract.fields:
            declared_fields[field.name] = field
            require(
                snapshot_binding.purpose in field.allowed_purposes,
                "FIELD_PURPOSE_NOT_ALLOWED",
                f"{field.name} purpose is not allowed",
            )
            require(
                field.license_tag in spec.allowed_license_tags
                and field.license_tag in snapshot_binding.allowed_license_tags,
                "FIELD_LICENSE_NOT_ALLOWED",
                f"{field.name} license is not allowed",
            )
    require(
        input_fields <= declared_fields.keys(),
        "IR_FIELD_NOT_IN_SNAPSHOT",
        "Factor IR references a field absent from snapshot",
    )

    if violations:
        raise FormalPreconditionError(tuple(violations))
    return FormalExecutionBinding(
        experiment_id=spec.experiment_id,
        market=spec.market,
        universe_ref=spec.universe_ref,
        frequency=spec.frequency,
        snapshot_id=spec.snapshot_id,
        snapshot_manifest_hash=spec.snapshot_manifest_hash,
        factor_ir_hash=spec.factor_ir_hash,
    )


def _digest(value: str | None) -> str | None:
    return value.removeprefix("sha256:") if value is not None else None
