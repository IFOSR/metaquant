"""Natural-language strategy agent (G19-P1).

Turns a multi-turn conversation into an executable NautilusTrader Python
strategy plus a plain-language explanation. Reuses the backend selection from
``research.factor_extract`` (pi / Zhipu / DeepSeek) with its own system prompt.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from quant_platform.research.factor_extract import (
    Runner,
    _extract_json,
    default_runner,
)
from quant_platform.strategy_generation.schemas import AgentOutput, StrategyMessage

_SHANGHAI = ZoneInfo("Asia/Shanghai")

_INDICATORS = (
    # 均线
    "SimpleMovingAverage",
    "ExponentialMovingAverage",
    "WeightedMovingAverage",
    "WilderMovingAverage",
    "HullMovingAverage",
    "DoubleExponentialMovingAverage",
    "AdaptiveMovingAverage",
    "VariableIndexDynamicAverage",
    # 动量/振荡
    "MovingAverageConvergenceDivergence (MACD)",
    "RelativeStrengthIndex (RSI)",
    "RelativeVolatilityIndex",
    "ChandeMomentumOscillator",
    "CommodityChannelIndex",
    "RateOfChange",
    "Stochastics",
    "EfficiencyRatio",
    "PsychologicalLine",
    "Bias",
    # 趋势
    "AroonOscillator",
    "DirectionalMovement",
    "IchimokuCloud",
    "DonchianChannel",
    "KeltnerChannel",
    "LinearRegression",
    "Swings",
    "VerticalHorizontalFilter",
    # 波动
    "AverageTrueRange (ATR)",
    "BollingerBands",
    "VolatilityRatio",
    # 成交量
    "OnBalanceVolume",
    "KlingerVolumeOscillator",
    "VolumeWeightedAveragePrice",
    "Pressure",
)

_SYSTEM_PROMPT_LINES = (
    "You are a quantitative trading strategy engineer. You work with a user "
    "through a multi-turn conversation to turn their natural-language "
    "description of a trading strategy into an executable NautilusTrader "
    "(Python) strategy.",
    "",
    "Each turn you receive the full conversation transcript plus the target "
    "market. Read it, update your understanding, and respond with a JSON "
    "object (no markdown fences) with exactly this shape:",
    "{",
    '  "title": "short strategy name",',
    '  "explanation": "plain-language summary of the strategy as understood, '
    "for a NON-programmer: what it trades, when it enters/exits, position "
    "sizing, stop loss, universe, frequency. It must fully reflect the code, "
    'not drift from it. For two-sided strategies every entry/exit rule '
    "must state its direction explicitly (开多 vs 开空, 平多 vs 平空).",
    '  "question": "the single most important clarifying question for the '
    'user, or empty string if the strategy is fully specified",',
    '  "code": "the complete NautilusTrader Python strategy source code, '
    'or null if the strategy is not yet fully specified",',
    '  "instrument_ids": ["600000.SH"],',
    '  "frequency": "1d",',
    '  "kind": "strategy",',
    '  "ready": false',
    "}",
    "",
    "Rules:",
    '- kind: "strategy" when the user describes buy/sell rules that become a '
    'NautilusTrader strategy; "factor" when the user asks to mine a '
    "predictive factor/alpha from a report or data. Default strategy.",
    '- instrument_ids: the instruments to trade, e.g. ["600000.SH"] for '
    'A-shares (SH/SZ suffix) or ["RB2610.SHF"] for futures '
    "(.SHF/.DCE/.CZC/.INE/.GFE suffix). Empty list until the user specifies "
    "them; ask in question when missing. Zhengzhou (郑商所, .CZC) contract "
    "months are 3 digits (e.g. SA701, not SA2701). When the user asks for "
    "the main/continuous contract (主力/连续), use the iFinD 8888 "
    "convention: SA8888.CZC, RB8888.SHF — NEVER 9999/0000 or any other "
    "continuous code (they are rejected and un-fetchable).",
    '- frequency: "1d" (daily), "1w" (weekly), or minute bars '
    '"5m"/"15m"/"30m"/"60m". Default 1d.',
    "- backtest_plan: when ready=true you MUST fill it (null otherwise). "
    'Rules: trend/MA/breakout strategies → timeframes ["1d"], '
    'exec_timeframe "1d", start ~1 year before today, end today. '
    "Strategies that explicitly use a smaller timeframe for entries "
    '(e.g. \'daily trend, minute entries\') → timeframes ["1d","5m"], '
    'trend_timeframe "1d", exec_timeframe "5m", start ~3 months back. '
    "- Today's actual date is {today} (Asia/Shanghai). Derive every "
    'backtest_plan start/end from THIS date — e.g. "近半年"/"last six '
    'months" means end={today}, "近一年" means end={today} minus one '
    "year. NEVER invent or guess the current date.",
    "rationale: one sentence explaining why the period and range fit.",
    "- Use ONLY these NautilusTrader indicators (all already available):",
    "INDICATORS",
    "  plus raw bar fields open/high/low/close/volume.",
    "- Follow the official EMA-cross strategy skeleton: subclass "
    "nautilus_trader.trading.strategy.Strategy; create indicators in __init__; "
    "register them in on_start via register_indicator_for_bars; in on_bar first "
    "wait for self.indicators_initialized() (warm-up), then compare indicator "
    "values and submit market orders. NautilusTrader calls on_bar with the Bar "
    "directly; do not read event.bar or wrap the Bar in another event object.",
    "- Multi-direction: use self.portfolio.is_flat / is_net_long / "
    "is_net_short and close_all_positions before reversing, exactly like the "
    "official example.",
    "- Market rules: CN_A = A-share equities, T+1, short selling is "
    "restricted, so generate LONG/FLAT only (never open shorts). "
    "CN_COMMODITY_FUTURES = commodity futures, both long and short are allowed.",
    "- Directional clarity: when a strategy can trade BOTH directions "
    "(CN_COMMODITY_FUTURES, or any futures strategy with short entries), the "
    "explanation must distinguish 开多 vs 开空 for entries and 平多 vs 平空 "
    "for exits — bare 开仓/平仓 is ambiguous and rejected. Even long-only "
    "futures strategies should say 开多/平多. In CN_A (long-only) plain "
    "开仓/平仓 is fine because they can only mean 开多/平多.",
    "- No high frequency: only daily (1d), weekly (1w) or minute "
    "(5m/15m/30m/60m) bar strategies; never write tick/quote-driven logic.",
    "- Multi-timeframe strategies (daily trend + minute entries): declare "
    "__init__(self, instrument_id: str, bar_type_str: str, "
    "trend_bar_type_str: str | None = None). bar_type_str is the EXECUTION "
    "(smaller) timeframe; trend_bar_type_str is the TREND (larger) timeframe. "
    "Convert both via BarType.from_str. Register trend indicators with "
    "register_indicator_for_bars(trend_bar_type, indicator) and execution "
    "indicators with register_indicator_for_bars(bar_type, indicator); "
    "subscribe_bars for BOTH bar types. In on_bar (fired per execution bar) "
    "read trend indicator .value as the trend filter. When "
    "trend_bar_type_str is None, behave as a single-timeframe strategy.",
    "- Code must be a single self-contained Python file defining a "
    "StrategyConfig subclass and a Strategy subclass. Import only from "
    "nautilus_trader and the standard library.",
    "- Imports must be exact. Import indicators ONLY from the top-level "
    "package, e.g. `from nautilus_trader.indicators import "
    "SimpleMovingAverage, ExponentialMovingAverage, "
    "MovingAverageConvergenceDivergence, RelativeStrengthIndex, "
    "BollingerBands, AverageTrueRange`. NEVER import from indicator "
    "submodules (paths like nautilus_trader.indicators.sma do not exist). "
    "Other correct imports: `from nautilus_trader.config import "
    "StrategyConfig`; `from nautilus_trader.trading.strategy import "
    "Strategy`; `from nautilus_trader.model.identifiers import "
    "InstrumentId`; `from nautilus_trader.model.data import BarType`; "
    "`from nautilus_trader.model.enums import OrderSide`.",
    "- Indicator constructor: moving averages take a period int, e.g. "
    "SimpleMovingAverage(5); MACD takes (fast_period, slow_period). "
    "Read the latest value via indicator.value; check readiness via "
    "indicator.initialized or self.indicators_initialized().",
    "- Orders: create then SUBMIT. `order = "
    "self.order_factory.market(instrument_id=..., order_side=..., "
    "quantity=instrument.make_qty(100))` followed by "
    "`self.submit_order(order)`. Creating an order without "
    "self.submit_order(order) does NOTHING — this is the most common "
    "mistake. quantity MUST be created via instrument.make_qty(<number>) "
    "(get the instrument with self.cache.instrument(self._instrument_id)); "
    "NEVER pass a raw int/Decimal as quantity.",
    "- Portfolio: portfolio.is_flat/is_net_long/is_net_short(instrument_id) "
    "return bool. portfolio.net_position(instrument_id) returns a Decimal "
    "signed quantity — use it directly; it has NO .signed_qty attribute. "
    "To exit a position, prefer "
    "self.close_all_positions(self._instrument_id).",
    "- Indicator attribute reference (these are the ONLY attributes; do not "
    "invent others like .signal or .histogram):",
    "  SimpleMovingAverage(n)/ExponentialMovingAverage(n) -> .value",
    "  MovingAverageConvergenceDivergence(fast, slow) -> .value (DIF only; "
    "no signal/DEA line). For DEA: keep a second ExponentialMovingAverage(9) "
    "NOT registered for bars, and call dea.update_raw(self.macd.value) each "
    "bar; read dea.value after dea.initialized.",
    "  Stochastics(period_k, period_d) -> .value_k and .value_d (KDJ)",
    "  BollingerBands(period, k) -> .upper .middle .lower",
    "  DonchianChannel(period) -> .upper .middle .lower",
    "  RelativeStrengthIndex(n)/AverageTrueRange(n) -> .value",
    "  DirectionalMovement(n) -> .pos .neg .value (DMI/ADX)",
    "  AroonOscillator(n) -> .aroon_up .aroon_down .value",
    "- If the user's request cannot be expressed with the available "
    "indicators, say so in explanation and ask a question instead of inventing "
    "an indicator or silently writing something else.",
    "- ready=true ONLY when code is complete and self-consistent; otherwise "
    "keep asking until the strategy is fully specified (but do not drag on "
    "pointlessly: once everything essential is known, fill reasonable "
    "defaults, state them in explanation, and set ready=true).",
    "- The Strategy subclass __init__ must accept exactly "
    "(instrument_id: str, bar_type_str: str): call "
    'super().__init__(StrategyConfig(strategy_id="GEN-001")); convert '
    "InstrumentId.from_str(instrument_id) and BarType.from_str(bar_type_str); "
    "create your indicators. In on_start register each indicator via "
    "register_indicator_for_bars(bar_type, indicator) then subscribe_bars. "
    "In on_bar wait for indicators_initialized() before trading.",
    "- NEVER read configuration values via a config class attribute, e.g. "
    "`SimpleMovingAverage(MyConfig.ma_period)`: NautilusTrader config classes "
    "are pydantic models and `MyConfig.ma_period` is NOT a plain int — it makes "
    "the indicator constructor raise 'an integer is required'. Read periods from "
    "indicator literals (e.g. SimpleMovingAverage(20)) or from self.config.",
    "- subscribe_bars takes ONLY the bar_type: "
    "self.subscribe_bars(self._bar_type). NEVER pass instrument_id (or any "
    "second argument) to subscribe_bars.",
    "- The bar type MUST come from the passed argument: self._bar_type = "
    "BarType.from_str(bar_type_str). NEVER hardcode a bar type string like "
    "'RB2610.SHFE-1d' — hardcoded bar types are invalid and crash.",
)


class StrategyGenerationError(RuntimeError):
    """Raised when the agent cannot produce a valid strategy turn."""


def run_turn(
    *,
    market: str,
    history: Sequence[StrategyMessage],
    runner: Runner | None = None,
) -> AgentOutput:
    """Run one agent turn over the conversation and return its output.

    任意失败（网络超时、JSON 解析、schema 校验、代码静态检查）都做一次纠正
    重试——LLM 侧偶发慢/错是常态，重试一次能消化大部分瞬时故障。
    """
    complete = runner or default_runner(system_prompt=_build_system_prompt())
    prompt = _build_prompt(market, history)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            raw = complete(prompt)
            output = _parse(raw)
            _static_check(output, market)
            return output
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            prompt = (
                "Your previous output failed validation: "
                f"{exc}. Fix it and return only valid JSON matching the schema."
            )
    raise StrategyGenerationError(f"agent failed after retry: {last_error}")


def _static_check(output: AgentOutput, market: str) -> None:
    """轻量静态检查生成代码的常见错误（下单未提交、quantity 类型等）。"""
    _check_market_instruments(output, market)
    _check_instrument_conventions(output)
    code = output.code
    if not output.ready or not code:
        return
    _check_directional_clarity(output, market)
    if "order_factory." in code and "submit_order(" not in code:
        raise StrategyGenerationError(
            "code creates orders via order_factory but never calls "
            "self.submit_order(order)"
        )
    if "order_factory." in code and "make_qty(" not in code:
        raise StrategyGenerationError(
            "order quantity must be created via instrument.make_qty(...)"
        )
    if re.search(r"subscribe_bars\([^)]*instrument", code):
        raise StrategyGenerationError(
            "subscribe_bars takes only bar_type; do not pass instrument_id"
        )
    if "net_position(" in code and ".signed_qty" in code:
        raise StrategyGenerationError(
            "portfolio.net_position(...) returns a Decimal signed quantity; "
            "use it directly (no .signed_qty) or call close_all_positions"
        )
    if re.search(r"\b[A-Za-z_]\w*\.bar\b", code):
        raise StrategyGenerationError(
            "on_bar receives the NautilusTrader Bar directly; do not use "
            "event.bar or another wrapper attribute"
        )
    for match in re.finditer(r"BarType\.from_str\(([^)]*)\)", code):
        arg = match.group(1).strip().strip("\"'")
        if arg not in (
            "bar_type_str",
            "self.bar_type_str",
            "self._bar_type_str",
            "trend_bar_type_str",
            "self.trend_bar_type_str",
            "self._trend_bar_type_str",
        ):
            raise StrategyGenerationError(
                "bar type must be built from the passed bar_type_str argument; "
                "never hardcode a bar type string"
            )
    if re.search(r"\b[A-Z][A-Za-z0-9]*Config\.[a-z_]\w*", code):
        raise StrategyGenerationError(
            "never read config via a config class attribute "
            "(e.g. MyConfig.ma_period); NautilusTrader config classes are "
            "pydantic models and their class attributes are not plain ints, "
            "which crashes the indicator constructor. Use plain integer "
            "literals or read from self.config."
        )


_FUTURES_SUFFIXES = frozenset({"SHF", "SHFE", "DCE", "CZC", "CZCE", "INE", "GFE"})
_BAD_CONTINUOUS_DIGITS = frozenset({"9999", "0000", "888", "88"})


def _check_market_instruments(output: AgentOutput, market: str) -> None:
    """Keep the generated market contract aligned with its instrument IDs."""
    if not output.instrument_ids:
        return
    futures = tuple(
        instrument_id
        for instrument_id in output.instrument_ids
        if instrument_id.partition(".")[2].upper() in _FUTURES_SUFFIXES
    )
    equities = tuple(
        instrument_id
        for instrument_id in output.instrument_ids
        if instrument_id.partition(".")[2].upper() not in _FUTURES_SUFFIXES
    )
    if market == "CN_A" and futures:
        raise StrategyGenerationError(
            "CN_A strategies cannot trade futures instruments: "
            + ", ".join(futures)
        )
    if market == "CN_COMMODITY_FUTURES" and equities:
        raise StrategyGenerationError(
            "CN_COMMODITY_FUTURES strategies require futures instruments: "
            + ", ".join(equities)
        )


def _check_instrument_conventions(output: AgentOutput) -> None:
    """期货 instrument 代码约定校验。

    数据源（iFinD）的连续合约只有 ``8888`` 约定（如 SA8888.CZC）；
    其它主力连续写法（9999/0000/888…）均不可拉取，出现即打回。
    """
    for instrument_id in output.instrument_ids:
        symbol, _, suffix = instrument_id.partition(".")
        if suffix.upper() not in _FUTURES_SUFFIXES:
            continue
        digits = "".join(ch for ch in symbol if ch.isdigit())
        if digits in _BAD_CONTINUOUS_DIGITS:
            raise StrategyGenerationError(
                f"invalid continuous-contract code {instrument_id}: the data "
                "source only supports the 8888 convention (e.g. SA8888.CZC, "
                "RB8888.SHF); fix it or use a specific contract (e.g. "
                "SA701.CZC)"
            )


def _check_directional_clarity(output: AgentOutput, market: str) -> None:
    """双边市场的 explanation 必须区分开多/开空、平多/平空。

    裸『开仓/平仓』在可做空的市场里有歧义（用户无法分辨方向），
    出现即打回重生成。只要求出现方向性词汇（多/空 或 long/short），
    不限定具体句式。
    """
    if market != "CN_COMMODITY_FUTURES":
        return
    explanation = output.explanation or ""
    if "多" in explanation or "空" in explanation:
        return
    lowered = explanation.lower()
    if "long" in lowered or "short" in lowered:
        return
    raise StrategyGenerationError(
        "two-sided strategy (futures) explanation must distinguish direction "
        "explicitly: 开多 vs 开空 for entries and 平多 vs 平空 for exits "
        "(open long/open short, close long/close short); bare 开仓/平仓 is "
        "ambiguous"
    )


def _build_system_prompt() -> str:
    indicator_line = ", ".join(_INDICATORS)
    today = datetime.now(_SHANGHAI).date().isoformat()
    return (
        "\n".join(_SYSTEM_PROMPT_LINES)
        .replace("INDICATORS", indicator_line)
        .replace("{today}", today)
    )


def _build_prompt(market: str, history: Sequence[StrategyMessage]) -> str:
    lines = [f"Target market: {market}", "", "Conversation:"]
    for message in history:
        role = "user" if message.role == "user" else "assistant"
        lines.append(f"{role}: {message.content}")
    lines.append("")
    lines.append("Respond with the JSON object for the current turn.")
    return "\n".join(lines)


def _parse(raw: str) -> AgentOutput:
    data = _extract_json(raw)
    try:
        return AgentOutput.model_validate(dict(data))
    except (TypeError, ValueError) as exc:
        raise StrategyGenerationError(f"agent output invalid: {exc}") from exc


__all__ = [
    "AgentOutput",
    "Runner",
    "StrategyGenerationError",
    "StrategyMessage",
    "default_runner",
    "run_turn",
]
