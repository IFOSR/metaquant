"""Natural-language strategy agent (G19-P1).

Turns a multi-turn conversation into an executable NautilusTrader Python
strategy plus a plain-language explanation. Reuses the backend selection from
``research.factor_extract`` (pi / Zhipu / DeepSeek) with its own system prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from quant_platform.research.factor_extract import (
    Runner,
    _extract_json,
    default_runner,
)
from quant_platform.strategy_generation.schemas import AgentOutput, StrategyMessage

_SHANGHAI = ZoneInfo("Asia/Shanghai")

_INDICATORS = (
    "sma(period) -> value",
    "ema(period) -> value",
    "wma(period) -> value",
    "dema(period) -> value",
    "hma(period) -> value",
    "macd(fast, slow, signal=9) -> dif, dea",
    "atr(period) -> value",
    "adx(period) -> adx, di_plus, di_minus",
    "bollinger(period, k=2) -> upper, mid, lower",
    "rsi(period) -> value",
    "roc(period) -> value",
    "cci(period) -> value",
    "stoch(period_k, period_d, slowing=1) -> k, d",
    "aroon(period) -> value, up, down",
    "cmo(period) -> value",
    "linreg(period) -> value, slope, intercept",
    "keltner(period, k=2) -> upper, mid, lower",
    "donchian(period) -> upper, mid, lower",
    "obv(period) -> value",
)

_SYSTEM_PROMPT_LINES = (
    "You are a quantitative trading strategy engineer. You work with a user "
    "through a multi-turn conversation to turn their natural-language "
    "description of a trading strategy into a SIGNAL SPECIFICATION: a "
    "declarative indicator list plus a pure signal function. The platform "
    "(not you) owns the entire pipeline — bar subscription, indicator "
    "computation, order submission, position tracking, stop/take-profit "
    "enforcement.",
    "",
    "Each turn you receive the full conversation transcript plus the target "
    "market. Read it, update your understanding, and respond with a JSON "
    "object (no markdown fences) with exactly this shape:",
    "{",
    '  "title": "short strategy name",',
    '  "explanation": "plain-language summary of the strategy as understood, '
    "for a NON-programmer: what it trades, when it enters/exits, position "
    "sizing, stop loss, universe, frequency. It must fully reflect the "
    "signal logic, not drift from it. For two-sided strategies every "
    "entry/exit rule must state its direction explicitly (开多 vs 开空, "
    "平多 vs 平空).",
    '  "question": "the single most important clarifying question for the '
    'user, or empty string if the strategy is fully specified",',
    '  "code": "the signal specification Python source (INDICATORS + '
    'compute_signal), or null if not yet fully specified",',
    '  "instrument_ids": ["600000.SH"],',
    '  "frequency": "1d",',
    '  "kind": "strategy",',
    '  "ready": false',
    "}",
    "",
    "Rules:",
    '- kind: "strategy" when the user describes buy/sell rules that become a '
    'strategy; "factor" when the user asks to mine a predictive '
    "factor/alpha from a report or data. Default strategy.",
    '- instrument_ids: the instruments to trade, e.g. ["600000.SH"] for '
    'A-shares (SH/SZ suffix) or ["RB2610.SHF"] for futures '
    "(.SHF/.DCE/.CZC/.INE/.GFE suffix). Empty list until the user specifies "
    "them; ask in question when missing. Zhengzhou (郑商所, .CZC) contract "
    "months are 3 digits (e.g. SA701, not SA2701). When the user asks for "
    "the main/continuous contract (主力/连续), use the iFinD 8888 "
    "convention: SA8888.CZC, RB8888.SHF — NEVER 9999/0000 or any other "
    "continuous code (they are rejected and un-fetchable).",
    "- NEVER drift to placeholder values: the example [\"600000.SH\"] in "
    "the JSON shape is ONLY a placeholder. Preserve the current "
    "instrument_ids across turns unless the user explicitly asks to "
    "change them.",
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
    "",
    "The 'code' field is a SIGNAL SPECIFICATION. It must contain exactly two "
    "top-level objects and nothing else:",
    'INDICATORS = [{"key": "trend_sma", "type": "sma", "period": 20}, ...]',
    "def compute_signal(ctx):",
    "    ...",
    "    return Signal(target_qty=..., stop_price=..., take_profit=...)",
    "",
    "- No imports, no classes, no NautilusTrader API. You may use `math` and "
    "the `Signal` dataclass. Any pipeline symbol (subscribe_bars, "
    "order_factory, submit_order, register_indicator_for_bars, Strategy, "
    "StrategyConfig, close_all_positions, ...) is forbidden — the platform "
    "owns it.",
    "- INDICATORS: a list of dicts. Each is "
    '{"key": <string>, "type": <one of the available types>, ...params}. '
    "Available types (with their params and the fields exposed on their "
    "values):",
    "AVAILABLE_INDICATORS",
    "- The platform computes every declared indicator on BOTH timeframes "
    "automatically. In compute_signal read current values as "
    "ctx.exec.<key>.<field> (execution timeframe) and "
    "ctx.trend.<key>.<field> (trend timeframe); previous-bar values as "
    "ctx.prev.exec.<key>.<field> / ctx.prev.trend.<key>.<field> (for "
    "golden/death cross detection). ctx.trend is empty unless the strategy "
    "is multi-timeframe (user configured a trend timeframe).",
    "- ctx fields: bar (open/high/low/close/volume/ts), trend_bar (None if "
    "single-timeframe), exec/trend/prev (indicator values), position "
    "(current signed lots), entry_price, bars_since_entry, stop_price "
    "(current stop level), ready (True only when ALL indicators are warmed "
    "up).",
    "- Signal(target_qty, stop_price=None, take_profit=None). target_qty is "
    "the signed TARGET position in lots (1 = one contract/lot, 0 = flat, "
    "-1 = short one lot). Return the target and the platform submits the "
    "market orders to reach it. stop_price/take_profit are OPTIONAL "
    "protection levels: set them to arm, omit them (or None) to disarm. "
    "Trailing stop: ratchet from ctx.stop_price, e.g. "
    "stop_price = max(ctx.stop_price, ctx.bar.close - 2 * ctx.exec.atr.value).",
    "- Warm-up: ctx.ready is False until ALL declared indicators are "
    "initialized. ALWAYS start compute_signal with:",
    "    if not ctx.ready:",
    "        return Signal(target_qty=0)",
    "- Multi-timeframe: declare each indicator ONCE; reference it as "
    "ctx.trend.<key> for the trend (larger) timeframe and ctx.exec.<key> "
    "for the execution (smaller) timeframe. The USER sets "
    "exec_timeframe/trend_timeframe in the backtest plan — you NEVER "
    "hardcode a timeframe or bar type anywhere in the code.",
    "- Market rules: CN_A = A-share equities, T+1, short selling is "
    "restricted, so generate LONG/FLAT only (never negative target_qty). "
    "CN_COMMODITY_FUTURES = commodity futures, both long and short are "
    "allowed.",
    "- Directional clarity: when a strategy can trade BOTH directions "
    "(CN_COMMODITY_FUTURES, or any futures strategy with short entries), "
    "the explanation must distinguish 开多 vs 开空 for entries and 平多 vs "
    "平空 for exits — bare 开仓/平仓 is ambiguous and rejected. Even "
    "long-only futures strategies should say 开多/平多. In CN_A (long-only) "
    "plain 开仓/平仓 is fine because they can only mean 开多/平多.",
    "- No high frequency: only daily (1d), weekly (1w) or minute "
    "(5m/15m/30m/60m) bar strategies; never write tick/quote-driven logic.",
    "- If the user's request cannot be expressed with the available "
    "indicators, say so in explanation and ask a question instead of "
    "inventing an indicator or silently writing something else.",
    "- explanation must NEVER be empty: even when the user only tweaks one "
    "detail (e.g. switch timeframe), re-summarize the FULL strategy in one "
    "or two sentences. Empty explanation is rejected.",
    "- ready=true ONLY when the signal spec is complete and self-consistent; "
    "otherwise keep asking until the strategy is fully specified (but do "
    "not drag on pointlessly: once everything essential is known, fill "
    "reasonable defaults, state them in explanation, and set ready=true).",
)

class StrategyGenerationError(RuntimeError):
    """Raised when the agent cannot produce a valid strategy turn."""


def run_turn(
    *,
    market: str,
    history: Sequence[StrategyMessage],
    runner: Runner | None = None,
    state: dict[str, Any] | None = None,
) -> AgentOutput:
    """Run one agent turn over the conversation and return its output.

    任意失败（网络超时、JSON 解析、schema 校验、代码静态检查）都做一次纠正
    重试——LLM 侧偶发慢/错是常态，重试一次能消化大部分瞬时故障。
    """
    complete = runner or default_runner(system_prompt=_build_system_prompt())
    prompt = _build_prompt(market, history, state)
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
                f"{exc}. Fix it and return ONLY valid JSON matching the "
                "schema. Reminder: 'explanation' must be a non-empty "
                "plain-language summary of the full strategy (even for a "
                "small change like a timeframe switch); 'question' may be "
                "an empty string."
            )
    raise StrategyGenerationError(f"agent failed after retry: {last_error}")


def _static_check(output: AgentOutput, market: str) -> None:
    """轻量静态检查：信号文件契约 + 禁止管道/原生 NT API。"""
    _check_market_instruments(output, market)
    _check_instrument_conventions(output)
    code = output.code
    if not output.ready or not code:
        return
    _check_directional_clarity(output, market)
    if "INDICATORS" not in code:
        raise StrategyGenerationError("signal code must define INDICATORS")
    if "compute_signal" not in code:
        raise StrategyGenerationError(
            "signal code must define compute_signal(ctx)"
        )
    for forbidden in (
        "subscribe_bars",
        "order_factory",
        "submit_order",
        "register_indicator_for_bars",
        "close_all_positions",
        "StrategyConfig",
        "class ",
        "import ",
    ):
        if forbidden in code:
            raise StrategyGenerationError(
                f"signal code must not use '{forbidden.strip()}'; "
                "the platform owns the pipeline"
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
        .replace("AVAILABLE_INDICATORS", indicator_line)
        .replace("{today}", today)
    )


def _build_prompt(
    market: str,
    history: Sequence[StrategyMessage],
    state: dict[str, Any] | None = None,
) -> str:
    lines = [f"Target market: {market}"]
    if state:
        lines.append("")
        lines.append(
            "Current strategy state — PRESERVE these unless the user "
            "explicitly asks to change them:"
        )
        lines.append(f"- instrument_ids: {state.get('instrument_ids', [])}")
        lines.append(f"- frequency: {state.get('frequency', '1d')}")
    lines.append("")
    lines.append("Conversation:")
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
