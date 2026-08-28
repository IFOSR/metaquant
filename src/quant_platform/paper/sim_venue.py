"""China-market sandbox execution for paper accounts.

NautilusTrader's stock ``SandboxExecutionClient`` hardcodes a
``MakerTakerFeeModel`` (crypto-venue semantics). Paper accounts must use the
platform's single source of truth in ``markets/`` — A-share
commission/stamp-duty/transfer fees, futures close-today/close-yesterday
schedules, CASH vs MARGIN account types — so this module rebuilds the
simulated venue with the correct models while keeping the sandbox client's
wiring intact.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
from nautilus_trader.adapters.sandbox.execution import (  # type: ignore[attr-defined]
    SandboxExecutionClient,
    account_type_from_str,
    book_type_from_str,
    oms_type_from_str,
)
from nautilus_trader.backtest.engine import SimulatedExchange
from nautilus_trader.backtest.execution_client import BacktestExecClient
from nautilus_trader.backtest.models import FeeModel, FillModel, LatencyModel
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus, TestClock
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.identifiers import AccountId, ClientId, Venue
from nautilus_trader.model.objects import Currency, Money

from quant_platform.markets.futures import CloseOffset, FeeRate, FeeSchedule
from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.futures_fee import FuturesFeeModel

# 演示费率（每手，CNY）；正式应从市场规则层 TradingRuleVersion 取。
PAPER_FUTURES_FEE_SCHEDULE = FeeSchedule(
    {
        CloseOffset.CLOSE_TODAY: FeeRate(per_lot=Decimal("10")),
        CloseOffset.CLOSE_YESTERDAY: FeeRate(per_lot=Decimal("2")),
    }
)

# NT msgbus 通配符按点分段匹配；bar topic 需要独立订阅（见 connect）。
BAR_DATA_TOPIC = "data.bars.*"


def subscribe_bar_feed(msgbus: MessageBus, handler: Any) -> None:
    """订阅全部 K 线 topic，把行情转发给撮合引擎。"""
    msgbus.subscribe(BAR_DATA_TOPIC, handler=handler)


_VENUE_BY_SUFFIX = {
    "SH": "SSE",
    "SSE": "SSE",
    "SZ": "SZSE",
    "SZSE": "SZSE",
    "SHF": "SHFE",
    "INE": "INE",
    "DCE": "DCE",
    "CZC": "CZCE",
    "CZCE": "CZCE",
    "GFE": "GFEX",
    "GFEX": "GFEX",
}


def venue_for_instrument(instrument_id: str) -> str:
    """``600000.SH`` → ``SSE``；``RB2610.SHF`` → ``SHFE``。"""
    symbol, _, suffix = instrument_id.partition(".")
    venue = _VENUE_BY_SUFFIX.get(suffix.upper())
    if venue is None or not symbol:
        raise ValueError(f"unsupported instrument_id: {instrument_id}")
    return venue


def fee_model_for_market(
    market: str,
    *,
    multiplier: Decimal | None = None,
) -> FeeModel:
    if market == "CN_A":
        return AShareFeeModel()
    if market == "CN_COMMODITY_FUTURES":
        return FuturesFeeModel(PAPER_FUTURES_FEE_SCHEDULE, multiplier=multiplier)
    raise ValueError(f"unsupported market: {market}")


def account_type_for_market(market: str) -> str:
    """A 股为现金账户，期货为保证金账户。"""
    return "CASH" if market == "CN_A" else "MARGIN"


def sandbox_config_for(
    market: str,
    *,
    instrument_ids: tuple[str, ...],
    initial_cash: Decimal,
) -> SandboxExecutionClientConfig:
    """Build the sandbox exec config bound to the first instrument's venue."""
    if not instrument_ids:
        raise ValueError("sandbox venue requires at least one instrument")
    venue = venue_for_instrument(instrument_ids[0])
    return SandboxExecutionClientConfig(
        venue=venue,
        starting_balances=[f"{initial_cash} CNY"],
        base_currency="CNY",
        oms_type="NETTING",
        account_type=account_type_for_market(market),
        default_leverage=Decimal(1),
        bar_execution=True,
        trade_execution=False,
        reject_stop_orders=True,
        support_gtd_orders=True,
        support_contingent_orders=False,
        use_position_ids=True,
        use_random_ids=False,
        use_reduce_only=False,
    )


class ChinaVenueSandboxExecutionClient(SandboxExecutionClient):
    """沙箱执行客户端，撮合所使用 markets/ 的中国市场费率模型。

    复刻 NT 1.231 ``SandboxExecutionClient.__init__`` 的装配顺序，仅把
    ``MakerTakerFeeModel`` 替换为调用方传入的费率模型（版本 pin 住，
    升级 NT 时需复核此文件）。
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        portfolio: object,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        config: SandboxExecutionClientConfig,
        fee_model: FeeModel,
        fill_model: FillModel | None = None,
    ) -> None:
        venue = Venue(config.venue)
        oms_type = oms_type_from_str(config.oms_type)
        account_type = account_type_from_str(config.account_type)
        base_currency = (
            Currency.from_str(config.base_currency) if config.base_currency else None
        )

        self.test_clock = TestClock()

        LiveExecutionClient.__init__(
            self,
            loop=loop,
            client_id=ClientId(config.venue),
            venue=venue,
            oms_type=oms_type,
            account_type=account_type,
            base_currency=base_currency,
            instrument_provider=InstrumentProvider(),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=None,
        )

        self._set_account_id(AccountId(f"{config.venue}-001"))

        self.exchange = SimulatedExchange(
            venue=venue,
            oms_type=oms_type,
            account_type=account_type,
            starting_balances=[Money.from_str(b) for b in config.starting_balances],
            base_currency=base_currency,
            default_leverage=config.default_leverage,
            leverages=config.leverages or {},
            modules=[],
            portfolio=portfolio,
            msgbus=self._msgbus,
            cache=cache,
            clock=self.test_clock,
            fill_model=fill_model or FillModel(),
            fee_model=fee_model,
            latency_model=LatencyModel(0),
            book_type=book_type_from_str(config.book_type),
            frozen_account=config.frozen_account,
            bar_execution=config.bar_execution,
            trade_execution=config.trade_execution,
            reject_stop_orders=config.reject_stop_orders,
            support_gtd_orders=config.support_gtd_orders,
            support_contingent_orders=config.support_contingent_orders,
            use_position_ids=config.use_position_ids,
            use_random_ids=config.use_random_ids,
            use_reduce_only=config.use_reduce_only,
            use_message_queue=False,  # 实时路径不使用内部消息队列
        )

        self._client = BacktestExecClient(
            exchange=self.exchange,
            msgbus=msgbus,
            cache=cache,
            clock=self.test_clock,
        )

        self.exchange.register_client(self._client)
        self.exchange.initialize_account()

    def connect(self) -> None:
        """连接并补上按段匹配的 K 线订阅。

        NT 的 msgbus 通配符按点分段匹配：bar topic 形如
        ``data.bars.RB2610.SHFE-5-MINUTE-LAST-EXTERNAL``，venue 嵌在第四段
        里，母类订阅的 ``data.*.SHFE.*`` 匹配不到（该模式只覆盖 tick 类
        topic）。缺了这条订阅，撮合引擎永远收不到行情，所有订单被以
        ``no market`` 拒单。
        """
        super().connect()
        subscribe_bar_feed(self._msgbus, self.on_data)
