"""Tests for the async backtest task service (P2 BacktestNode alignment)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.artifacts.store import InMemoryArtifactStore
from quant_platform.data_gateway.loader import RawPITRow
from quant_platform.data_gateway.pit_store import SqlAlchemyPitStore
from quant_platform.research.models import Base
from quant_platform.strategy_generation.backtest import BacktestRequest
from quant_platform.strategy_generation.repository import (
    SqlAlchemyStrategyRepository,
)
from quant_platform.strategy_generation.schemas import AgentOutput
from quant_platform.strategy_generation.service import StrategyBacktestService
from quant_platform.strategy_generation.tasks import BacktestTaskService

_CODE = (
    "from nautilus_trader.config import StrategyConfig\n"
    "from nautilus_trader.trading.strategy import Strategy\n"
    "from nautilus_trader.model.identifiers import InstrumentId\n"
    "from nautilus_trader.model.data import BarType\n"
    "class GenStrategy(Strategy):\n"
    "    def __init__(self, instrument_id: str, bar_type_str: str):\n"
    "        super().__init__(StrategyConfig(strategy_id='GEN'))\n"
    "        self._instrument_id = InstrumentId.from_str(instrument_id)\n"
    "        self._bar_type = BarType.from_str(bar_type_str)\n"
    "    def on_start(self):\n"
    "        self.subscribe_bars(self._bar_type)\n"
    "    def on_bar(self, bar):\n"
    "        pass\n"
    "    def on_stop(self):\n"
    "        pass\n"
)

_BASE = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)


def _seed_daily_rows(engine: Engine, days: int = 10) -> None:
    sessions = SqlAlchemyStrategyRepository(engine)._sessions  # noqa: SLF001
    rows: list[RawPITRow] = []
    for day in range(days):
        ts = _BASE + timedelta(days=day)
        for field in ("open", "high", "low", "close", "volume"):
            rows.append(
                RawPITRow(
                    source_id="ifind-cn",
                    dataset_id="market-eod",
                    field=f"market.eod.{field}",
                    instrument_id="600000.SSE",
                    event_time=ts,
                    available_time=ts,
                    ingested_at=ts,
                    revision_id="r1",
                    license_tag="formal",
                    value_type="decimal",
                    value="10.0",
                )
            )
    SqlAlchemyPitStore(sessions).persist(rows)


def _make() -> tuple[BacktestTaskService, SqlAlchemyStrategyRepository]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    drafts = SqlAlchemyStrategyRepository(engine)
    _seed_daily_rows(engine)
    service = BacktestTaskService(
        sessions=drafts._sessions,  # noqa: SLF001
        artifact_store=InMemoryArtifactStore(),
        backtest_service=StrategyBacktestService(drafts._sessions),  # noqa: SLF001
        drafts=drafts,
    )
    return service, drafts


def _request() -> BacktestRequest:
    from quant_platform.markets.nt.venue import venue_spec_for_market

    return BacktestRequest(
        draft_id="sd_x",
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        trend_frequency=None,
        start=None,
        end=None,
        initial_cash=Decimal("1000000"),
        venue_spec=venue_spec_for_market("CN_A"),
    )


def _wait_terminal(service: BacktestTaskService, task_id: str) -> dict[str, object]:
    """轮询任务至 DONE/FAILED 并返回快照（防 None）。"""
    import time

    fetched: dict[str, object] | None = None
    for _ in range(200):
        fetched = service.get(task_id)
        assert fetched is not None
        if fetched["status"] in {"DONE", "FAILED"}:
            break
        time.sleep(0.05)
    assert fetched is not None
    return fetched


def test_task_request_hash_and_idempotency() -> None:
    service, _drafts = _make()
    task = service.create(actor_id="tester", request=_request())
    assert task["status"] in {"PENDING", "RUNNING", "DONE", "FAILED"}
    duplicate = service.create(actor_id="tester", request=_request())
    assert duplicate["id"] == task["id"]  # 同 request_hash 幂等


def test_task_fails_when_draft_missing() -> None:
    service, _drafts = _make()
    task = service.create(actor_id="tester", request=_request())
    fetched = _wait_terminal(service, task["id"])
    assert fetched["status"] == "FAILED"


def test_task_runs_frozen_draft_and_stores_result() -> None:
    service, drafts = _make()
    draft = drafts.create_draft(actor_id="tester", market="CN_A")
    drafts.apply_turn(
        draft_id=draft.id,
        user_content="make a strategy",
        output=AgentOutput(
            title="MA",
            explanation="Buy on cross.",
            question="",
            code=_CODE,
            ready=True,
            instrument_ids=["600000.SH"],
            frequency="1d",
        ),
    )
    request = _request().__class__(
        draft_id=draft.id,
        market="CN_A",
        instrument_ids=("600000.SH",),
        frequency="1d",
        trend_frequency=None,
        start=None,
        end=None,
        initial_cash=Decimal("1000000"),
        venue_spec=_request().venue_spec,
    )
    task = service.create(actor_id="tester", request=request)
    fetched = _wait_terminal(service, task["id"])
    assert fetched["status"] == "DONE"
    assert fetched["result_address"] is not None
    assert "result" in fetched
