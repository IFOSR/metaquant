"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { quantApiClient } from "../lib/client";
import type { MarketId } from "../lib/types";
import { useI18n } from "./i18n-provider";

export function PaperPipeline() {
  const { t } = useI18n();
  const router = useRouter();
  const [paperText, setPaperText] = useState("");
  const [market, setMarket] = useState<MarketId>("CN_COMMODITY_FUTURES");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!paperText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await quantApiClient.createResearchFromPaper(
        paperText.trim(),
        market,
      );
      router.push(`/research/jobs/${result.jobId}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <span className="eyebrow">{t("pipeline.eyebrow")}</span>
      <h2>{t("pipeline.title")}</h2>
      <p className="lede">{t("pipeline.lede")}</p>
      <label className="field field-wide">
        <span>{t("brief.paperText")}</span>
        <textarea
          value={paperText}
          onChange={(event) => setPaperText(event.target.value)}
          rows={8}
          placeholder={t("brief.paperPlaceholder")}
        />
      </label>
      <div className="field-grid">
        <label className="field">
          <span>{t("pipeline.market")}</span>
          <select
            value={market}
            onChange={(event) => setMarket(event.target.value as MarketId)}
          >
            <option value="CN_COMMODITY_FUTURES">商品期货</option>
            <option value="CN_A">A 股</option>
          </select>
        </label>
      </div>
      {error ? (
        <div className="form-errors" role="alert">
          <span>{error}</span>
        </div>
      ) : null}
      <div className="form-actions">
        <button
          className="button button-primary"
          type="button"
          disabled={busy || !paperText.trim()}
          onClick={create}
        >
          {busy ? t("pipeline.busy") : t("pipeline.create")}
        </button>
      </div>
    </section>
  );
}
