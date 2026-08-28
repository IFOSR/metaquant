"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

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

  const counts = useMemo(
    () => ({
      all: items.length,
      factor: items.filter((item) => item.kind === "factor").length,
      strategy: items.filter((item) => item.kind === "strategy").length,
    }),
    [items],
  );

  const filtered = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.kind === filter)),
    [items, filter],
  );

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
      </div>

      <div className="home-feed-list">
        {filtered.map((item) => (
          <Link className="home-feed-row" href={item.href} key={`${item.kind}-${item.id}`}>
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
            <span className="home-feed-open" aria-hidden="true">
              →
            </span>
          </Link>
        ))}
        {filtered.length === 0 && (
          <p className="muted home-feed-empty">{t("home.emptyResearch")}</p>
        )}
      </div>
    </div>
  );
}
