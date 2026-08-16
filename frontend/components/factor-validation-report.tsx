"use client";

import type { FactorValidationReport } from "../lib/types";
import { useI18n } from "./i18n-provider";

interface FactorValidationReportProps {
  report: FactorValidationReport | null;
}

function num(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(4);
}

function pct(value: number | null): string {
  if (value === null) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

export function FactorValidationReportPanel({
  report,
}: FactorValidationReportProps) {
  const { t } = useI18n();
  if (!report) {
    return (
      <section className="panel validation-report">
        <span className="eyebrow">{t("fvr.emptyEyebrow")}</span>
        <h2>{t("fvr.emptyTitle")}</h2>
        <p className="experiment-empty">
          {t("fvr.emptyDetail")}
        </p>
      </section>
    );
  }

  const power = report.predictivePower;

  return (
    <section
      className="panel validation-report"
      aria-labelledby="validation-title"
    >
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">{t("fvr.eyebrow")}</span>
          <h2 id="validation-title">{t("fvr.title")}</h2>
        </div>
      </div>

      <div className="experiment-hashes">
        <div>
          <span className="eyebrow">{t("fvr.policy")}</span>
          <span className="mono">{report.policyId}</span>
        </div>
        <div>
          <span className="eyebrow">{t("fvr.label")}</span>
          <span className="mono">{report.labelId}</span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fvr.predictive")}</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>{t("fvr.meanPearsonIc")}</span>
            <strong>{num(power.meanPearsonIc)}</strong>
          </div>
          <div>
            <span>{t("fvr.meanRankIc")}</span>
            <strong>{num(power.meanRankIc)}</strong>
          </div>
          <div>
            <span>{t("fvr.icir")}</span>
            <strong>{num(power.icir)}</strong>
          </div>
          <div>
            <span>{t("fvr.neweyWest")}</span>
            <strong>{num(power.nwT)}</strong>
          </div>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fvr.quantileReturns")}</span>
        </div>
        <div className="validation-metrics">
          {power.quantileReturns.map((item) => (
            <div key={item.quantile}>
              <span>Q{item.quantile}</span>
              <strong>{pct(item.meanReturn)}</strong>
            </div>
          ))}
        </div>
        <div className="spread-row">
          <span>{t("fvr.topBottom")}</span>
          <strong>{pct(power.topBottomSpread)}</strong>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fvr.dataQuality")}</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>{t("fvr.coverage")}</span>
            <strong>{pct(report.dataQuality.coverageRatio)}</strong>
          </div>
          <div>
            <span>{t("fvr.constantRatio")}</span>
            <strong>{pct(report.dataQuality.constantRatio)}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}
