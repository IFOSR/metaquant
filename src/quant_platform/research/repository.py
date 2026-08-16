from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.research.models import (
    AuditEventModel,
    ExperimentSpecModel,
    OutboxEventModel,
    ResearchBriefVersionModel,
    ResearchCommandReceiptModel,
    ResearchJobModel,
)
from quant_platform.research.schemas import (
    FREQUENCIES,
    BriefContent,
    BriefDirection,
    BriefStatus,
    CommandReceipt,
    MarketId,
    ResearchBriefRecord,
    ResearchJobRecord,
    ResearchJobState,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _content_hash(content: BriefContent) -> str:
    canonical = json.dumps(
        content.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"


class SqlAlchemyResearchRepository:
    def __init__(
        self,
        engine: Engine,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        self._before_commit = before_commit

    def create_job(
        self,
        *,
        actor_id: str,
        project_id: str = "local",
        title: str,
        market: str,
        universe_ref: str,
        frequency: str,
        decision_clock: str,
        trade_clock: str,
        settlement_clock: str | None,
        exchange_scope: list[str],
        contract_selection: str | None,
        roll_policy: str | None,
        horizon: str,
        research_brief_version_id: str,
        budget: dict[str, Any],
    ) -> ResearchJobRecord:
        self._validate_job_fields(
            market=market,
            frequency=frequency,
            settlement_clock=settlement_clock,
            exchange_scope=exchange_scope,
            contract_selection=contract_selection,
            roll_policy=roll_policy,
        )
        timestamp = _now()
        model = ResearchJobModel(
            id=f"rj_{uuid4().hex}",
            project_id=project_id,
            resource_version=1,
            title=title,
            market=market,
            environment="RESEARCH",
            state=ResearchJobState.DRAFT,
            owner=actor_id,
            universe_ref=universe_ref,
            frequency=frequency,
            decision_clock=decision_clock,
            trade_clock=trade_clock,
            settlement_clock=settlement_clock,
            exchange_scope=exchange_scope,
            contract_selection=contract_selection,
            roll_policy=roll_policy,
            horizon=horizon,
            research_brief_version_id=research_brief_version_id,
            budget=budget,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._sessions.begin() as session:
            session.add(model)
        return self._job_record(model)

    def execute_create_job_command(
        self,
        *,
        actor_id: str,
        project_id: str = "local",
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        title: str,
        market: str,
        environment: str = "RESEARCH",
        universe_ref: str,
        frequency: str,
        decision_clock: str,
        trade_clock: str,
        settlement_clock: str | None,
        exchange_scope: list[str],
        contract_selection: str | None,
        roll_policy: str | None,
        horizon: str,
        research_brief_version_id: str,
        budget: dict[str, Any],
    ) -> CommandReceipt:
        self._validate_job_fields(
            market=market,
            frequency=frequency,
            settlement_clock=settlement_clock,
            exchange_scope=exchange_scope,
            contract_selection=contract_selection,
            roll_policy=roll_policy,
        )
        with self._sessions.begin() as session:
            self._lock_idempotency_key(session, actor_id, idempotency_key)
            existing = session.get(
                ResearchCommandReceiptModel, (actor_id, idempotency_key)
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSE")
                return CommandReceipt.model_validate(existing.response)

            timestamp = _now()
            command_id = f"cmd_{uuid4().hex}"
            job = ResearchJobModel(
                id=f"rj_{uuid4().hex}",
                project_id=project_id,
                resource_version=1,
                title=title,
                market=market,
                environment=environment,
                state=ResearchJobState.DRAFT,
                owner=actor_id,
                universe_ref=universe_ref,
                frequency=frequency,
                decision_clock=decision_clock,
                trade_clock=trade_clock,
                settlement_clock=settlement_clock,
                exchange_scope=exchange_scope,
                contract_selection=contract_selection,
                roll_policy=roll_policy,
                horizon=horizon,
                research_brief_version_id=research_brief_version_id,
                budget=budget,
                created_at=timestamp,
                updated_at=timestamp,
            )
            receipt = CommandReceipt(
                command_id=command_id,
                resource_id=job.id,
                submitted_at=timestamp,
            )
            after_hash = self._job_hash(job)
            event_id = f"evt_{uuid4().hex}"
            session.add_all(
                [
                    job,
                    ResearchCommandReceiptModel(
                        actor_id=actor_id,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response=receipt.model_dump(mode="json"),
                        created_at=timestamp,
                    ),
                    AuditEventModel(
                        id=f"audit_{uuid4().hex}",
                        occurred_at=timestamp,
                        actor=actor_id,
                        action="research_job.created",
                        resource_id=job.id,
                        resource_version="1",
                        reason=reason,
                        parent_artifact_id=parent_artifact_id,
                        request_id=command_id,
                        correlation_id=command_id,
                        policy_decision="RESEARCH_ONLY",
                        before_hash=None,
                        after_hash=after_hash,
                    ),
                    OutboxEventModel(
                        event_id=event_id,
                        event_type="ResearchJobCreated",
                        aggregate_type="ResearchJob",
                        aggregate_id=job.id,
                        aggregate_version="1",
                        occurred_at=timestamp,
                        payload={
                            "command_id": command_id,
                            "market": market,
                            "owner": actor_id,
                            "state": ResearchJobState.DRAFT,
                        },
                        schema_version="v1",
                        sequence=None,
                        published=False,
                        published_at=None,
                    ),
                ]
            )
            if self._before_commit is not None:
                self._before_commit()
            return receipt

    def list_jobs(
        self,
        *,
        scopes: frozenset[tuple[str, str]],
        market: str | None = None,
        state: str | None = None,
    ) -> list[ResearchJobRecord]:
        with self._sessions() as session:
            if not scopes:
                return []
            statement = select(ResearchJobModel).where(
                or_(
                    *[
                        and_(
                            ResearchJobModel.project_id == project_id,
                            ResearchJobModel.market == scope_market,
                        )
                        for project_id, scope_market in scopes
                    ]
                )
            )
            if market is not None:
                statement = statement.where(ResearchJobModel.market == market)
            if state is not None:
                statement = statement.where(ResearchJobModel.state == state)
            statement = statement.order_by(
                ResearchJobModel.updated_at.desc(), ResearchJobModel.id
            )
            return [
                self._job_record(model) for model in session.scalars(statement).all()
            ]

    def get_job(
        self,
        job_id: str,
        *,
        scopes: frozenset[tuple[str, str]] | None = None,
    ) -> ResearchJobRecord | None:
        with self._sessions() as session:
            model = session.get(ResearchJobModel, job_id)
            if model is None or (
                scopes is not None and (model.project_id, model.market) not in scopes
            ):
                return None
            return self._job_record(model)

    def latest_experiment_id(self, job_id: str) -> str | None:
        with self._sessions() as session:
            return session.scalar(
                select(ExperimentSpecModel.id)
                .where(ExperimentSpecModel.research_job_id == job_id)
                .order_by(ExperimentSpecModel.created_at.desc())
                .limit(1)
            )

    def create_brief_version(
        self,
        *,
        job_id: str,
        actor_id: str,
        content: BriefContent,
        expected_job_version: int,
    ) -> ResearchBriefRecord:
        with self._sessions.begin() as session:
            job = session.get(ResearchJobModel, job_id)
            if job is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            self._check_version(job.resource_version, expected_job_version)
            current_version = session.scalar(
                select(func.max(ResearchBriefVersionModel.version)).where(
                    ResearchBriefVersionModel.job_id == job_id
                )
            )
            model = ResearchBriefVersionModel(
                id=f"rbv_{uuid4().hex}",
                job_id=job_id,
                version=(current_version or 0) + 1,
                resource_version=1,
                status=BriefStatus.DRAFT,
                content_hash=None,
                created_at=_now(),
                created_by=actor_id,
                frozen_at=None,
                frozen_by=None,
                **content.model_dump(mode="json"),
            )
            session.add(model)
            job.resource_version += 1
            job.research_brief_version_id = model.id
            job.updated_at = _now()
        return self._brief_record(model)

    def list_briefs(self, job_id: str) -> list[ResearchBriefRecord]:
        with self._sessions() as session:
            models: Sequence[ResearchBriefVersionModel] = session.scalars(
                select(ResearchBriefVersionModel)
                .where(ResearchBriefVersionModel.job_id == job_id)
                .order_by(ResearchBriefVersionModel.version)
            ).all()
            return [self._brief_record(model) for model in models]

    def get_brief(self, brief_id: str) -> ResearchBriefRecord | None:
        with self._sessions() as session:
            model = session.get(ResearchBriefVersionModel, brief_id)
            return self._brief_record(model) if model is not None else None

    def update_brief(
        self,
        brief_id: str,
        *,
        actor_id: str,
        content: BriefContent,
        expected_resource_version: int,
    ) -> ResearchBriefRecord:
        del actor_id
        with self._sessions.begin() as session:
            model = session.scalar(
                select(ResearchBriefVersionModel)
                .where(ResearchBriefVersionModel.id == brief_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            self._check_version(model.resource_version, expected_resource_version)
            if model.status != BriefStatus.DRAFT:
                raise ValueError("BRIEF_NOT_DRAFT")
            self._write_content(model, content)
            model.resource_version += 1
        return self._brief_record(model)

    def freeze_brief(
        self,
        brief_id: str,
        *,
        actor_id: str,
        expected_resource_version: int,
    ) -> ResearchBriefRecord:
        with self._sessions.begin() as session:
            model = session.scalar(
                select(ResearchBriefVersionModel)
                .where(ResearchBriefVersionModel.id == brief_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            self._check_version(model.resource_version, expected_resource_version)
            if model.status != BriefStatus.DRAFT:
                raise ValueError("BRIEF_NOT_DRAFT")
            content = self._brief_content(model)
            model.content_hash = _content_hash(content)
            model.status = BriefStatus.FROZEN
            model.resource_version += 1
            model.frozen_at = _now()
            model.frozen_by = actor_id
        return self._brief_record(model)

    def get_command_receipt(
        self, actor_id: str, idempotency_key: str
    ) -> tuple[str, CommandReceipt] | None:
        with self._sessions() as session:
            model = session.get(
                ResearchCommandReceiptModel, (actor_id, idempotency_key)
            )
            if model is None:
                return None
            return model.request_hash, CommandReceipt.model_validate(model.response)

    def save_command_receipt(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        receipt: CommandReceipt,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                ResearchCommandReceiptModel(
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response=receipt.model_dump(mode="json"),
                    created_at=_now(),
                )
            )

    def execute_create_brief_command(
        self,
        *,
        job_id: str,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        content: BriefContent | dict[str, Any],
        expected_job_version: int,
    ) -> CommandReceipt:
        brief_content = (
            content
            if isinstance(content, BriefContent)
            else BriefContent.model_validate(content)
        )
        with self._sessions.begin() as session:
            self._lock_idempotency_key(session, actor_id, idempotency_key)
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            job = session.scalar(
                select(ResearchJobModel)
                .where(ResearchJobModel.id == job_id)
                .with_for_update()
            )
            if job is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            self._check_version(job.resource_version, expected_job_version)
            current_version = session.scalar(
                select(func.max(ResearchBriefVersionModel.version)).where(
                    ResearchBriefVersionModel.job_id == job_id
                )
            )
            model = ResearchBriefVersionModel(
                id=f"rbv_{uuid4().hex}",
                job_id=job_id,
                version=(current_version or 0) + 1,
                resource_version=1,
                status=BriefStatus.DRAFT,
                content_hash=None,
                created_at=_now(),
                created_by=actor_id,
                frozen_at=None,
                frozen_by=None,
                **brief_content.model_dump(mode="json"),
            )
            session.add(model)
            job.resource_version += 1
            job.research_brief_version_id = model.id
            job.updated_at = _now()
            receipt = self._record_brief_delivery(
                session,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason=reason,
                parent_artifact_id=parent_artifact_id,
                model=model,
                action="research_brief.created",
                event_type="ResearchBriefCreated",
            )
            if self._before_commit is not None:
                self._before_commit()
            return receipt

    def execute_update_brief_command(
        self,
        *,
        brief_id: str,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        content: BriefContent,
        expected_resource_version: int,
    ) -> CommandReceipt:
        with self._sessions.begin() as session:
            self._lock_idempotency_key(session, actor_id, idempotency_key)
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            model = session.scalar(
                select(ResearchBriefVersionModel)
                .where(ResearchBriefVersionModel.id == brief_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            self._check_version(model.resource_version, expected_resource_version)
            if model.status != BriefStatus.DRAFT:
                raise ValueError("BRIEF_NOT_DRAFT")
            self._write_content(model, content)
            model.resource_version += 1
            receipt = self._record_brief_delivery(
                session,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason=reason,
                parent_artifact_id=parent_artifact_id,
                model=model,
                action="research_brief.updated",
                event_type="ResearchBriefUpdated",
            )
            if self._before_commit is not None:
                self._before_commit()
            return receipt

    def execute_freeze_brief_command(
        self,
        *,
        brief_id: str,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        expected_resource_version: int,
    ) -> CommandReceipt:
        with self._sessions.begin() as session:
            self._lock_idempotency_key(session, actor_id, idempotency_key)
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            model = session.scalar(
                select(ResearchBriefVersionModel)
                .where(ResearchBriefVersionModel.id == brief_id)
                .with_for_update()
            )
            if model is None:
                raise ValueError("RESOURCE_NOT_FOUND")
            existing = self._receipt(session, actor_id, idempotency_key)
            if existing is not None:
                return self._replay_receipt(existing, request_hash)
            self._check_version(model.resource_version, expected_resource_version)
            if model.status != BriefStatus.DRAFT:
                raise ValueError("BRIEF_NOT_DRAFT")
            model.content_hash = _content_hash(self._brief_content(model))
            model.status = BriefStatus.FROZEN
            model.resource_version += 1
            model.frozen_at = _now()
            model.frozen_by = actor_id
            receipt = self._record_brief_delivery(
                session,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason=reason,
                parent_artifact_id=parent_artifact_id,
                model=model,
                action="research_brief.frozen",
                event_type="ResearchBriefFrozen",
            )
            if self._before_commit is not None:
                self._before_commit()
            return receipt

    @staticmethod
    def _receipt(
        session: Session, actor_id: str, idempotency_key: str
    ) -> ResearchCommandReceiptModel | None:
        return session.get(ResearchCommandReceiptModel, (actor_id, idempotency_key))

    @staticmethod
    def _lock_idempotency_key(
        session: Session, actor_id: str, idempotency_key: str
    ) -> None:
        if session.get_bind().dialect.name != "postgresql":
            return
        digest = hashlib.sha256(f"{actor_id}\0{idempotency_key}".encode()).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
        session.execute(select(func.pg_advisory_xact_lock(lock_id)))

    @staticmethod
    def _replay_receipt(
        existing: ResearchCommandReceiptModel, request_hash: str
    ) -> CommandReceipt:
        if existing.request_hash != request_hash:
            raise ValueError("IDEMPOTENCY_KEY_REUSE")
        return CommandReceipt.model_validate(existing.response)

    def _record_brief_delivery(
        self,
        session: Session,
        *,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        reason: str,
        parent_artifact_id: str | None,
        model: ResearchBriefVersionModel,
        action: str,
        event_type: str,
    ) -> CommandReceipt:
        timestamp = _now()
        command_id = f"cmd_{uuid4().hex}"
        receipt = CommandReceipt(
            command_id=command_id,
            resource_id=model.id,
            submitted_at=timestamp,
        )
        content_hash = _content_hash(self._brief_content(model))
        session.add_all(
            [
                ResearchCommandReceiptModel(
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response=receipt.model_dump(mode="json"),
                    created_at=timestamp,
                ),
                AuditEventModel(
                    id=f"audit_{uuid4().hex}",
                    occurred_at=timestamp,
                    actor=actor_id,
                    action=action,
                    resource_id=model.id,
                    resource_version=str(model.resource_version),
                    reason=reason,
                    parent_artifact_id=parent_artifact_id,
                    request_id=command_id,
                    correlation_id=command_id,
                    policy_decision="RESEARCH_ONLY",
                    before_hash=None,
                    after_hash=content_hash,
                ),
                OutboxEventModel(
                    event_id=f"evt_{uuid4().hex}",
                    event_type=event_type,
                    aggregate_type="ResearchBriefVersion",
                    aggregate_id=model.id,
                    aggregate_version=str(model.resource_version),
                    occurred_at=timestamp,
                    payload={
                        "command_id": command_id,
                        "job_id": model.job_id,
                        "status": model.status,
                    },
                    schema_version="v1",
                    sequence=None,
                    published=False,
                    published_at=None,
                ),
            ]
        )
        return receipt

    @staticmethod
    def _check_version(current: int, expected: int) -> None:
        if current != expected:
            raise ValueError(f"STALE_OBJECT_VERSION:{current}")

    @staticmethod
    def _validate_job_fields(
        *,
        market: str,
        frequency: str,
        settlement_clock: str | None,
        exchange_scope: list[str],
        contract_selection: str | None,
        roll_policy: str | None,
    ) -> None:
        if frequency not in FREQUENCIES:
            raise ValueError("FREQUENCY_NOT_ENABLED")
        if market == MarketId.CN_COMMODITY_FUTURES and not all(
            (settlement_clock, exchange_scope, contract_selection, roll_policy)
        ):
            raise ValueError("FUTURES_FIELDS_REQUIRED")

    @staticmethod
    def _job_hash(model: ResearchJobModel) -> str:
        canonical = json.dumps(
            {
                "budget": model.budget,
                "decision_clock": model.decision_clock,
                "frequency": model.frequency,
                "horizon": model.horizon,
                "id": model.id,
                "market": model.market,
                "owner": model.owner,
                "state": model.state,
                "trade_clock": model.trade_clock,
                "universe_ref": model.universe_ref,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"

    @staticmethod
    def _write_content(model: ResearchBriefVersionModel, content: BriefContent) -> None:
        for field, value in content.model_dump(mode="json").items():
            setattr(model, field, value)

    @staticmethod
    def _brief_content(model: ResearchBriefVersionModel) -> BriefContent:
        return BriefContent(
            hypothesis=model.hypothesis,
            economic_mechanism=model.economic_mechanism,
            expected_direction=BriefDirection(model.expected_direction),
            falsification_conditions=model.falsification_conditions,
            allowed_data_domains=model.allowed_data_domains,
            forbidden_data_domains=model.forbidden_data_domains,
            constraints=model.constraints,
            evidence_ref_ids=model.evidence_ref_ids,
            uncertainties=model.uncertainties,
        )

    @staticmethod
    def _job_record(model: ResearchJobModel) -> ResearchJobRecord:
        return ResearchJobRecord(
            id=model.id,
            project_id=model.project_id,
            resource_version=model.resource_version,
            title=model.title,
            market=MarketId(model.market),
            environment=model.environment,
            state=ResearchJobState(model.state),
            owner=model.owner,
            universe_ref=model.universe_ref,
            frequency=model.frequency,
            decision_clock=model.decision_clock,
            trade_clock=model.trade_clock,
            settlement_clock=model.settlement_clock,
            exchange_scope=model.exchange_scope,
            contract_selection=model.contract_selection,
            roll_policy=model.roll_policy,
            horizon=model.horizon,
            research_brief_version_id=model.research_brief_version_id,
            budget=model.budget,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @classmethod
    def _brief_record(cls, model: ResearchBriefVersionModel) -> ResearchBriefRecord:
        return ResearchBriefRecord(
            **cls._brief_content(model).model_dump(),
            id=model.id,
            job_id=model.job_id,
            version=model.version,
            resource_version=model.resource_version,
            status=BriefStatus(model.status),
            content_hash=model.content_hash,
            created_at=model.created_at,
            created_by=model.created_by,
            frozen_at=model.frozen_at,
            frozen_by=model.frozen_by,
        )
