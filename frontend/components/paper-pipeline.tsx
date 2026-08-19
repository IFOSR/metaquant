"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { quantApiClient } from "../lib/client";
import type { MarketId } from "../lib/types";
import { useI18n } from "./i18n-provider";

export function PaperPipeline() {
  const { t } = useI18n();
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [market, setMarket] = useState<MarketId>("CN_COMMODITY_FUTURES");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pickFile(files: FileList | null) {
    const first = files?.[0];
    if (first) setFile(first);
  }

  async function create() {
    if (!prompt.trim() && !file) return;
    setBusy(true);
    setError(null);
    try {
      const result = file
        ? await quantApiClient.createResearchFromPaperFile(
            file,
            prompt.trim(),
            market,
          )
        : await quantApiClient.createResearchFromPaper(prompt.trim(), market);
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
        <span>{t("pipeline.prompt")}</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={5}
          placeholder={t("pipeline.promptPlaceholder")}
        />
      </label>
      <div className="brief-template-row">
        <div className="field">
          <span>{t("pipeline.market")}</span>
          <select
            value={market}
            onChange={(event) => setMarket(event.target.value as MarketId)}
          >
            <option value="CN_COMMODITY_FUTURES">商品期货</option>
            <option value="CN_A">A 股</option>
          </select>
        </div>
        <div className="field">
          <span>{t("pipeline.attachment")}</span>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={(event) => pickFile(event.target.files)}
          />
        </div>
        {file ? (
          <span className="mono provision-status provision-done">
            ✓ {file.name}
          </span>
        ) : null}
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
          disabled={busy || (!prompt.trim() && !file)}
          onClick={create}
        >
          {busy ? t("pipeline.busy") : t("pipeline.create")}
        </button>
      </div>
    </section>
  );
}
