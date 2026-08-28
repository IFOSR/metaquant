"""Tests for the natural-language strategy agent (mocked runner)."""

from __future__ import annotations

import json

from quant_platform.strategy_generation.agent import run_turn
from quant_platform.strategy_generation.schemas import StrategyMessage

_VALID = {
    "title": "MA cross",
    "explanation": "Buy when the 5-day MA crosses above the 20-day MA.",
    "question": "",
    "code": "class MAStrategy(Strategy): ...",
    "ready": True,
}


def _ok(_prompt: str) -> str:
    return json.dumps(_VALID)


def test_run_turn_parses_agent_output() -> None:
    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="均线金叉买入")],
        runner=_ok,
    )
    assert output.title == "MA cross"
    assert output.ready is True
    assert output.code is not None


def test_run_turn_retries_on_invalid_json() -> None:
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return "not json at all"
        return json.dumps(_VALID)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert output.title == "MA cross"
    assert len(calls) == 2


def test_run_turn_prompt_includes_market() -> None:
    captured: list[str] = []

    def capture(prompt: str) -> str:
        captured.append(prompt)
        return json.dumps(_VALID)

    run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="均线金叉")],
        runner=capture,
    )
    assert "CN_COMMODITY_FUTURES" in captured[0]


def test_system_prompt_lists_nt_indicators() -> None:
    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    assert "ExponentialMovingAverage" in prompt
    assert "MovingAverageConvergenceDivergence" in prompt
    assert "BollingerBands" in prompt


def test_system_prompt_injects_real_today() -> None:
    """提示词必须注入真实当前日期，否则 LLM 以训练截止日为锚推时间段。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    assert today in prompt
    assert "{today}" not in prompt  # 占位符已全部替换


def test_run_turn_retries_when_order_not_submitted() -> None:
    """生成代码创建了订单但没 submit_order 时，触发一次自动修正重试。"""
    bad_code = (
        "class S(Strategy):\n"
        "    def on_bar(self, bar):\n"
        "        order = self.order_factory.market(\n"
        "            instrument_id=self._instrument_id,\n"
        "            order_side=OrderSide.BUY,\n"
        "            quantity=instrument.make_qty(100),\n"
        "        )\n"
    )
    good = {**_VALID, "code": "... make_qty(100) ... self.submit_order(order)"}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps({**_VALID, "code": bad_code})
        return json.dumps(good)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == good["code"]


def test_run_turn_retries_when_subscribe_bars_has_instrument() -> None:
    """subscribe_bars 误传 instrument_id 时触发自动修正重试。"""
    bad_code = (
        "class S(Strategy):\n"
        "    def on_start(self):\n"
        "        self.subscribe_bars(self._bar_type, self._instrument_id)\n"
        "    def on_bar(self, bar):\n"
        "        order = self.order_factory.market(\n"
        "            instrument_id=self._instrument_id,\n"
        "            order_side=OrderSide.BUY,\n"
        "            quantity=instrument.make_qty(100),\n"
        "        )\n"
        "        self.submit_order(order)\n"
    )
    good = {**_VALID, "code": "... make_qty(100) ... self.submit_order(order)"}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps({**_VALID, "code": bad_code})
        return json.dumps(good)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == good["code"]


def test_run_turn_retries_when_config_class_attr_read() -> None:
    """从配置类读类属性会崩 indicator 构造，应触发一次自动修正重试。"""
    bad_code = (
        "class MyConfig(StrategyConfig):\n"
        "    ma_period: int = 20\n"
        "class S(Strategy):\n"
        "    def __init__(self, instrument_id, bar_type_str):\n"
        "        super().__init__(StrategyConfig(strategy_id='GEN'))\n"
        "        self.ma = SimpleMovingAverage(MyConfig.ma_period)\n"
    )
    good = {**_VALID, "code": "... SimpleMovingAverage(20) ..."}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps({**_VALID, "code": bad_code})
        return json.dumps(good)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == good["code"]
