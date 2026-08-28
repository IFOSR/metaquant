"""Tests for China-market sandbox venue assembly."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quant_platform.markets.nt.fees import AShareFeeModel
from quant_platform.markets.nt.futures_fee import FuturesFeeModel
from quant_platform.paper.sim_venue import (
    PAPER_FUTURES_FEE_SCHEDULE,
    account_type_for_market,
    fee_model_for_market,
    sandbox_config_for,
    venue_for_instrument,
)


@pytest.mark.parametrize(
    ("instrument_id", "venue"),
    [
        ("600000.SH", "SSE"),
        ("000001.SZ", "SZSE"),
        ("RB2610.SHF", "SHFE"),
        ("AU2612.INE", "INE"),
        ("M2609.DCE", "DCE"),
        ("TA609.CZC", "CZCE"),
        ("LC2509.GFE", "GFEX"),
    ],
)
def test_venue_for_instrument(instrument_id: str, venue: str) -> None:
    assert venue_for_instrument(instrument_id) == venue


def test_venue_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="unsupported instrument_id"):
        venue_for_instrument("AAPL.US")


def test_fee_model_per_market() -> None:
    assert isinstance(fee_model_for_market("CN_A"), AShareFeeModel)
    futures_model = fee_model_for_market("CN_COMMODITY_FUTURES")
    assert isinstance(futures_model, FuturesFeeModel)
    with pytest.raises(ValueError, match="unsupported market"):
        fee_model_for_market("US")


def test_account_type_per_market() -> None:
    assert account_type_for_market("CN_A") == "CASH"
    assert account_type_for_market("CN_COMMODITY_FUTURES") == "MARGIN"


def test_sandbox_config_mapping() -> None:
    config = sandbox_config_for(
        "CN_A",
        instrument_ids=("600000.SH",),
        initial_cash=Decimal("1000000"),
    )
    assert config.venue == "SSE"
    assert config.account_type == "CASH"
    assert config.starting_balances == ["1000000 CNY"]
    assert config.base_currency == "CNY"
    assert config.bar_execution is True

    futures_config = sandbox_config_for(
        "CN_COMMODITY_FUTURES",
        instrument_ids=("RB2610.SHF",),
        initial_cash=Decimal("1000000"),
    )
    assert futures_config.venue == "SHFE"
    assert futures_config.account_type == "MARGIN"


def test_sandbox_config_requires_instruments() -> None:
    with pytest.raises(ValueError, match="at least one instrument"):
        sandbox_config_for("CN_A", instrument_ids=(), initial_cash=Decimal("1000000"))


def test_futures_fee_schedule_present() -> None:
    rates = PAPER_FUTURES_FEE_SCHEDULE.rates
    assert rates  # 平今/平昨两档齐备（FeeSchedule 构造已校验）


def test_futures_fee_model_charges_close_offsets() -> None:
    """FuturesFeeModel 挂载后按 tag 区分平今平昨（引擎语义冒烟）。"""
    from nautilus_trader.common.component import TestClock
    from nautilus_trader.common.factories import OrderFactory
    from nautilus_trader.model.enums import OrderSide
    from nautilus_trader.model.identifiers import StrategyId, TraderId

    from quant_platform.markets.nt.instruments import futures_contract

    instrument = futures_contract(
        symbol="RB2610",
        venue="SHFE",
        underlying="RB",
        price_increment="1",
        multiplier="10",
        price_precision=0,
        activation_ns=0,
        expiration_ns=9_999_999_999_999_999_999,
    )
    factory = OrderFactory(
        trader_id=TraderId("TESTER-001"),
        strategy_id=StrategyId("S-001"),
        clock=TestClock(),
    )
    model = fee_model_for_market("CN_COMMODITY_FUTURES", multiplier=Decimal("10"))
    assert isinstance(model, FuturesFeeModel)
    order = factory.market(
        instrument_id=instrument.id,
        order_side=OrderSide.SELL,
        quantity=instrument.make_qty(1),
        tags=["close_offset=CLOSE_TODAY"],
    )
    fee = model.get_commission(
        order,
        instrument.make_qty(1),
        instrument.make_price("4000"),
        instrument,
    )
    assert float(str(fee).split()[0]) == pytest.approx(10.0)


def test_connect_subscribes_bar_feed_with_segment_safe_pattern() -> None:
    """回归：bar topic 中 venue 嵌在第四段，NT 通配符按点分段匹配，

    母类订阅的 ``data.*.SHFE.*`` 永远匹配不到
    ``data.bars.RB2610.SHFE-5-MINUTE-LAST-EXTERNAL``——撮合引擎收不到行情，
    所有订单以 ``no market`` 拒单。connect 必须额外订阅 ``data.bars.*``。
    """
    from unittest.mock import MagicMock

    from quant_platform.paper.sim_venue import BAR_DATA_TOPIC, subscribe_bar_feed

    msgbus = MagicMock()
    handler = object()
    subscribe_bar_feed(msgbus, handler)

    msgbus.subscribe.assert_called_once_with(BAR_DATA_TOPIC, handler=handler)
    assert BAR_DATA_TOPIC == "data.bars.*"


def test_bar_data_topic_matches_nautilus_wildcard_semantics() -> None:
    """用 NT 真实的匹配函数验证订阅模式能命中我们的 bar topic。"""
    from nautilus_trader.common.component import is_matching_py

    topic = "data.bars.RB2610.SHFE-5-MINUTE-LAST-EXTERNAL"
    assert is_matching_py(topic, "data.bars.*")
    # 母类模式按段匹配，命中不了 bar topic（回归证据，勿删）
    assert not is_matching_py(topic, "data.*.SHFE.*")
