"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { getVisibleNavigation, ENV_LABEL_KEYS, MARKET_LABEL_KEYS } from "../lib/domain";
import { quantApiClient } from "../lib/client";
import type { Environment, MarketId, Session } from "../lib/types";
import { useI18n } from "./i18n-provider";
import { StateBoundary } from "./state-boundary";

const AGENT_CONFIG_EVENT = "quant:agent-config-changed";

export function WorkbenchShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const [session, setSession] = useState<Session | null>(null);
  const [environment, setEnvironment] = useState<Environment>("RESEARCH");
  const [market, setMarket] = useState<MarketId>("CN_COMMODITY_FUTURES");
  const [baseModel, setBaseModel] = useState<string | null>(null);

  const refreshBaseModel = useCallback(() => {
    quantApiClient
      .getAgentConfig()
      .then((config) => {
        const parts = [config.agent, config.provider, config.model].filter(
          (part) => part && part.trim(),
        );
        setBaseModel(parts.length ? parts.join(" · ") : null);
      })
      .catch(() => setBaseModel(null));
  }, []);

  useEffect(() => {
    void quantApiClient.getSession().then(setSession);
  }, []);

  useEffect(() => {
    refreshBaseModel();
    const handler = () => refreshBaseModel();
    window.addEventListener(AGENT_CONFIG_EVENT, handler);
    return () => window.removeEventListener(AGENT_CONFIG_EVENT, handler);
  }, [refreshBaseModel]);

  if (!session) {
    return (
      <main className="shell-loading">
        <StateBoundary
          state="loading"
          title={t("shell.loading.title")}
          detail={t("shell.loading.detail")}
        />
      </main>
    );
  }

  const visibleNavigation = getVisibleNavigation(session.capabilities);
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="wordmark" href="/">
          <span className="wordmark-kicker">{t("shell.wordmarkKicker")}</span>
          <span className="wordmark-title">{t("shell.wordmark")}</span>
        </Link>
        <div className="topbar-context">
          <label className="context-select">
            <span>{t("shell.environment")}</span>
            <select
              aria-label={t("shell.environment")}
              value={environment}
              onChange={(event) =>
                setEnvironment(event.target.value as Environment)
              }
            >
              {session.environments.map((env) => (
                <option key={env} value={env}>
                  {t(ENV_LABEL_KEYS[env])}
                </option>
              ))}
            </select>
          </label>
          <label className="context-select">
            <span>{t("shell.market")}</span>
            <select
              aria-label={t("shell.market")}
              value={market}
              onChange={(event) => setMarket(event.target.value as MarketId)}
            >
              {session.markets.map((marketId) => (
                <option key={marketId} value={marketId}>
                  {t(MARKET_LABEL_KEYS[marketId])}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="actor-context">
          <span className="online-dot" aria-hidden="true" />
          <span>{session.actor.displayName}</span>
          <span className="mono">{t("shell.actorBadge")}</span>
          {baseModel ? (
            <span className="actor-model mono" title={t("shell.baseModel")}>
              {baseModel}
            </span>
          ) : null}
          <Link className="actor-link" href="/settings/agent">
            {t("shell.agentConfig")}
          </Link>
        </div>
      </header>
      <div className="shell-body">
        <aside className="sidebar" aria-label={t("shell.navAria")}>
          <div className="sidebar-intro">
            <span className="eyebrow">{t("shell.sidebar.eyebrow")}</span>
            <p>{t("shell.sidebar.intro")}</p>
          </div>
          <nav className="nav-list">
            {visibleNavigation.map((item) => (
              <Link
                className={`nav-link ${pathname === item.href ? "is-active" : ""}`}
                href={item.href}
                key={item.href}
              >
                <span className="nav-marker">{item.marker}</span>
                <span>{t(item.labelKey)}</span>
              </Link>
            ))}
          </nav>
          <div className="sidebar-foot">
            <span className="eyebrow">{t("shell.sidebar.scopeEyebrow")}</span>
            <strong>{t(MARKET_LABEL_KEYS[market])}</strong>
            <span className="mono">{t("shell.sidebar.scopeValue")}</span>
          </div>
        </aside>
        <main className="main-content">
          <div className="evidence-rail" aria-hidden="true">
            <span>{t("shell.rail.env", { env: t(ENV_LABEL_KEYS[environment]) })}</span>
            <span>{t("shell.rail.market", { market: t(MARKET_LABEL_KEYS[market]) })}</span>
            <span>{t("shell.rail.policy")}</span>
          </div>
          <div className="content-wrap">{children}</div>
        </main>
      </div>
    </div>
  );
}
