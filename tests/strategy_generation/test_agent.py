"""Tests for the natural-language strategy agent (mocked runner)."""

from __future__ import annotations

import json

from quant_platform.strategy_generation.agent import run_turn
from quant_platform.strategy_generation.schemas import StrategyMessage

_VALID = {
    "title": "MA cross",
    "explanation": "Buy when the 5-day MA crosses above the 20-day MA.",
    "question": "",
    "code": (
        "INDICATORS = [{\"key\": \"ma5\", \"type\": \"sma\", \"period\": 5}]\n"
        "def compute_signal(ctx):\n"
        "    if not ctx.ready:\n"
        "        return Signal(target_qty=0)\n"
        "    return Signal(target_qty=1)\n"
    ),
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


def test_run_turn_retries_when_explanation_empty() -> None:
    """explanation 为空（min_length=1 校验失败）时触发一次修正重试。"""
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps({**_VALID, "explanation": ""})
        return json.dumps(_VALID)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="用1小时K线")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.explanation == _VALID["explanation"]


def test_run_turn_prompt_includes_market() -> None:
    captured: list[str] = []

    def capture(prompt: str) -> str:
        captured.append(prompt)
        return json.dumps(
            {**_VALID, "explanation": "金叉开多，死叉平多并反手开空。"}
        )

    run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="均线金叉")],
        runner=capture,
    )
    assert "CN_COMMODITY_FUTURES" in captured[0]


def test_run_turn_prompt_includes_current_state() -> None:
    """当前草稿状态（标的/周期/代码）必须注入提示词，防止 agent 漂移标的。"""
    captured: list[str] = []

    def capture(prompt: str) -> str:
        captured.append(prompt)
        return json.dumps({**_VALID_FUTURES, "instrument_ids": ["P8888.DCE"]})

    run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="获取数据")],
        runner=capture,
        state={
            "instrument_ids": ["P8888.DCE"],
            "frequency": "1d",
            "code": "INDICATORS = []",
        },
    )
    assert "PRESERVE" in captured[0]
    assert "P8888.DCE" in captured[0]
    assert "INDICATORS = []" in captured[0]


_VALID_FUTURES = {
    **_VALID,
    "instrument_ids": ["SA701.CZC"],
    "explanation": "金叉开多，死叉平多并反手开空。",
}


def test_instrument_9999_continuous_code_rejected_and_retried() -> None:
    """连续合约写成 9999（不可拉取）时打回重生成，改用 8888 约定。"""
    bad = {**_VALID_FUTURES, "instrument_ids": ["SA9999.CZC"]}
    good = {**_VALID_FUTURES, "instrument_ids": ["SA8888.CZC"]}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps(bad)
        return json.dumps(good)

    output = run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="用纯碱连续合约")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.instrument_ids == ["SA8888.CZC"]


def test_instrument_8888_continuous_code_accepted() -> None:
    """iFinD 的 8888 连续约定直接放行。"""
    good = {**_VALID_FUTURES, "instrument_ids": ["RB8888.SHF"]}

    output = run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="用螺纹主力")],
        runner=lambda _p: json.dumps(good),
    )
    assert output.instrument_ids == ["RB8888.SHF"]


def test_market_instrument_mismatch_is_retried() -> None:
    """A 股市场不能生成商品期货标的，避免回测套用错误费用模型。"""
    bad = {**_VALID_FUTURES, "instrument_ids": ["SA8888.CZC"]}
    good = {**_VALID, "instrument_ids": ["600000.SH"]}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        return json.dumps(bad if len(calls) == 1 else good)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="做纯碱期货")],
        runner=flaky,
    )

    assert len(calls) == 2
    assert output.instrument_ids == ["600000.SH"]


def test_system_prompt_states_8888_continuous_convention() -> None:
    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    assert "SA8888.CZC" in prompt
    assert "8888" in prompt
    assert "9999" in prompt


def test_system_prompt_requires_directional_clarity() -> None:
    """双边策略提示词必须要求区分开多/开空、平多/平空。"""
    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    assert "开多" in prompt
    assert "开空" in prompt
    assert "平多" in prompt
    assert "平空" in prompt


def test_two_sided_explanation_without_direction_retried() -> None:
    """期货策略 explanation 只写『开仓/平仓』时打回重生成。"""
    ambiguous = {**_VALID, "explanation": "金叉时开仓，死叉时平仓。"}
    directional = {**_VALID, "explanation": "金叉时开多，死叉时平多并反手开空。"}
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        if len(calls) == 1:
            return json.dumps(ambiguous)
        return json.dumps(directional)

    output = run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="均线金叉")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert "开多" in output.explanation
    assert "开空" in output.explanation


def test_two_sided_explanation_english_directional_words_pass() -> None:
    """英文 explanation 含 open/close long/short 也算方向明确。"""
    directional = {
        **_VALID,
        "explanation": "Open long on golden cross; close long and open short "
        "on death cross.",
    }

    output = run_turn(
        market="CN_COMMODITY_FUTURES",
        history=[StrategyMessage(role="user", content="均线金叉")],
        runner=lambda _p: json.dumps(directional),
    )
    assert output.ready is True


def test_long_only_market_allows_bare_open_close_wording() -> None:
    """A股（只能做多）开仓/平仓无歧义，不要求方向词。"""
    bare = {**_VALID, "explanation": "金叉时开仓，死叉时平仓。"}

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="均线金叉")],
        runner=lambda _p: json.dumps(bare),
    )
    assert output.explanation == bare["explanation"]


def test_system_prompt_lists_nt_indicators() -> None:
    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    assert "sma(period)" in prompt
    assert "macd(fast, slow, signal=9)" in prompt
    assert "adx(period)" in prompt
    assert "bollinger(period, k=2)" in prompt


def test_system_prompt_describes_signal_spec() -> None:
    from quant_platform.strategy_generation.agent import _build_system_prompt

    prompt = _build_system_prompt()
    assert "INDICATORS" in prompt
    assert "compute_signal" in prompt
    assert "Signal(target_qty" in prompt
    assert "ctx.ready" in prompt


def test_run_turn_retries_when_missing_indicators() -> None:
    """信号文件缺 INDICATORS 时触发一次自动修正重试。"""
    bad = {
        **_VALID,
        "code": "def compute_signal(ctx):\n    return Signal(target_qty=1)\n",
    }
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        return json.dumps(bad if len(calls) == 1 else _VALID)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == _VALID["code"]


def test_run_turn_retries_when_uses_pipeline_api() -> None:
    """信号代码使用管道 API（order_factory/submit_order）时触发修正重试。"""
    bad = {
        **_VALID,
        "code": (
            "INDICATORS = []\n"
            "def compute_signal(ctx):\n"
            "    order = self.order_factory.market(instrument_id='x', "
            "order_side=OrderSide.BUY, quantity=1)\n"
            "    self.submit_order(order)\n"
            "    return Signal(target_qty=0)\n"
        ),
    }
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        return json.dumps(bad if len(calls) == 1 else _VALID)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == _VALID["code"]


def test_run_turn_retries_when_imports() -> None:
    """信号代码 import/class 时触发修正重试（隔离契约）。"""
    bad = {
        **_VALID,
        "code": (
            "import os\n"
            "INDICATORS = []\n"
            "def compute_signal(ctx):\n"
            "    return Signal(target_qty=0)\n"
        ),
    }
    calls: list[str] = []

    def flaky(_prompt: str) -> str:
        calls.append(_prompt)
        return json.dumps(bad if len(calls) == 1 else _VALID)

    output = run_turn(
        market="CN_A",
        history=[StrategyMessage(role="user", content="x")],
        runner=flaky,
    )
    assert len(calls) == 2
    assert output.code == _VALID["code"]
