"""Agent 基座模型目录：从 pi / codex 自动获取可用模型清单。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import httpx

# 全部内置 provider（全局、与 agent 无关）。自定义（Other）provider 追加在后。
BUILTIN_PROVIDERS: tuple[str, ...] = (
    "openai",
    "deepseek",
    "kimi-coding",
    "openrouter",
    "anthropic",
    "google",
)

# OpenAI 兼容的内置 provider：codex（基于 OpenAI Codex CLI / OPENAI_BASE_URL）
# 只能用这些 + 自定义 OpenAI 兼容端点；pi 全部可用。
OPENAI_COMPAT_BUILTINS: frozenset[str] = frozenset(
    {"openai", "deepseek", "kimi-coding", "openrouter"}
)

# 每个 Agent 的默认（首选）provider。
DEFAULT_PROVIDERS: dict[str, tuple[str, ...]] = {
    "codex": ("openai",),
    "pi": BUILTIN_PROVIDERS,
}


def agent_supported_builtins(agent: str) -> tuple[str, ...]:
    """某 agent 支持的内置 provider。codex 仅 OpenAI 兼容；pi 全部。"""
    if agent == "codex":
        return tuple(p for p in BUILTIN_PROVIDERS if p in OPENAI_COMPAT_BUILTINS)
    return BUILTIN_PROVIDERS

# codex（OpenAI/GPT）静态兜底模型清单：当 /v1/models 不可用时使用。
_CODEX_FALLBACK_MODELS = (
    "gpt-5.6-sol",
    "o3",
    "o4-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "gpt-4o-mini",
)

_OPENAI_BASE_URL = "https://api.openai.com/v1"

# pi 内置 provider → 默认 base url。配置好 key 后按各自 /models 接口自动拉取
# 基础模型清单，用户无需手敲。openai/deepseek/kimi-coding/openrouter 为
# OpenAI 兼容；anthropic/google 走各自鉴权与返回结构；自定义（Other）用用户
# 提供的 base_url 并按 OpenAI 兼容处理。
_PI_DEFAULT_BASE_URL: dict[str, str] = {
    "openai": _OPENAI_BASE_URL,
    "deepseek": "https://api.deepseek.com/v1",
    "kimi-coding": "https://api.moonshot.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta",
}


@dataclass(frozen=True, slots=True)
class ModelInfo:
    provider: str
    model: str
    context: str = ""
    max_out: str = ""
    thinking: bool = False
    images: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context": self.context,
            "max_out": self.max_out,
            "thinking": self.thinking,
            "images": self.images,
        }


def _parse_pi_models(stdout: str, provider: str | None = None) -> list[ModelInfo]:
    """解析 ``pi --list-models`` 的空白对齐表格。"""
    models: list[ModelInfo] = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text or text.startswith("provider"):
            continue
        parts = text.split()
        if len(parts) < 6:
            continue
        name = parts[0]
        if provider is not None and name != provider:
            continue
        # 前 4 列固定为 context / max-out / thinking / images，中间 token 合并为模型名。
        model = " ".join(parts[1:-4])
        models.append(
            ModelInfo(
                provider=name,
                model=model,
                context=parts[-4],
                max_out=parts[-3],
                thinking=parts[-2] == "yes",
                images=parts[-1] == "yes",
            )
        )
    return models


class ModelCatalogService:
    """自动获取某 agent × provider 下的模型清单（含兜底与失败原因）。"""

    def _http_error_note(self, provider: str, exc: BaseException) -> str:
        code = ""
        status = getattr(exc, "response", None)
        if status is not None:
            code = getattr(status, "status_code", "")
        if isinstance(exc, httpx.TimeoutException):
            return f"{provider} 连接超时（不可达），请检查网络或稍后重试"
        if code:
            return (
                f"{provider} 拒绝了访问（HTTP {code}）——多为 API Key 无效或过期，"
                "请检查后重试，或改用被支持的 provider"
            )
        return f"{provider} 模型查询失败"

    def list_models(
        self,
        *,
        agent: str,
        provider: str,
        api_key: str = "",
        base_url: str | None = None,
    ) -> list[ModelInfo]:
        return self.list_models_with_report(
            agent=agent, provider=provider, api_key=api_key, base_url=base_url
        )[0]

    def list_models_with_report(
        self,
        *,
        agent: str,
        provider: str,
        api_key: str = "",
        base_url: str | None = None,
    ) -> tuple[list[ModelInfo], str]:
        """返回 (模型清单, 失败原因)。原因非空说明自动获取失败，可展示给用户。"""
        if agent == "pi":
            return self._pi_models(provider, api_key=api_key, base_url=base_url)
        if agent == "codex":
            return self._codex_models(
                provider, api_key=api_key, base_url=base_url
            )
        return [], ""

    def _pi_models(
        self,
        provider: str,
        *,
        api_key: str = "",
        base_url: str | None = None,
    ) -> tuple[list[ModelInfo], str]:
        """有 key 时按 provider 各自的 /models 接口自动拉取，失败回退 pi CLI。"""
        note = ""
        if api_key and (base_url is not None or provider in _PI_DEFAULT_BASE_URL):
            http_models, note = self._provider_http_models(
                provider=provider, api_key=api_key, base_url=base_url
            )
            if http_models:
                return http_models, ""
        cli_models: list[ModelInfo] = []
        try:
            result = subprocess.run(
                ["pi", "--list-models"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            cli_models = _parse_pi_models(result.stdout, provider=provider)
        if cli_models:
            return cli_models, ""
        return [], note

    def _provider_http_models(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str | None,
    ) -> tuple[list[ModelInfo], str]:
        """按 provider 分发到正确的鉴权 + 返回结构解析。"""
        if provider == "google":
            return self._google_models(provider, api_key, base_url)
        if provider == "anthropic":
            return self._anthropic_models(provider, api_key, base_url)
        # openai / deepseek / kimi-coding / openrouter / 自定义 -> OpenAI 兼容
        return self._openai_models(
            api_key=api_key,
            base_url=base_url or _PI_DEFAULT_BASE_URL.get(provider),
            provider=provider,
        )

    def _codex_models(
        self, provider: str, *, api_key: str, base_url: str | None
    ) -> tuple[list[ModelInfo], str]:
        models, note = self._openai_models(
            api_key=api_key, base_url=base_url, provider=provider
        )
        if models:
            return models, ""
        # GPT 兜底清单只在真正指向 openai 时才有意义；其它 OpenAI 兼容端点
        # 模型名不同，失败时应让用户看到错误而非错误的模型名。
        if provider == "openai":
            return [
                ModelInfo(provider=provider, model=name)
                for name in _CODEX_FALLBACK_MODELS
            ], ""
        return [], note

    def _openai_models(
        self,
        *,
        api_key: str,
        base_url: str | None,
        provider: str = "openai",
    ) -> tuple[list[ModelInfo], str]:
        if not api_key:
            return [], ""
        root = (
            base_url or _PI_DEFAULT_BASE_URL.get(provider) or _OPENAI_BASE_URL
        ).rstrip("/")
        try:
            response = httpx.get(
                f"{root}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return [], self._http_error_note(provider, exc)
        try:
            data = response.json()["data"]
        except (KeyError, TypeError, ValueError):
            return [], f"{provider} 返回结构异常，无法解析模型列表"
        models = [
            ModelInfo(provider=provider, model=str(item.get("id", "")))
            for item in data
            if isinstance(item, dict) and item.get("id")
        ]
        return models, ""

    def _anthropic_models(
        self, provider: str, api_key: str, base_url: str | None
    ) -> tuple[list[ModelInfo], str]:
        if not api_key:
            return [], ""
        root = (base_url or _PI_DEFAULT_BASE_URL["anthropic"]).rstrip("/")
        try:
            response = httpx.get(
                f"{root}/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=20,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return [], self._http_error_note(provider, exc)
        try:
            data = response.json()["data"]
        except (KeyError, TypeError, ValueError):
            return [], f"{provider} 返回结构异常，无法解析模型列表"
        models = [
            ModelInfo(provider=provider, model=str(item.get("id", "")))
            for item in data
            if isinstance(item, dict) and item.get("id")
        ]
        return models, ""

    def _google_models(
        self, provider: str, api_key: str, base_url: str | None
    ) -> tuple[list[ModelInfo], str]:
        if not api_key:
            return [], ""
        root = (base_url or _PI_DEFAULT_BASE_URL["google"]).rstrip("/")
        try:
            response = httpx.get(
                f"{root}/models", params={"key": api_key}, timeout=20
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return [], self._http_error_note(provider, exc)
        try:
            models = response.json()["models"]
        except (KeyError, TypeError, ValueError):
            return [], f"{provider} 返回结构异常，无法解析模型列表"
        out: list[ModelInfo] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "")
            model = name.removeprefix("models/") or name
            if model:
                out.append(ModelInfo(provider=provider, model=model))
        return out, ""
