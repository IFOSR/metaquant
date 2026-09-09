"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { quantApiClient } from "../lib/client";
import {
  MARKET_LABEL_KEYS,
  RESEARCH_KIND_LABEL_KEYS,
  RESEARCH_STAGE_LABEL_KEYS,
} from "../lib/domain";
import { useI18n } from "./i18n-provider";

export interface HomeResearch {
  id: string;
  kind: "factor" | "strategy";
  title: string;
  market: "CN_A" | "CN_COMMODITY_FUTURES";
  stage: "CREATING" | "READY" | "CODE_TESTED" | "BACKTESTED" | "PAPER_LINKED";
  updatedAt: string;
  href: string;
}

type Filter = "all" | "factor" | "strategy";

export function HomeFeed({ items }: { items: HomeResearch[] }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<Filter>("all");
  const [localItems, setLocalItems] = useState(items);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const counts = useMemo(
    () => ({
      all: localItems.length,
      factor: localItems.filter((item) => item.kind === "factor").length,
      strategy: localItems.filter((item) => item.kind === "strategy").length,
    }),
    [localItems],
  );

  const filtered = useMemo(
    () =>
      filter === "all"
        ? localItems
        : localItems.filter((item) => item.kind === filter),
    [localItems, filter],
  );

  async function deleteStrategy(id: string) {
    if (busy || !window.confirm(t("home.deleteConfirm"))) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.deleteStrategyDraft(id);
      setLocalItems((previous) =>
        previous.filter((item) => !(item.kind === "strategy" && item.id === id)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("home.deleteFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function clearStrategies() {
    if (busy || !window.confirm(t("home.clearConfirm"))) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.clearStrategyDrafts();
      setLocalItems((previous) =>
        previous.filter((item) => item.kind !== "strategy"),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("home.deleteFailed"));
    } finally {
      setBusy(false);
    }
  }

  const tabs: Array<{ key: Filter; label: string; count: number }> = [
    { key: "all", label: t("home.filterAll"), count: counts.all },
    {
      key: "factor",
      label: t(RESEARCH_KIND_LABEL_KEYS.factor),
      count: counts.factor,
    },
    {
      key: "strategy",
      label: t(RESEARCH_KIND_LABEL_KEYS.strategy),
      count: counts.strategy,
    },
  ];

  return (
    <div className="home-feed-bundle">
      <div className="home-feed-tabs" role="tablist" aria-label={t("home.filterAll")}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={filter === tab.key}
            className={`home-feed-tab ${filter === tab.key ? "is-active" : ""}`}
            onClick={() => setFilter(tab.key)}
          >
            {tab.label}
            <span className="home-feed-count mono">{tab.count}</span>
          </button>
        ))}
        {counts.strategy > 0 && (
          <button
            type="button"
            className="home-feed-clear"
            onClick={() => void clearStrategies()}
            disabled={busy}
          >
            {busy ? t("home.deleting") : t("home.clearStrategies")}
          </button>
        )}
      </div>

      {error && <p className="muted home-feed-error">{error}</p>}

      <div className="home-feed-list">
        {filtered.map((item) => (
          <div className="home-feed-row" key={`${item.kind}-${item.id}`}>
            <Link className="home-feed-row-link" href={item.href}>
              <span className={`research-kind research-kind-${item.kind}`}>
                {t(RESEARCH_KIND_LABEL_KEYS[item.kind])}
              </span>
              <strong className="home-feed-title">{item.title}</strong>
              <span className="home-feed-stage mono" data-stage={item.stage}>
                {t(RESEARCH_STAGE_LABEL_KEYS[item.stage])}
                <span className="home-feed-stage-dot" aria-hidden="true" />
              </span>
              <span className="home-feed-meta mono">
                {t(MARKET_LABEL_KEYS[item.market])} · {item.updatedAt.slice(0, 10)}
              </span>
            </Link>
            {item.kind === "strategy" && (
              <button
                type="button"
                className="home-feed-delete"
                onClick={() => void deleteStrategy(item.id)}
                disabled={busy}
                aria-label={t("home.delete")}
              >
                {t("home.delete")}
              </button>
            )}
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="muted home-feed-empty">{t("home.emptyResearch")}</p>
        )}
      </div>
    </div>
  );
}
