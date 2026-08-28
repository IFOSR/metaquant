"""Agent 基座模型配置服务：活跃选择的解析 + Provider（全局）凭据管理。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from quant_platform.agent_config.catalog import (
    DEFAULT_PROVIDERS,
    ModelInfo,
    agent_supported_builtins,
)
from quant_platform.research.models import (
    AgentConfigModel,
    AgentProviderModel,
)

AGENTS = ("codex", "pi")

_CONFIG_ID = "default"


@dataclass(frozen=True, slots=True)
class ResolvedAgentConfig:
    """一次调用所需的全部基座模型配置（已解析、可直接透传给 CLI）。"""

    agent: str
    provider: str
    model: str
    api_key: str
    base_url: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def mask_api_key(api_key: str) -> str:
    """掩码展示：``sk-***abcd``。"""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


def provider_payload(row: AgentProviderModel) -> dict[str, Any]:
    return {
        "provider": row.provider,
        "kind": row.kind,
        "base_url": row.base_url,
        "has_api_key": bool(row.api_key),
        "masked_key": mask_api_key(row.api_key),
    }


class AgentConfigService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    # ── 活跃配置解析（供 runner 每次调用即时读取）─────────────────────────

    def resolve_active(self) -> ResolvedAgentConfig | None:
        """读单行活跃配置 + 对应 provider 凭据，供 ``default_runner`` 派发。

        Provider 凭据是全局的（与 agent 无关），按 provider 名读取。
        """
        with self._sessions() as session:
            config = session.get(AgentConfigModel, _CONFIG_ID)
            if config is None or not config.active_provider or not config.active_model:
                return None
            credential = session.get(AgentProviderModel, config.active_provider)
            return ResolvedAgentConfig(
                agent=config.active_agent,
                provider=config.active_provider,
                model=config.active_model,
                api_key=credential.api_key if credential is not None else "",
                base_url=credential.base_url if credential is not None else None,
            )

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get_config(self) -> dict[str, Any]:
        with self._sessions() as session:
            config = session.get(AgentConfigModel, _CONFIG_ID)
            return {
                "agent": config.active_agent if config else "",
                "provider": config.active_provider if config else "",
                "model": config.active_model if config else "",
            }

    def list_providers(self) -> list[dict[str, Any]]:
        """全部已配置/已存在的 Provider（全局）。"""
        with self._sessions() as session:
            rows = session.scalars(select(AgentProviderModel)).all()
            return [provider_payload(row) for row in rows]

    def get_credential(self, provider: str) -> tuple[str, str | None]:
        """返回某 provider 的原始 (api_key, base_url)，未配置返回 ("", None)。"""
        with self._sessions() as session:
            row = session.get(AgentProviderModel, provider)
            if row is None:
                return "", None
            return row.api_key, row.base_url

    # ── 写入 ──────────────────────────────────────────────────────────────

    def save_config(self, *, agent: str, provider: str, model: str) -> dict[str, Any]:
        with self._sessions.begin() as session:
            config = session.get(AgentConfigModel, _CONFIG_ID)
            if config is None:
                config = AgentConfigModel(
                    id=_CONFIG_ID,
                    active_agent=agent,
                    active_provider=provider,
                    active_model=model,
                    updated_at=_now(),
                )
                session.add(config)
            else:
                config.active_agent = agent
                config.active_provider = provider
                config.active_model = model
                config.updated_at = _now()
        return self.get_config()

    def upsert_provider(
        self,
        *,
        provider: str,
        api_key: str,
        kind: str = "builtin",
        base_url: str | None = None,
    ) -> dict[str, Any]:
        with self._sessions.begin() as session:
            row = session.get(AgentProviderModel, provider)
            if row is None:
                row = AgentProviderModel(
                    provider=provider,
                    kind=kind,
                    base_url=base_url,
                    api_key=api_key,
                    updated_at=_now(),
                )
                session.add(row)
            else:
                row.kind = kind
                row.base_url = base_url
                row.api_key = api_key
                row.updated_at = _now()
        return {
            "provider": provider,
            "kind": kind,
            "base_url": base_url,
            "has_api_key": bool(api_key),
            "masked_key": mask_api_key(api_key),
        }

    def delete_provider(self, *, provider: str) -> None:
        with self._sessions.begin() as session:
            row = session.get(AgentProviderModel, provider)
            if row is not None:
                session.delete(row)


def agent_agents_payload() -> list[dict[str, Any]]:
    """Agent 清单：支持的内置 provider + 默认 provider（供前端选择）。"""
    return [
        {
            "name": agent,
            "supportedProviders": list(agent_supported_builtins(agent)),
            "defaultProviders": list(DEFAULT_PROVIDERS.get(agent, ())),
        }
        for agent in AGENTS
    ]


def catalog_model_payload(models: list[ModelInfo]) -> list[dict[str, Any]]:
    return [model.payload() for model in models]
