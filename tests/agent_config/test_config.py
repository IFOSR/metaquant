"""Tests for agent base-model config (catalog parsing + service + runner)."""

from __future__ import annotations

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from quant_platform.agent_config.catalog import ModelCatalogService, _parse_pi_models
from quant_platform.agent_config.service import (
    AgentConfigService,
    ResolvedAgentConfig,
    mask_api_key,
)
from quant_platform.research.models import Base

_SAMPLE = (
    "provider     model               context  max-out  thinking  images\n"
    "anthropic    claude-opus-5       1M       128K     yes       yes\n"
    "deepseek     deepseek-v4-pro     1M       384K     yes       no\n"
    "code-cli     gpt-5.6-sol         272K     32.8K    yes       yes\n"
)


def _service() -> AgentConfigService:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return AgentConfigService(sessionmaker(engine))


def test_parse_pi_models_filters_by_provider() -> None:
    models = _parse_pi_models(_SAMPLE, provider="deepseek")
    assert len(models) == 1
    assert models[0].model == "deepseek-v4-pro"
    assert models[0].thinking is True
    assert models[0].images is False


def test_parse_pi_models_all() -> None:
    assert len(_parse_pi_models(_SAMPLE)) == 3


def _fake_http(payload: dict, status: int = 200):
    class _Response:
        status_code = status

        def raise_for_status(self) -> None:
            if status >= 400:
                raise httpx.HTTPStatusError(
                    "error", request=None, response=httpx.Response(status)
                )

        def json(self) -> dict:
            return payload

    return _Response()


def test_pi_openai_compat_models_via_http(monkeypatch) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        assert headers and headers.get("Authorization") == "Bearer sk-x"
        return _fake_http(
            {"data": [{"id": "moonshot-v1-8k"}, {"id": "moonshot-v1-32k"}]}
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    models = ModelCatalogService().list_models(
        agent="pi", provider="kimi-coding", api_key="sk-x"
    )
    assert [m.model for m in models] == ["moonshot-v1-8k", "moonshot-v1-32k"]
    assert models[0].provider == "kimi-coding"


def test_pi_anthropic_models_via_http(monkeypatch) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        assert headers and headers.get("x-api-key") == "sk-ant-x"
        return _fake_http(
            {"data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-opus-4-5"}]}
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    models = ModelCatalogService().list_models(
        agent="pi", provider="anthropic", api_key="sk-ant-x"
    )
    assert [m.model for m in models] == ["claude-sonnet-4-5", "claude-opus-4-5"]


def test_pi_google_models_via_http(monkeypatch) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        assert params and params.get("key") == "g-key"
        return _fake_http(
            {
                "models": [
                    {"name": "models/gemini-2.0-flash"},
                    {"name": "models/gemini-pro"},
                ]
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    models = ModelCatalogService().list_models(
        agent="pi", provider="google", api_key="g-key"
    )
    assert [m.model for m in models] == ["gemini-2.0-flash", "gemini-pro"]


def test_pi_http_auth_failure_falls_back(monkeypatch) -> None:
    def fake_get(url, headers=None, params=None, timeout=None):
        return _fake_http({"error": "unauthorized"}, status=401)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _subprocess_result(
            stdout="\nprovider     model   context max-out thinking images\n",
            returncode=0,
        ),
    )
    models, note = ModelCatalogService().list_models_with_report(
        agent="pi", provider="kimi-coding", api_key="sk-bad"
    )
    assert models == []
    assert "401" in note
    assert "kimi-coding" in note


def test_pi_no_key_returns_empty_without_error(monkeypatch) -> None:
    def boom(*a, **k):
        raise AssertionError("should not hit network without a key")

    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _subprocess_result(
            stdout="\nprovider     model   context max-out thinking images\n",
            returncode=0,
        ),
    )
    models, note = ModelCatalogService().list_models_with_report(
        agent="pi", provider="kimi-coding", api_key=""
    )
    assert models == []
    assert note == ""


class _subprocess_result:
    def __init__(self, *, stdout: str, returncode: int) -> None:
        self.stdout = stdout
        self.returncode = returncode


def test_mask_api_key() -> None:
    assert mask_api_key("sk-test-1234567890") == "sk-***7890"
    assert mask_api_key("short") == "***"


def test_resolve_active_none_when_unconfigured() -> None:
    service = _service()
    assert service.resolve_active() is None


def test_resolve_active_returns_config() -> None:
    service = _service()
    service.upsert_provider(provider="deepseek", api_key="sk-123")
    service.save_config(agent="pi", provider="deepseek", model="deepseek-v4-pro")
    resolved = service.resolve_active()
    assert resolved is not None
    assert resolved == ResolvedAgentConfig(
        agent="pi",
        provider="deepseek",
        model="deepseek-v4-pro",
        api_key="sk-123",
        base_url=None,
    )


def test_credential_reuse_and_override() -> None:
    service = _service()
    first = service.upsert_provider(provider="openai", api_key="sk-first-1234567890")
    assert first["has_api_key"] is True
    assert first["masked_key"].endswith("7890")

    overridden = service.upsert_provider(
        provider="openai", api_key="sk-second-1234567890"
    )
    assert overridden["masked_key"].endswith("7890")
    assert service.get_credential("openai")[0] == "sk-second-1234567890"


def test_provider_is_global_across_agents() -> None:
    service = _service()
    service.upsert_provider(provider="openai", api_key="sk-global-1234567890")
    # codex 与 pi 读到的都是同一个 provider 的凭据。
    assert service.get_credential("openai")[0] == "sk-global-1234567890"
    assert service.list_providers()[0]["provider"] == "openai"


def test_delete_provider_removes_row() -> None:
    service = _service()
    service.upsert_provider(provider="openai", api_key="sk-del-1234567890")
    service.delete_provider(provider="openai")
    assert service.get_credential("openai") == ("", None)
