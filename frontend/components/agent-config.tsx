"use client";

import { useEffect, useMemo, useState } from "react";

import { quantApiClient } from "../lib/client";
import type {
  AgentDescriptor,
  AgentId,
  AgentModelInfo,
  AgentProviderInfo,
} from "../lib/types";
import { useI18n } from "./i18n-provider";

type Step = "agent" | "provider" | "model";

const AGENT_CONFIG_EVENT = "quant:agent-config-changed";

export function AgentConfig() {
  const { t } = useI18n();

  // ── 全局 Provider（独立板块） ─────────────────────────────────────────
  const [providers, setProviders] = useState<AgentProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [providerKey, setProviderKey] = useState("");
  const [providerBaseUrl, setProviderBaseUrl] = useState("");
  const [addingCustom, setAddingCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customBaseUrl, setCustomBaseUrl] = useState("");
  const [customApiKey, setCustomApiKey] = useState("");

  // ── Agent 基座模型配置 ────────────────────────────────────────────────
  const [agents, setAgents] = useState<AgentDescriptor[]>([]);
  const [step, setStep] = useState<Step>("agent");
  const [agent, setAgent] = useState<AgentId | null>(null);
  const [agentProviders, setAgentProviders] = useState<AgentProviderInfo[]>([]);
  const [provider, setProvider] = useState<string | null>(null);
  const [models, setModels] = useState<AgentModelInfo[]>([]);
  const [model, setModel] = useState<string | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsNote, setModelsNote] = useState<string | null>(null);
  const [current, setCurrent] = useState<{
    agent: string;
    provider: string;
    model: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshProviders = async () => {
    const list = await quantApiClient.listAgentConfigProviders();
    setProviders(list);
  };

  useEffect(() => {
    quantApiClient
      .listAgentConfigAgents()
      .then(setAgents)
      .catch(() => setAgents([]));
    quantApiClient
      .listAgentConfigProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
    quantApiClient
      .getAgentConfig()
      .then((config) =>
        setCurrent({
          agent: config.agent,
          provider: config.provider,
          model: config.model,
        }),
      )
      .catch(() => setCurrent(null));
  }, []);

  const refreshAgentProviders = async (agentId: AgentId) => {
    const list = await quantApiClient.listAgentConfigProviders(agentId);
    setAgentProviders(list);
  };

  function selectAgent(next: AgentId) {
    setAgent(next);
    setProvider(null);
    setModel(null);
    setModels([]);
    setModelsNote(null);
    setStep("provider");
    void refreshAgentProviders(next);
  }

  async function loadModels(targetProvider: string) {
    if (!agent) return;
    setModelsLoading(true);
    setModels([]);
    setModel(null);
    setModelsNote(null);
    try {
      const fetched = await quantApiClient.listAgentConfigModels(
        agent,
        targetProvider,
      );
      setModels(fetched.items);
      setModelsNote(fetched.note ?? null);
    } catch (caught) {
      setModels([]);
      setModelsNote(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setModelsLoading(false);
    }
  }

  function selectProvider(next: string) {
    setProvider(next);
    setModel(null);
    setModels([]);
    setModelsNote(null);
    setStep("model");
    void loadModels(next);
  }

  // ── Provider 板块操作 ─────────────────────────────────────────────────

  async function saveProvider() {
    if (!selectedProvider) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.upsertAgentProvider({
        provider: selectedProvider,
        apiKey: providerKey,
        kind: "builtin",
        baseUrl: providerBaseUrl || undefined,
      });
      setProviderKey("");
      setProviderBaseUrl("");
      await refreshProviders();
      window.dispatchEvent(new CustomEvent(AGENT_CONFIG_EVENT));
      setNote(t("agent.saved"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function clearProviderKey() {
    if (!selectedProvider) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.upsertAgentProvider({
        provider: selectedProvider,
        apiKey: "",
        kind: "builtin",
      });
      await refreshProviders();
      window.dispatchEvent(new CustomEvent(AGENT_CONFIG_EVENT));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function deleteProvider() {
    if (!selectedProvider) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.deleteAgentProvider(selectedProvider);
      setSelectedProvider(null);
      await refreshProviders();
      window.dispatchEvent(new CustomEvent(AGENT_CONFIG_EVENT));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function addCustomProvider() {
    const name = customName.trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.upsertAgentProvider({
        provider: name,
        apiKey: customApiKey,
        kind: "custom",
        baseUrl: customBaseUrl.trim() || undefined,
      });
      setCustomName("");
      setCustomBaseUrl("");
      setCustomApiKey("");
      setAddingCustom(false);
      await refreshProviders();
      window.dispatchEvent(new CustomEvent(AGENT_CONFIG_EVENT));
      setNote(t("agent.customAdded", { provider: name }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!agent || !provider || !model) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await quantApiClient.saveAgentConfig({ agent, provider, model });
      setCurrent({ agent, provider, model });
      setNote(t("agent.saved"));
      // 通知顶栏刷新当前生效的 Agent / 基座模型徽标。
      window.dispatchEvent(new CustomEvent(AGENT_CONFIG_EVENT));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  const selectedProviderInfo = useMemo(
    () => providers.find((item) => item.provider === selectedProvider),
    [providers, selectedProvider],
  );

  const agentDescriptor = useMemo(
    () => agents.find((item) => item.name === agent),
    [agents, agent],
  );

  return (
    <div className="agent-config">
      <p className="agent-isolation">{t("agent.isolationNote")}</p>

      {/* ── Provider 独立板块 ─────────────────────────────────────────── */}
      <section className="panel agent-provider-board">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("agent.providerBoardTitle")}</span>
            <h2>{t("agent.providerBoardTitle")}</h2>
            <p className="lede">{t("agent.providerBoardHint")}</p>
          </div>
          <button
            type="button"
            className="button button-secondary button-small"
            onClick={() => setAddingCustom((value) => !value)}
          >
            {t("agent.addCustomProvider")}
          </button>
        </div>

        {addingCustom && (
          <div className="agent-other-form">
            <label className="agent-field">
              <span>{t("agent.providerName")}</span>
              <input
                placeholder={t("agent.otherNamePlaceholder")}
                value={customName}
                onChange={(event) => setCustomName(event.target.value)}
              />
            </label>
            <label className="agent-field">
              <span>{t("agent.baseUrl")}</span>
              <input
                placeholder="https://api.example.com/v1"
                value={customBaseUrl}
                onChange={(event) => setCustomBaseUrl(event.target.value)}
              />
            </label>
            <label className="agent-field">
              <span>{t("agent.apiKey")}</span>
              <input
                type="password"
                placeholder={t("agent.apiKeyPlaceholder")}
                value={customApiKey}
                onChange={(event) => setCustomApiKey(event.target.value)}
              />
            </label>
            <p className="muted agent-other-hint">{t("agent.otherBaseUrlHint")}</p>
            <button
              type="button"
              className="button button-primary"
              onClick={addCustomProvider}
              disabled={busy || !customName.trim()}
            >
              {t("agent.saveCustomProvider")}
            </button>
          </div>
        )}

        <div className="agent-choice-grid">
          {providers.map((item) => (
            <button
              key={item.provider}
              type="button"
              className={`agent-choice ${
                selectedProvider === item.provider ? "is-selected" : ""
              }`}
              onClick={() => {
                setSelectedProvider(item.provider);
                setProviderKey("");
                setProviderBaseUrl("");
              }}
            >
              <strong className="mono">{item.provider}</strong>
              <span className="agent-kind-badge mono">
                {item.kind === "custom" ? t("agent.customKind") : t("agent.builtinKind")}
              </span>
              <span>
                {item.hasApiKey
                  ? `${t("agent.apiKeyConfigured")} ${item.maskedKey}`
                  : t("agent.apiKey")}
              </span>
              {item.kind === "custom" && item.baseUrl ? (
                <span className="mono muted">{item.baseUrl}</span>
              ) : null}
            </button>
          ))}
        </div>

        {selectedProvider && selectedProviderInfo && (
          <div className="agent-key-field agent-provider-edit">
            <span>
              {t("agent.editProvider")}：{selectedProvider}
            </span>
            <div className="agent-key-row">
              <input
                type="password"
                placeholder={
                  selectedProviderInfo.hasApiKey
                    ? t("agent.apiKeyReusePlaceholder", {
                        masked: selectedProviderInfo.maskedKey,
                      })
                    : t("agent.apiKeyPlaceholder")
                }
                value={providerKey}
                onChange={(event) => setProviderKey(event.target.value)}
              />
              {selectedProviderInfo.hasApiKey ? (
                <button
                  type="button"
                  className="agent-key-clear"
                  onClick={clearProviderKey}
                  disabled={busy}
                >
                  {t("agent.clearApiKey")}
                </button>
              ) : null}
            </div>
            {selectedProviderInfo.kind === "custom" && (
              <label className="agent-field">
                <span>{t("agent.baseUrl")}</span>
                <input
                  placeholder="https://api.example.com/v1"
                  value={providerBaseUrl}
                  onChange={(event) => setProviderBaseUrl(event.target.value)}
                />
              </label>
            )}
            <p className="muted agent-key-help">{t("agent.apiKeyHelp")}</p>
            <div className="agent-actions">
              <button
                type="button"
                className="button button-primary"
                onClick={saveProvider}
                disabled={busy}
              >
                {t("agent.providerSave")}
              </button>
              {selectedProviderInfo.kind === "custom" ? (
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={deleteProvider}
                  disabled={busy}
                >
                  {t("agent.deleteProvider")}
                </button>
              ) : null}
            </div>
          </div>
        )}
      </section>

      {/* ── Agent 基座模型配置 ─────────────────────────────────────────── */}
      <section className="panel agent-agent-config">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("agent.agentConfigTitle")}</span>
            <h2>{t("agent.agentConfigTitle")}</h2>
            <p className="lede">{t("agent.agentConfigHint")}</p>
          </div>
        </div>

        {current && (current.agent || current.model) && (
          <p className="agent-current mono">
            {t("agent.current")}：{current.agent || "—"} · {current.provider || "—"} ·{" "}
            {current.model || "—"}
          </p>
        )}

        <ol className="agent-steps">
          {(
            [
              { name: "agent", labelKey: "agent.stepAgent" },
              { name: "provider", labelKey: "agent.stepProvider" },
              { name: "model", labelKey: "agent.stepModel" },
            ] as Array<{
              name: Step;
              labelKey: "agent.stepAgent" | "agent.stepProvider" | "agent.stepModel";
            }>
          ).map(({ name, labelKey }) => {
            const reachable =
              name === "agent"
                ? agents.length > 0
                : name === "provider"
                  ? !!agent
                  : !!(agent && provider);
            return (
              <li key={name}>
                <button
                  type="button"
                  className={`agent-step ${step === name ? "is-active" : ""}`}
                  onClick={() => {
                    if (name === "provider" && agent) {
                      setStep("provider");
                    } else if (name === "agent") {
                      setStep("agent");
                    }
                  }}
                  disabled={!reachable || step === name}
                >
                  {t(labelKey)}
                </button>
              </li>
            );
          })}
        </ol>

        {step === "agent" && (
          <div className="agent-choice-grid">
            {agents.map((item) => (
              <button
                key={item.name}
                type="button"
                className="agent-choice"
                onClick={() => selectAgent(item.name)}
              >
                <strong className="mono">{item.name}</strong>
                <span>
                  {item.name === "codex" ? t("agent.codexNote") : t("agent.piNote")}
                </span>
              </button>
            ))}
          </div>
        )}

        {step === "provider" && agent && (
          <div className="agent-panel">
            <p className="muted">
              {t("agent.agentConfigHint")} 当前支持{" "}
              {agentDescriptor?.supportedProviders.length ?? 0} 个内置 + 自定义 Provider。
            </p>
            <div className="agent-choice-grid">
              {agentProviders.map((item) => (
                <button
                  key={item.provider}
                  type="button"
                  className={`agent-choice ${
                    provider === item.provider ? "is-selected" : ""
                  }`}
                  onClick={() => selectProvider(item.provider)}
                >
                  <strong className="mono">{item.provider}</strong>
                  <span className="agent-kind-badge mono">
                    {item.kind === "custom"
                      ? t("agent.customKind")
                      : t("agent.builtinKind")}
                  </span>
                  <span>
                    {item.hasApiKey
                      ? `${t("agent.apiKeyConfigured")} ${item.maskedKey}`
                      : t("agent.apiKey")}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === "model" && (
          <div className="agent-panel">
            <div className="agent-model-head">
              <span className="mono">
                {agent} / {provider}
              </span>
              <button
                type="button"
                className="button button-small"
                onClick={() => provider && loadModels(provider)}
                disabled={modelsLoading}
              >
                {t("agent.refresh")}
              </button>
            </div>

            {modelsLoading ? (
              <p className="muted">{t("agent.modelLoading")}</p>
            ) : models.length ? (
              <div className="agent-model-list">
                {models.map((item) => (
                  <button
                    key={item.model}
                    type="button"
                    className={`agent-model ${
                      model === item.model ? "is-selected" : ""
                    }`}
                    onClick={() => setModel(item.model)}
                  >
                    <strong className="mono">{item.model}</strong>
                    <span className="agent-model-caps mono">
                      {item.context ? `${t("agent.capContext")} ${item.context}` : ""}
                      {item.maxOut ? ` · ${t("agent.capMaxOut")} ${item.maxOut}` : ""}
                      {item.thinking ? ` · ${t("agent.capThinking")}` : ""}
                      {item.images ? ` · ${t("agent.capImages")}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className={`agent-model-note ${modelsNote ? "is-error" : "muted"}`}>
                {modelsNote ?? t("agent.noModels")}
              </p>
            )}

            <label className="agent-field">
              <span>{t("agent.customModel")}</span>
              <input
                placeholder={t("agent.customModel")}
                value={model ?? ""}
                onChange={(event) => setModel(event.target.value)}
              />
            </label>

            <div className="agent-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => agent && setStep("provider")}
              >
                {t("agent.configureMore")}
              </button>
              <button
                type="button"
                className="button button-primary"
                onClick={save}
                disabled={busy || !model}
              >
                {busy ? t("agent.saved") : t("agent.save")}
              </button>
            </div>
          </div>
        )}

        {note && <p className="agent-note">{note}</p>}
        {error && <p className="sc-error">{error}</p>}
      </section>
    </div>
  );
}
