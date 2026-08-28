"""Tests for paper node assembly (config + factory binding)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import asyncio

import pytest

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.futures_fee import FuturesFeeModel
from quant_platform.paper.contracts import PaperAccount, PaperAccountState
from quant_platform.paper.node import (
    ChinaVenueSandboxExecFactory,
    PaperNodeRunner,
    exec_factory_for,
    warmup_bars_for,
)
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.research.models import Base


def _account(market: str = "CN_A") -> PaperAccount:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return PaperAccount(
        id="pa_abcdef12",
        owner="tester",
        draft_id="sd_1",
        artifact_address="sha256:" + "a" * 64,
        content_hash="sha256:" + "b" * 64,
        market=market,
        instrument_ids=("600000.SH",) if market == "CN_A" else ("RB2610.SHF",),
        frequency="1d",
        initial_cash=Decimal("1000000"),
        state=PaperAccountState.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _repository() -> SqlAlchemyPaperRepository:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return SqlAlchemyPaperRepository(engine)


def test_build_config_binds_venue_and_trader() -> None:
    runner = PaperNodeRunner(
        account=_account(),
        code="class S: ...",
        repository=_repository(),
        poller=None,  # type: ignore[arg-type]
    )
    config = runner.build_config()
    assert config.trader_id.value.startswith("PAPER-ABCDEF12")
    assert "SSE" in config.exec_clients
    venue_config = config.exec_clients["SSE"]
    assert venue_config.account_type == "CASH"
    assert venue_config.starting_balances == ["1000000 CNY"]


def test_build_config_futures_margin_venue() -> None:
    runner = PaperNodeRunner(
        account=_account("CN_COMMODITY_FUTURES"),
        code="class S: ...",
        repository=_repository(),
        poller=None,  # type: ignore[arg-type]
    )
    config = runner.build_config()
    assert "SHFE" in config.exec_clients
    assert config.exec_clients["SHFE"].account_type == "MARGIN"


def test_exec_factory_binds_market_fee_model() -> None:
    equity_cls = exec_factory_for(_account())
    assert issubclass(equity_cls, ChinaVenueSandboxExecFactory)
    assert isinstance(equity_cls.fee_model, AShareFeeModel)

    futures_cls = exec_factory_for(_account("CN_COMMODITY_FUTURES"))
    assert isinstance(futures_cls.fee_model, FuturesFeeModel)


def test_warmup_defaults_by_frequency() -> None:
    assert warmup_bars_for("1d") > 0
    assert warmup_bars_for("5m") > 0
    assert warmup_bars_for("unknown") == 0


class _FakeNode:
    """最小 TradingNode 替身：run_until 只需要这四个接口。"""

    def is_running(self) -> bool:
        return True

    async def run_async(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def dispose(self) -> None:
        return None


def test_run_until_builds_node_inside_running_loop() -> None:
    """回归：节点构建必须发生在运行中的事件循环内。

    TradingNode 构造时通过 asyncio.get_event_loop() 绑定 loop，引擎的
    命令/事件队列消费协程调度在该 loop 上。若在循环外 build（如脚本
    main() 里预构建），队列协程绑到永不运行的默认 loop——K 线照流
    （msgbus 同步派发），但 SubmitOrder 命令无人消费，订单全部停在
    INITIALIZED，永远零成交。
    """
    runner = PaperNodeRunner(
        account=_account(),
        code="class S: ...",
        repository=_repository(),
        poller=None,  # type: ignore[arg-type]
    )
    built_with_running_loop: list[bool] = []

    def fake_build() -> _FakeNode:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            built_with_running_loop.append(False)
        else:
            built_with_running_loop.append(True)
        return _FakeNode()

    runner.build = fake_build  # type: ignore[method-assign]

    async def noop_async(*args: object, **kwargs: object) -> None:
        return None

    runner._drain_engines = noop_async  # type: ignore[method-assign]
    runner._request_warmup = lambda: None  # type: ignore[method-assign]

    async def main() -> None:
        stop = asyncio.Event()
        stop.set()  # 不进入轮询循环，build 完成后即停
        await runner.run_until(stop)

    asyncio.run(main())
    assert built_with_running_loop == [True]


def test_run_until_records_error_state_when_build_fails() -> None:
    """启动失败（如策略代码无法加载）要落库 ERROR，供运维页显示真实原因。"""
    repository = _repository()
    runner = PaperNodeRunner(
        account=_account(),
        code="class S: ...",
        repository=repository,
        poller=None,  # type: ignore[arg-type]
    )

    def boom() -> _FakeNode:
        raise RuntimeError("strategy load failed")

    runner.build = boom  # type: ignore[method-assign]

    async def main() -> None:
        await runner.run_until(asyncio.Event())

    with pytest.raises(RuntimeError, match="strategy load failed"):
        asyncio.run(main())

    state = repository.get_run_state("pa_abcdef12")
    assert state is not None
    assert state["status"] == "ERROR"
    assert "strategy load failed" in str(state["last_error"])
