"""Extract a factor + brief from a research paper via a non-interactive agent.

The agent is an amplifier, not an authority: it proposes a factor definition
(factor IR) and a brief, the researcher reviews and freezes them, and the
deterministic kernel still preregisters/validates.  The agent never writes to
the kernel.

The agent backend is injectable.  The default prefers the ``pi`` CLI in
non-interactive mode (``pi -p``) when ``CODE_CLI_API_KEY`` is present, then
falls back to a direct Zhipu HTTP call (the opencode provider), then DeepSeek.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from quant_platform.research.schemas import BriefContent

Runner = Callable[[str], str]

_SYSTEM_PROMPT = """You are a quantitative factor researcher. Read a research
report and extract ONE testable factor as structured JSON.

Return only a JSON object (no markdown fences) with exactly this shape:
{
  "factor_id": "snake_case identifier, e.g. classic.cn_a.momentum_5d",
  "factor_name": "short human-readable name",
  "inputs": [
    {"alias": "close", "field_ref": "market.eod.close",
     "available_time_rule": "T_CLOSE+20m"}
  ],
  "expression": {
    "op": "one of the operators listed in the rules below",
    "args": [{"ref": "close"}],
    "params": {}
  },
  "brief": {
    "hypothesis": "one sentence: the factor and its predicted effect",
    "economic_mechanism": "why the effect should exist",
    "expected_direction": "POSITIVE | NEGATIVE | NON_MONOTONIC | UNKNOWN",
    "falsification_conditions": ["what result would prove it wrong"],
    "allowed_data_domains": ["formal.market.eod"],
    "forbidden_data_domains": [],
    "constraints": ["universe or timing constraints"],
    "evidence_ref_ids": [],
    "uncertainties": ["known weaknesses"]
  },
  "explanation": "one sentence describing the extracted factor"
}

Rules:
- Use the report's actual factor definition; do not invent a new one.
- expected_direction must be POSITIVE, NEGATIVE, NON_MONOTONIC or UNKNOWN.
- field_ref must reference market.eod.* fields only.
- returns/lag/delta use params.periods (integer lookback).
- rolling_mean/rolling_std/rolling_min/rolling_max/ts_rank/ts_corr use params.window.
- cs_rank/zscore use no params; winsorize uses params.limit.
- Use "ref" in args to reference an input alias.
"""


class FactorExtractionError(RuntimeError):
    """Raised when the agent cannot produce a valid factor extraction."""


@dataclass(frozen=True, slots=True)
class FactorExtraction:
    brief: BriefContent
    factor_ir: dict[str, Any]
    explanation: str


def extract_factor_from_paper(
    paper_text: str,
    market: str,
    *,
    runner: Runner | None = None,
    user_prompt: str | None = None,
) -> FactorExtraction:
    """Translate a report into a factor IR + brief draft via the agent."""
    complete = runner or _default_runner()
    if user_prompt:
        material = f"User request: {user_prompt}\n\nReport text:\n\n{paper_text}"
    else:
        material = f"Report text:\n\n{paper_text}"
    raw = complete(f"{material}\n\nTarget market: {market}")
    data = _extract_json(raw)
    try:
        return _build_extraction(data, market)
    except FactorExtractionError:
        # one retry with a corrective hint
        raw = complete(
            f"Your previous JSON failed validation. Return only valid JSON "
            f"matching the schema, with target market {market}.\n\n"
            f"Previous output: {raw[:2000]}"
        )
        return _build_extraction(_extract_json(raw), market)


def _build_extraction(data: Mapping[str, Any], market: str) -> FactorExtraction:
    if not isinstance(data.get("brief"), Mapping):
        raise FactorExtractionError("agent output missing brief")
    brief = BriefContent.model_validate(dict(data["brief"]))
    factor_ir = _build_factor_ir(data, market)
    explanation = str(data.get("explanation", "")).strip()
    return FactorExtraction(brief=brief, factor_ir=factor_ir, explanation=explanation)


_MARKET_SCOPE: dict[str, dict[str, object]] = {
    "CN_A": {
        "market": "CN_A",
        "frequency": "1d",
        "universe_ref": "universe://csi300-pit/v1",
        "exchange_scope": [],
    },
    "CN_COMMODITY_FUTURES": {
        "market": "CN_COMMODITY_FUTURES",
        "frequency": "1d",
        "universe_ref": "futures:liquid-initial",
        "exchange_scope": ["SHFE"],
        "contract_chain_ref": "chain://shfe-rb/v1",
        "roll_policy_ref": "roll-policy://oi-confirmed-3d/v1",
    },
}

_POLICY_REF: dict[str, str] = {
    "CN_A": "policy://cn-a-daily-factor/v1",
    "CN_COMMODITY_FUTURES": "policy://cn-futures-daily-factor/v1",
}


def _build_factor_ir(data: Mapping[str, Any], market: str) -> dict[str, Any]:
    if market not in _MARKET_SCOPE:
        raise FactorExtractionError(f"unsupported market: {market}")
    factor_id = str(data.get("factor_id", "")).strip()
    if not factor_id:
        raise FactorExtractionError("agent output missing factor_id")
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise FactorExtractionError("agent output missing inputs")
    expression = data.get("expression")
    if not isinstance(expression, Mapping):
        raise FactorExtractionError("agent output missing expression")
    expression = _normalize_expression(dict(expression))
    normalized_inputs = [
        {
            "alias": str(item.get("alias", "")),
            "field_ref": str(item.get("field_ref", "")),
            "data_type": "ScalarSeries",
            "unit": str(item.get("unit", "CNY")),
            "available_time_rule": str(item.get("available_time_rule", "T_CLOSE+20m")),
        }
        for item in inputs
    ]
    for item in normalized_inputs:
        if not item["alias"] or not item["field_ref"].startswith("market.eod."):
            raise FactorExtractionError("invalid input field reference")
    return {
        "schema_version": "factor-ir/v1",
        "factor_id": factor_id,
        "version": "1.0.0",
        "market_scope": _MARKET_SCOPE[market],
        "decision_clock": {
            "signal_time": "T_CLOSE+30m",
            "earliest_trade_time": "T+1_OPEN",
        },
        "inputs": normalized_inputs,
        "expression": expression,
        "validation_policy_ref": _POLICY_REF[market],
    }


_OPERATOR_ALIASES: dict[str, str] = {
    "return": "returns",
    "ret": "returns",
    "momentum": "returns",
    "pct_change": "returns",
    "rank": "cs_rank",
    "cross_rank": "cs_rank",
    "mean": "rolling_mean",
    "average": "rolling_mean",
    "rolling_average": "rolling_mean",
    "std": "rolling_std",
    "stdev": "rolling_std",
    "minimum": "rolling_min",
    "maximum": "rolling_max",
    "correlation": "ts_corr",
    "time_rank": "ts_rank",
    "minus": "sub",
    "times": "mul",
    "plus": "add",
    "divide": "div",
    "absolute": "abs",
    "logarithm": "log",
}


def _normalize_expression(expression: dict[str, Any]) -> dict[str, Any]:
    """Coerce agent output to the executor's parameter conventions."""
    op = str(expression.get("op", "")).strip()
    op = _OPERATOR_ALIASES.get(op, op)
    params = dict(expression.get("params", {}))
    if (
        op in {"returns", "lag", "delta"}
        and "periods" not in params
        and "window" in params
    ):
        params["periods"] = params.pop("window")
    return {
        "op": op,
        "args": list(expression.get("args", [])),
        "params": params,
    }


def _extract_json(raw: str) -> Mapping[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").rstrip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FactorExtractionError(f"agent returned invalid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise FactorExtractionError("agent output must be a JSON object")
    return data


# --- runner backends -------------------------------------------------------


def _pi_complete(prompt: str) -> str:
    result = subprocess.run(
        ["pi", "-p", "--no-session", "--mode", "text", prompt],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise FactorExtractionError(
            f"pi exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _zhipu_complete(prompt: str, *, system_prompt: str = _SYSTEM_PROMPT) -> str:
    api_key = os.environ.get("ZHIPU_API_KEY") or _read_zhipu_key()
    if not api_key:
        raise FactorExtractionError("ZHIPU_API_KEY is not configured")
    payload = {
        "model": "glm-4.6",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    response = httpx.post(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FactorExtractionError("unexpected Zhipu response shape") from exc
    if not isinstance(content, str):
        raise FactorExtractionError("unexpected Zhipu response shape")
    return content


def _deepseek_complete(
    prompt: str, *, system_prompt: str = _SYSTEM_PROMPT, json_mode: bool = True
) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise FactorExtractionError("DEEPSEEK_API_KEY is not configured")
    payload: dict[str, object] = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    response = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise FactorExtractionError("unexpected DeepSeek response shape") from exc
    if not isinstance(content, str):
        raise FactorExtractionError("unexpected DeepSeek response shape")
    return content


def _read_zhipu_key() -> str:
    path = Path.home() / ".config" / "opencode" / "opencode.json"
    try:
        document = json.loads(path.read_text())
        providers = document.get("provider", {})
        for provider in providers.values():
            options = provider.get("options", {})
            if isinstance(options, dict) and options.get("apiKey"):
                return str(options["apiKey"])
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""
    return ""


def default_runner(
    system_prompt: str | None = None, *, json_mode: bool = True
) -> Runner:
    """Select an agent backend, injecting ``system_prompt`` into the call.

    Kept as a factory (rather than returning the raw HTTP functions) so callers
    that need a *different* system prompt (e.g. factor construction) can reuse
    the backend selection without inheriting the factor-ir prompt.
    """
    prompt = system_prompt or _SYSTEM_PROMPT
    if os.environ.get("DEEPSEEK_API_KEY"):
        return lambda user: _deepseek_complete(
            user, system_prompt=prompt, json_mode=json_mode
        )
    if os.environ.get("ZHIPU_API_KEY") or _read_zhipu_key():
        return lambda user: _zhipu_complete(user, system_prompt=prompt)
    if shutil.which("pi") and os.environ.get("CODE_CLI_API_KEY"):
        return lambda user: _pi_complete(f"{prompt}\n\n{user}")
    raise FactorExtractionError(
        "no agent runner configured: set DEEPSEEK_API_KEY, ZHIPU_API_KEY, "
        "or CODE_CLI_API_KEY (pi)"
    )


def _default_runner() -> Runner:
    return default_runner()
