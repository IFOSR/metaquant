"""Tests for the paper account service (freeze discipline + lifecycle)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.paper.artifact import StrategyArtifactStore
from quant_platform.paper.contracts import PaperAccountError, PaperAccountState
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.paper.service import PaperAccountService
from quant_platform.research.models import Base
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)
from quant_platform.strategy_generation.schemas import AgentOutput

_SAFE_CODE = (
    "from nautilus_trader.trading.strategy import Strategy\n"
    "class GenStrategy(Strategy):\n"
    "    pass\n"
)
_UNSAFE_CODE = "import os\nclass GenStrategy:\n    pass\n"


def make_service() -> tuple[PaperAccountService, SqlAlchemyStrategyRepository]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    drafts = SqlAlchemyStrategyRepository(engine)
    return (
        PaperAccountService(
            repository=SqlAlchemyPaperRepository(engine),
            artifacts=StrategyArtifactStore(InMemoryArtifactStore()),
            drafts=drafts,
        ),
        drafts,
    )


def _freeze_draft(
    drafts: SqlAlchemyStrategyRepository,
    *,
    code: str = _SAFE_CODE,
    frequency: str = "1d",
) -> str:
    draft = drafts.create_draft(actor_id="tester", market="CN_A")
    output = AgentOutput(
        title="MA cross",
        explanation="Buy on cross.",
        question="",
        code=code,
        ready=True,
        instrument_ids=["600000.SH"],
        frequency=frequency,
    )
    drafts.apply_turn(
        draft_id=draft.id,
        user_content="make a strategy",
        output=output,
    )
    frozen = drafts.freeze(draft_id=draft.id, actor_id="tester")
    return frozen.id


def test_create_account_from_frozen_draft() -> None:
    service, drafts = make_service()
    draft_id = _freeze_draft(drafts)
    account = service.create_account(
        actor_id="tester", draft_id=draft_id, initial_cash=None
    )
    assert account.state is PaperAccountState.ACTIVE
    assert account.draft_id == draft_id
    assert account.initial_cash == 1000000


def test_rejects_non_frozen_draft() -> None:
    service, drafts = make_service()
    draft = drafts.create_draft(actor_id="tester", market="CN_A")
    with pytest.raises(PaperAccountError, match="FROZEN"):
        service.create_account(actor_id="tester", draft_id=draft.id)


def test_rejects_unsafe_code_even_if_frozen() -> None:
    service, drafts = make_service()
    draft_id = _freeze_draft(drafts, code=_UNSAFE_CODE)
    with pytest.raises(PaperAccountError, match="security policy"):
        service.create_account(actor_id="tester", draft_id=draft_id)


def test_rejects_frequency_paper_does_not_support() -> None:
    service, drafts = make_service()
    draft_id = _freeze_draft(drafts, frequency="1w")  # 回测支持 1w，但仿真盘仍未支持
    with pytest.raises(PaperAccountError, match="1w"):
        service.create_account(actor_id="tester", draft_id=draft_id)


def test_lifecycle_transitions_and_terminal_close() -> None:
    service, drafts = make_service()
    draft_id = _freeze_draft(drafts)
    account = service.create_account(actor_id="tester", draft_id=draft_id)
    paused = service.transition(account_id=account.id, action="pause")
    assert paused.state is PaperAccountState.PAUSED
    resumed = service.transition(account_id=account.id, action="resume")
    assert resumed.state is PaperAccountState.ACTIVE
    closed = service.transition(account_id=account.id, action="close")
    assert closed.state is PaperAccountState.CLOSED
    with pytest.raises(PaperAccountError):
        service.transition(account_id=account.id, action="resume")


def test_require_active_guard() -> None:
    service, drafts = make_service()
    draft_id = _freeze_draft(drafts)
    account = service.create_account(actor_id="tester", draft_id=draft_id)
    assert service.require_active(account.id).id == account.id
    service.transition(account_id=account.id, action="pause")
    with pytest.raises(PaperAccountError, match="PAUSED"):
        service.require_active(account.id)


def test_missing_draft_rejected() -> None:
    service, _drafts = make_service()
    with pytest.raises(PaperAccountError, match="not found"):
        service.create_account(actor_id="tester", draft_id="sd_missing")
