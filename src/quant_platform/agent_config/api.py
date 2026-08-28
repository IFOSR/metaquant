"""HTTP API for agent base-model configuration (codex / pi)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from quant_platform.agent_config.catalog import (
    BUILTIN_PROVIDERS,
    ModelCatalogService,
    agent_supported_builtins,
)
from quant_platform.agent_config.service import (
    AGENTS,
    AgentConfigService,
    agent_agents_payload,
    catalog_model_payload,
)
from quant_platform.research.api import (
    ProblemError,
    ResearchPrincipal,
    ResearchPrincipalProvider,
)


class SaveConfigCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class UpsertProviderCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    api_key: str = ""
    kind: str = "builtin"
    base_url: str | None = None


def build_agent_config_router(
    service: AgentConfigService,
    principal_provider: ResearchPrincipalProvider,
    catalog: ModelCatalogService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["AgentConfig"])
    model_catalog = catalog or ModelCatalogService()

    def principal(
        authorization: str | None = Header(default=None),
    ) -> ResearchPrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            raise ProblemError(
                status=401,
                code="AUTHENTICATION_REQUIRED",
                title="Authentication required",
                detail="A Bearer access token is required.",
            )
        resolved = principal_provider(authorization.removeprefix("Bearer ").strip())
        if resolved is None:
            raise ProblemError(
                status=401,
                code="INVALID_ACCESS_TOKEN",
                title="Invalid access token",
                detail="The supplied access token is not recognized.",
            )
        return resolved

    def _require_agent(agent: str) -> None:
        if agent not in AGENTS:
            raise ProblemError(
                status=422,
                code="INVALID_AGENT",
                title="Invalid agent",
                detail=f"agent must be one of {', '.join(AGENTS)}.",
            )

    @router.get("/agent-config")
    def get_agent_config(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        return {
            **service.get_config(),
            "providers": service.list_providers(),
        }

    @router.get("/agent-config/agents")
    def list_agents(
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        return {"items": agent_agents_payload()}

    @router.get("/agent-config/providers")
    def list_providers(
        agent: str | None = None,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        if agent is not None:
            _require_agent(agent)
        known = service.list_providers()
        by_provider = {item["provider"]: item for item in known}
        builtins = (
            agent_supported_builtins(agent)
            if agent is not None
            else BUILTIN_PROVIDERS
        )
        items = []
        for name in builtins:
            row = by_provider.get(name)
            items.append(
                {
                    "provider": name,
                    "kind": "builtin",
                    "base_url": row["base_url"] if row else None,
                    "has_api_key": bool(row and row["has_api_key"]),
                    "masked_key": row["masked_key"] if row else "",
                }
            )
        # 自定义（Other）provider 对两个 agent 都可用（OpenAI 兼容端点）。
        for item in known:
            if item["kind"] == "custom":
                items.append(item)
        return {"items": items}

    @router.get("/agent-config/models")
    def list_models(
        agent: str,
        provider: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        api_key, base_url = service.get_credential(provider)
        models, note = model_catalog.list_models_with_report(
            agent=agent, provider=provider, api_key=api_key, base_url=base_url
        )
        payload: dict[str, Any] = {"items": catalog_model_payload(models)}
        if note:
            payload["note"] = note
        return payload

    @router.put("/agent-config/credentials")
    def upsert_provider(
        command: UpsertProviderCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        return service.upsert_provider(
            provider=command.provider,
            api_key=command.api_key,
            kind=command.kind,
            base_url=command.base_url,
        )

    @router.delete("/agent-config/credentials")
    def delete_provider(
        provider: str,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        service.delete_provider(provider=provider)
        return {"provider": provider}

    @router.put("/agent-config")
    def save_config(
        command: SaveConfigCommand,
        actor: ResearchPrincipal = Depends(principal),  # noqa: B008
    ) -> dict[str, Any]:
        del actor
        _require_agent(command.agent)
        return service.save_config(
            agent=command.agent, provider=command.provider, model=command.model
        )

    return router
