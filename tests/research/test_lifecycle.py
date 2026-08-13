from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.research.models import Base
from quant_platform.research.repository import SqlAlchemyResearchRepository
from quant_platform.research.schemas import (
    BriefContent,
    BriefDirection,
    BriefStatus,
)


def make_repository() -> SqlAlchemyResearchRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyResearchRepository(engine)


def brief_content(
    hypothesis: str = "Inventory pressure predicts returns",
) -> BriefContent:
    return BriefContent(
        hypothesis=hypothesis,
        economic_mechanism="Inventory surprises alter near-term scarcity.",
        expected_direction=BriefDirection.NEGATIVE,
        falsification_conditions=["No OOS rank IC after costs"],
        allowed_data_domains=["formal.market.eod"],
        forbidden_data_domains=["future.revisions"],
        constraints=["daily only"],
        evidence_ref_ids=["evidence://inventory/1"],
        uncertainties=["reporting lag"],
    )


def test_frozen_brief_cannot_be_updated() -> None:
    repository = make_repository()
    job = repository.create_job(
        actor_id="researcher-1",
        project_id="local",
        title="Inventory signal",
        market="CN_A",
        universe_ref="universe://csi500/pit",
        frequency="1d",
        decision_clock="T_CLOSE",
        trade_clock="T_PLUS_1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief://seed",
        budget={"candidate_limit": 10, "wall_clock_minutes": 30},
    )
    brief = repository.create_brief_version(
        job_id=job.id,
        actor_id="researcher-1",
        content=brief_content(),
        expected_job_version=1,
    )

    frozen = repository.freeze_brief(
        brief.id,
        actor_id="research-lead-1",
        expected_resource_version=1,
    )

    assert frozen.status is BriefStatus.FROZEN
    assert frozen.content_hash is not None
    assert frozen.resource_version == 2

    try:
        repository.update_brief(
            brief.id,
            actor_id="researcher-1",
            content=brief_content("Changed after freeze"),
            expected_resource_version=2,
        )
    except ValueError as exc:
        assert str(exc) == "BRIEF_NOT_DRAFT"
    else:
        raise AssertionError("frozen brief update unexpectedly succeeded")


def test_brief_updates_require_current_resource_version() -> None:
    repository = make_repository()
    job = repository.create_job(
        actor_id="researcher-1",
        title="Momentum signal",
        market="CN_A",
        universe_ref="universe://csi300/pit",
        frequency="1d",
        decision_clock="T_CLOSE",
        trade_clock="T_PLUS_1_OPEN",
        settlement_clock=None,
        exchange_scope=[],
        contract_selection=None,
        roll_policy=None,
        horizon="20TD",
        research_brief_version_id="brief://seed",
        budget={"candidate_limit": 10, "wall_clock_minutes": 30},
    )
    brief = repository.create_brief_version(
        job_id=job.id,
        actor_id="researcher-1",
        content=brief_content(),
        expected_job_version=1,
    )

    try:
        repository.update_brief(
            brief.id,
            actor_id="researcher-1",
            content=brief_content("Stale edit"),
            expected_resource_version=99,
        )
    except ValueError as exc:
        assert str(exc) == "STALE_OBJECT_VERSION:1"
    else:
        raise AssertionError("stale brief update unexpectedly succeeded")
