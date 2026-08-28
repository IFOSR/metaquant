"""Extract a factor + brief from a research paper via a non-interactive agent.

The agent is an amplifier, not an authority: it proposes a factor definition
(factor IR) and a brief, the researcher reviews and freezes them, and the
deterministic kernel still preregisters/validates.  The agent never writes to
the kernel.

The agent backend is injectable.  The default reads the active agent base-model
config (``codex`` / ``pi``) via an injected resolver (DB-backed, resolved per
call), falling back to env-var backends (DeepSeek → Zhipu → legacy pi).  Both
CLI backends are non-interactive and never mutate the host-installed agent's
global config.
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

# 活跃 Agent 基座模型配置解析器（由 app 层装配，读 DB；每次调用即时解析）。
_agent_config_resolver: Callable[[], Any] | None = None


def set_agent_config_resolver(resolver: Callable[[], Any] | None) -> None:
    """注入「活跃 Agent 基座模型配置」解析器。

    解析器返回一个带 ``agent/provider/model/api_key/base_url`` 属性的对象，
    或 None（无配置，走 env 兜底）。每次调用即时解析，保证配置即时生效。
    """
    global _agent_config_resolver
    _agent_config_resolver = resolver


def _resolve_agent_config() -> Any:
    if _agent_config_resolver is None:
        return None
    try:
        return _agent_config_resolver()
    except Exception:  # noqa: BLE001 — 配置解析失败不影响 env 兜底
        return None


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


def _pi_complete(
    prompt: str,
    *,
    provider: str = "",
    model: str = "",
    api_key: str = "",
) -> str:
    """调用系统安装的 ``pi``（非交互），基座模型经 CLI 参数注入。

    只复用 ``pi`` 二进制，不改写 ``pi`` 自身的全局配置：``--provider`` /
    ``--model`` / ``--api-key`` 来自项目配置，仅对本项目本次调用生效。
    """
    argv = ["pi", "-p", "--no-session", "--mode", "text"]
    if provider:
        argv += ["--provider", provider]
    if model:
        argv += ["--model", model]
    if api_key:
        argv += ["--api-key", api_key]
    argv.append(prompt)
    result = subprocess.run(
        argv,
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


def _codex_complete(
    prompt: str,
    *,
    model: str,
    api_key: str = "",
    base_url: str | None = None,
) -> str:
    """调用系统安装的 ``codex``（非交互），模型经 ``-m`` 注入。

    用 ``--ignore-user-config`` 不读本机 ``~/.codex/config.toml``、
    ``--ephemeral`` 不落 session；api_key 仅经本次子进程 env 注入，不写全局。
    """
    env = dict(os.environ)
    if api_key:
        env["CODE_CLI_API_KEY"] = api_key
    if base_url:
        env["OPENAI_BASE_URL"] = base_url
    argv = ["codex", "exec", "--ignore-user-config", "--ephemeral"]
    if model:
        argv += ["-m", model]
    argv.append(prompt)
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise FactorExtractionError(
            f"codex exited {result.returncode}: {result.stderr.strip()}"
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

    优先级：DB 活跃 Agent 配置（codex / pi，即时解析）→ DeepSeek → Zhipu →
    遗留 pi（``CODE_CLI_API_KEY``）。
    """
    prompt = system_prompt or _SYSTEM_PROMPT
    config = _resolve_agent_config()
    if config is not None:
        agent = getattr(config, "agent", "") or ""
        if agent == "codex":
            return lambda user: _codex_complete(
                f"{prompt}\n\n{user}",
                model=getattr(config, "model", "") or "",
                api_key=getattr(config, "api_key", "") or "",
                base_url=getattr(config, "base_url", None),
            )
        if agent == "pi":
            return lambda user: _pi_complete(
                f"{prompt}\n\n{user}",
                provider=getattr(config, "provider", "") or "",
                model=getattr(config, "model", "") or "",
                api_key=getattr(config, "api_key", "") or "",
            )
    if os.environ.get("DEEPSEEK_API_KEY"):
        return lambda user: _deepseek_complete(
            user, system_prompt=prompt, json_mode=json_mode
        )
    if os.environ.get("ZHIPU_API_KEY") or _read_zhipu_key():
        return lambda user: _zhipu_complete(user, system_prompt=prompt)
    if shutil.which("pi") and os.environ.get("CODE_CLI_API_KEY"):
        return lambda user: _pi_complete(
            f"{prompt}\n\n{user}",
            provider=os.environ.get("PI_PROVIDER", "").strip(),
            model=os.environ.get("PI_MODEL", "").strip(),
            api_key=os.environ.get("PI_API_KEY", "").strip(),
        )
    raise FactorExtractionError(
        "no agent runner configured: set DEEPSEEK_API_KEY, ZHIPU_API_KEY, "
        "PI_PROVIDER/PI_MODEL, or CODE_CLI_API_KEY (pi)"
    )


def _default_runner() -> Runner:
    return default_runner()
