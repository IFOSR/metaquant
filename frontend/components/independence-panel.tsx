"use client";

import type { IndependenceSummary } from "../lib/types";
import { useI18n } from "./i18n-provider";

interface IndependencePanelProps {
  report: IndependenceSummary | null;
}

function num(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(4);
}

export function IndependencePanel({ report }: IndependencePanelProps) {
  const { t } = useI18n();
  if (!report) {
    return (
      <section className="panel independence-panel">
        <span className="eyebrow">{t("ind.emptyEyebrow")}</span>
        <h2>{t("ind.emptyTitle")}</h2>
        <p className="experiment-empty">
          {t("ind.emptyDetail")}
        </p>
      </section>
    );
  }

  return (
    <section
      className="panel independence-panel"
      aria-labelledby="independence-title"
    >
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">{t("ind.eyebrow")}</span>
          <h2 id="independence-title">{t("ind.title")}</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>{t("ind.replicatedLabel")}</b>
            <strong>{report.replicatedRiskFactor ? t("ind.yes") : t("ind.no")}</strong>
          </span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("ind.incrementalIc")}</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>{t("ind.baselineIc")}</span>
            <strong>{num(report.baselineIc)}</strong>
          </div>
          <div>
            <span>{t("ind.orthogonalizedIc")}</span>
            <strong>{num(report.orthogonalizedIc)}</strong>
          </div>
          <div>
            <span>{t("ind.maxAbsCorr")}</span>
            <strong>{num(report.maxAbsCorrelation)}</strong>
          </div>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("ind.pairwise")}</span>
          <span>{t("ind.poolFactors", { count: report.pairwise.length })}</span>
        </div>
        {report.pairwise.length ? (
          <div className="artifact-list">
            {report.pairwise.map((item) => (
              <div className="artifact-row" key={item.factorIrHash}>
                <div>
                  <span className="mono">{item.factorIrHash.slice(0, 16)}…</span>
                </div>
                <div>
                  <span>{t("ind.pearson", { value: num(item.pearson) })}</span>
                  <span>{t("ind.spearman", { value: num(item.spearman) })}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="experiment-empty">
            {t("ind.emptyPool")}
          </p>
        )}
      </div>
    </section>
  );
}
