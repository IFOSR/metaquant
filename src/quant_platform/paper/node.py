"""Paper trading runtime: TradingNode assembly + incremental run loop.

The runner binds one paper account to a live-kernel NautilusTrader node whose
orders execute against a China-market simulated exchange. Bars arrive
incrementally from the PIT poller and are published onto the kernel message
bus (topic ``data.bars.{bar_type}``) — the same path a real data adapter uses.
After each poll cycle the ledger reconciles fills/positions/equity into PG,
so a restarted process resumes instead of double counting.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
from nautilus_trader.common.component import Logger
from nautilus_trader.config import LoggingConfig, TradingNodeConfig
from nautilus_trader.live.factories import LiveExecClientFactory
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarSpecification, BarType
from nautilus_trader.model.identifiers import TraderId

from quant_platform.backtest.service import _CONTRACT_SPECS, _underlying
from quant_platform.markets.nt import (
    day_bar_spec,
    equity_instrument,
    futures_contract,
    minute_bar_spec,
    to_nautilus_bars,
)
from quant_platform.markets.nt.venue import venue_spec_for_market
from quant_platform.paper.contracts import PaperAccount
from quant_platform.paper.data_client import (
    PitBarPoller,
    PitDataClientConfig,
    PolledBar,
    data_factory_for,
)
from quant_platform.paper.ledger import (
    mark_to_market,
    reconcile_fills,
)
from quant_platform.paper.monitor import PaperMonitor, kill_switch_tripped
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.paper.sim_venue import (
    ChinaVenueSandboxExecutionClient,
    fee_model_for_market,
    sandbox_config_for,
    venue_for_instrument,
)
from quant_platform.strategy_generation.backtest import (
    StrategyLoadError,
    _normalize_instrument,
    load_strategy,
)

logger = logging.getLogger(__name__)

_BAR_SUFFIX = {
    "1d": "1-DAY-LAST-EXTERNAL",
    "5m": "5-MINUTE-LAST-EXTERNAL",
    "15m": "15-MINUTE-LAST-EXTERNAL",
    "30m": "30-MINUTE-LAST-EXTERNAL",
    "60m": "60-MINUTE-LAST-EXTERNAL",
}
_WARMUP_BY_FREQUENCY = {"1d": 250, "5m": 500, "15m": 500, "30m": 500, "60m": 500}


def _bar_spec_for(frequency: str) -> BarSpecification:
    """回测频率 → NT bar spec（日线用 day，分钟级用对应分钟数）。"""
    if frequency == "1d":
        return day_bar_spec()
    return minute_bar_spec(int(frequency[:-1]))


class ChinaVenueSandboxExecFactory(LiveExecClientFactory):
    """Sandbox exec factory bound to China-market fee semantics.

    子类（含动态生成的）通过类属性 ``fee_model``/``fill_model`` 绑定费率；
    ``create`` 必须是 classmethod 才能读到子类覆盖。
    """

    fee_model: Any = None
    fill_model: Any = None

    @classmethod
    def create(  # type: ignore[override]
        cls,
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: SandboxExecutionClientConfig,
        portfolio: Any,
        msgbus: Any,
        cache: Any,
        clock: Any,
    ) -> ChinaVenueSandboxExecutionClient:
        return ChinaVenueSandboxExecutionClient(
            loop=loop,
            portfolio=portfolio,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
            fee_model=cls.fee_model,
            fill_model=cls.fill_model,
        )


def exec_factory_for(account: PaperAccount) -> type[ChinaVenueSandboxExecFactory]:
    """动态子类绑定账户费率模型（NT 工厂按 ``type`` 注册）。

    注意：node_builder 以类名 ``"SandboxLiveExecClientFactory"`` 特判注入
    portfolio，因此动态类的 ``__name__`` 必须是这个魔法字符串（NT 版本
    pin 住；升级时复核 node_builder.build_exec_clients）。
    """
    multiplier: Decimal | None = None
    if account.market == "CN_COMMODITY_FUTURES":
        symbol, _venue = _normalize_instrument(account.instrument_ids[0])
        spec = _CONTRACT_SPECS.get(_underlying(symbol), ("1", "10", 0))
        multiplier = Decimal(spec[1])
    # 撮合假设与回测同一来源：按市场派生 VenueSpec（费用 + 涨跌停撮合）。
    venue_spec = venue_spec_for_market(account.market)
    attrs = {
        "fee_model": fee_model_for_market(account.market, multiplier=multiplier),
        "fill_model": venue_spec.fill_model,
    }
    return type(
        "SandboxLiveExecClientFactory",
        (ChinaVenueSandboxExecFactory,),
        attrs,
    )


def _precision_for(symbol: str, venue: str) -> int:
    if venue in ("SSE", "SZSE"):
        return 2
    _, _, precision = _CONTRACT_SPECS.get(_underlying(symbol), _CONTRACT_SPECS["RB"])
    return precision


def _instrument_ids_for_node(account: PaperAccount) -> dict[str, str]:
    """user-facing id → NautilusTrader instrument id（600000.SH → 600000.SSE）。"""
    mapping: dict[str, str] = {}
    for instrument_id in account.instrument_ids:
        symbol, venue = _normalize_instrument(instrument_id)
        mapping[instrument_id] = f"{symbol}.{venue}"
    return mapping


class PaperNodeRunner:
    """One paper account ↔ one TradingNode."""

    def __init__(
        self,
        *,
        account: PaperAccount,
        code: str,
        repository: SqlAlchemyPaperRepository,
        poller: PitBarPoller,
        poll_interval_seconds: int = 60,
        kill_switch_sessions: Any | None = None,
    ) -> None:
        self._account = account
        self._code = code
        self._repository = repository
        self._poller = poller
        self._poll_interval = poll_interval_seconds
        self._kill_switch_sessions = kill_switch_sessions
        self._monitor = PaperMonitor(
            account_id=account.id,
            expected_interval_seconds=poll_interval_seconds,
        )
        self._node: TradingNode | None = None
        self._data_client: Any | None = None
        self._strategy_bar_types: list[tuple[Any, BarType, str]] = []
        self._marks: dict[str, float] = {}
        self._log = Logger("PAPER-RUNNER")

    @property
    def monitor(self) -> PaperMonitor:
        return self._monitor

    def _persist_run_state(self, *, status: str, last_error: str | None) -> None:
        """把本周期运行进度写入 PG（运维页展示「跑到哪一步」）。"""
        self._repository.record_run_state(
            account_id=self._account.id,
            status=status,
            cycles_total=self._monitor.cycles_total,
            bars_total=self._monitor.bars_total,
            last_cycle_at=self._monitor.last_cycle_at,
            last_bar_at=self._monitor.last_bar_at,
            last_error=last_error,
        )

    # -- assembly -----------------------------------------------------------

    def check_restart_safe(self) -> None:
        """MVP 语义：paper 进程重启 = 空仓重启。

        SimulatedExchange 无法注入既有持仓；若账本里已有非零仓位，拒绝启动，
        提示先人工处理（close 或清仓），避免账实分裂。
        """
        positions = self._repository.list_positions(self._account.id)
        open_positions = [p for p in positions if p["quantity"] != 0]
        if open_positions:
            raise RuntimeError(
                "account has non-flat ledger positions; a paper restart would "
                "desync the simulated exchange from the ledger. Close the "
                "positions or the account first: "
                + ", ".join(
                    f"{p['instrument_id']}×{p['quantity']}" for p in open_positions
                )
            )

    def build_config(self) -> TradingNodeConfig:
        account = self._account
        venue = venue_for_instrument(account.instrument_ids[0])
        exec_config = sandbox_config_for(
            account.market,
            instrument_ids=account.instrument_ids,
            initial_cash=account.initial_cash,
        )
        return TradingNodeConfig(
            trader_id=TraderId(f"PAPER-{account.id.replace('pa_', '')[:8].upper()}"),
            logging=LoggingConfig(log_level="INFO"),
            data_clients={venue: PitDataClientConfig()},
            exec_clients={venue: exec_config},
        )

    def build(self) -> TradingNode:
        node = TradingNode(config=self.build_config())
        venue = venue_for_instrument(self._account.instrument_ids[0])
        node.add_exec_client_factory(venue, exec_factory_for(self._account))
        id_map = _instrument_ids_for_node(self._account)
        frequency = self._account.frequency
        bar_suffix = _BAR_SUFFIX[frequency]
        instruments = {
            nt_id: (user_id, _precision_for(*_normalize_instrument(user_id)))
            for user_id, nt_id in id_map.items()
        }
        factory = data_factory_for(
            store=self._poller._store,  # noqa: SLF001
            instruments=instruments,
            frequency=frequency,
            bar_spec=_bar_spec_for(frequency),
        )
        node.add_data_client_factory(venue, factory)
        node.build()
        self._data_client = factory.instance

        for user_id in id_map:
            symbol, nt_venue = _normalize_instrument(user_id)
            precision = _precision_for(symbol, nt_venue)
            instrument = (
                equity_instrument(symbol=symbol, venue=nt_venue)
                if nt_venue in ("SSE", "SZSE")
                else futures_contract(
                    symbol=symbol,
                    venue=nt_venue,
                    underlying=_underlying(symbol),
                    price_increment=str(
                        _CONTRACT_SPECS.get(_underlying(symbol), ("1",))[0]
                    ),
                    multiplier=str(
                        _CONTRACT_SPECS.get(_underlying(symbol), ("", "10"))[1]
                    ),
                    price_precision=precision,
                    activation_ns=0,
                    expiration_ns=9_999_999_999_999_999_999,
                )
            )
            node.cache.add_instrument(instrument)
            bar_type_str = f"{instrument.id}-{bar_suffix}"
            strategy = load_strategy(
                self._code, instrument_id=str(instrument.id), bar_type_str=bar_type_str
            )
            node.trader.add_strategy(strategy)
            self._strategy_bar_types.append(
                (strategy, BarType.from_str(bar_type_str), user_id)
            )
        self._node = node
        return node

    # -- runtime ------------------------------------------------------------

    def _publish(self, item: PolledBar) -> None:
        assert self._node is not None and self._data_client is not None
        nt_id = _instrument_ids_for_node(self._account)[item.instrument_id]
        bar_spec = _bar_spec_for(self._account.frequency)
        precision = _precision_for(*_normalize_instrument(item.instrument_id))
        bars = to_nautilus_bars(
            (item.bar,),
            instrument_id=nt_id,
            bar_spec=bar_spec,
            price_precision=precision,
        )
        for bar in bars:
            # NT 标准实盘数据路径：DataClient._handle_data → 策略/缓存/撮合所。
            self._data_client.publish_bar(bar)
            self._marks[item.instrument_id] = float(bar.close)

    def reconcile(self) -> dict[str, Any]:
        """把撮合回报对账进 PG，并写当日净值快照。"""
        assert self._node is not None
        # NT 的 fills 报告以 client_order_id 为 DataFrame 索引，
        # to_dict("records") 会丢掉该列——先 reset_index 还原（NT 1.231 pin）。
        fills_report = (
            self._node.trader.generate_order_fills_report()
            .reset_index()
            .to_dict("records")
        )
        inserted = reconcile_fills(
            repository=self._repository,
            account_id=self._account.id,
            fills_report=list(fills_report),
        )
        positions_report = self._node.trader.generate_positions_report().to_dict(
            "records"
        )
        positions: dict[str, int] = {}
        entries: dict[str, float] = {}
        realized = 0.0
        multipliers: dict[str, int] = {}
        for row in positions_report:
            nt_id = str(row["instrument_id"])
            user_id = next(
                (
                    user
                    for user, candidate in _instrument_ids_for_node(
                        self._account
                    ).items()
                    if candidate == nt_id
                ),
                nt_id,
            )
            quantity = int(float(str(row["quantity"])))
            side = str(row["side"]).upper()
            positions[user_id] = quantity if side.startswith("LONG") else -quantity
            entries[user_id] = float(str(row["avg_px_open"]))
            realized += float(str(row["realized_pnl"]).split()[0])
            parts = user_id.split(".")
            is_equity = len(parts) < 2 or parts[1] in ("SSE", "SZSE")
            multiplier = (
                1
                if is_equity
                else int(_CONTRACT_SPECS.get(_underlying(parts[0]), ("1", "10", 0))[1])
            )
            multipliers[user_id] = multiplier
        snapshot = mark_to_market(
            initial_cash=float(self._account.initial_cash),
            realized_pnl=realized,
            positions=positions,
            marks=self._marks,
            entries=entries,
            multipliers=multipliers,
            margin_account=self._account.market != "CN_A",
        )
        today = datetime.now(UTC).date().isoformat()
        self._repository.record_equity(
            account_id=self._account.id,
            trade_date=today,
            equity=Decimal(str(snapshot.equity)),
            cash=Decimal(str(snapshot.cash)),
            margin_used=Decimal(str(snapshot.margin_used)),
            drawdown=Decimal(str(snapshot.drawdown)),
        )
        return {"new_fills": inserted, **snapshot.payload()}

    async def _drain_engines(self, timeout: float = 10.0) -> None:
        """等引擎命令/事件队列排空：成交在对账前落进 NT 报告。

        订单事件经 call_soon + 队列任务异步处理；同一周期内 publish 后立刻
        reconcile 会读到空报告（成交要下个周期才可见——纯延迟，但运维页
        观感差）。排空后再对账即可消除。
        """
        assert self._node is not None
        kernel = self._node.kernel
        engines = (kernel.risk_engine, kernel.exec_engine, kernel.data_engine)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            pending = 0
            for engine in engines:
                for probe in ("cmd_qsize", "evt_qsize", "data_qsize"):
                    qsize = getattr(engine, probe, None)
                    if callable(qsize):
                        pending += int(qsize())
            if pending == 0:
                await asyncio.sleep(0.05)  # 队空≠回调已跑完，再让一拍
                return
            if loop.time() > deadline:
                self._log.warning(f"engine queues not drained (pending={pending})")
                return
            await asyncio.sleep(0.05)

    def _request_warmup(self) -> None:
        """经 NT 历史数据通道预热：request_bars → on_historical_data。

        历史 bar 只喂指标（NT 原生语义，已实证：register_indicator_for_bars
        注册的指标会被历史 bar 更新），不进入 on_bar、不产生订单流。水位线
        已提前到最新，后续 poll 只推真正的新 bar。
        """
        starts = self._poller.prime()
        for strategy, bar_type, instrument_id in self._strategy_bar_types:
            start = starts.get(instrument_id)
            if start is None:
                continue
            strategy.request_bars(bar_type, start=start)

    async def run_until(self, stop: asyncio.Event) -> None:
        """Run poll→publish→reconcile cycles until ``stop`` is set.

        节点必须在运行中的事件循环内构建：TradingNode 构造时通过
        ``asyncio.get_event_loop()`` 绑定 loop，引擎的命令/事件队列消费协程
        在该 loop 上调度。若在同步上下文提前 build（循环外的默认 loop），
        队列任务永远不会被调度——K 线照流（msgbus 同步派发），但订单命令
        无人消费，全部停在 INITIALIZED。
        """
        self.check_restart_safe()
        try:
            node = self._node or self.build()
        except Exception as exc:  # noqa: BLE001
            # 启动失败（如策略代码无法加载）也落库，供运维页显示真实原因。
            self._persist_run_state(status="ERROR", last_error=str(exc))
            raise
        node_task = asyncio.create_task(node.run_async())
        try:
            deadline = asyncio.get_running_loop().time() + 60
            while not node.is_running():
                if asyncio.get_running_loop().time() > deadline:
                    raise RuntimeError("paper node failed to reach RUNNING state")
                if node_task.done():
                    task_error = node_task.exception()
                    if task_error is not None:
                        raise task_error
                await asyncio.sleep(0.5)
            self._log.info(f"paper node running for {self._account.id}")
            self._request_warmup()
            await self._drain_engines()
            while not stop.is_set():
                try:
                    if self._kill_switch_sessions is not None and kill_switch_tripped(
                        self._kill_switch_sessions
                    ):
                        self._log.warning("kill switch TRIPPED — cycle skipped")
                        self._monitor.record_error("kill_switch_tripped")
                    else:
                        polled = self._poller.poll()
                        for item in polled:
                            self._publish(item)
                        self._monitor.record_bars(count=len(polled))
                        await self._drain_engines()
                        self.reconcile()
                        self._monitor.record_cycle()
                        self._persist_run_state(
                            status=("LIVE" if self._poller.warmed_up else "WARMUP"),
                            last_error=None,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("poll cycle failed: %s", exc)
                    self._monitor.record_error(str(exc))
                    self._persist_run_state(status="ERROR", last_error=str(exc))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._poll_interval)
        finally:
            node.stop()
            await asyncio.sleep(1)
            node.dispose()


def warmup_bars_for(frequency: str) -> int:
    return _WARMUP_BY_FREQUENCY.get(frequency, 0)


__all__ = [
    "ChinaVenueSandboxExecFactory",
    "PaperNodeRunner",
    "StrategyLoadError",
    "exec_factory_for",
    "warmup_bars_for",
]
