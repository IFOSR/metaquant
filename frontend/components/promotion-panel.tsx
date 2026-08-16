"use client";

import { DISPOSITION_KEYS } from "../lib/domain";
import type { PromotionSummary } from "../lib/types";
import { useI18n } from "./i18n-provider";

interface PromotionPanelProps {
  report: PromotionSummary | null;
}

function num(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(4);
}

export function PromotionPanel({ report }: PromotionPanelProps) {
  const { t } = useI18n();
  if (!report) {
    return (
      <section className="panel promotion-panel">
        <span className="eyebrow">{t("promo.emptyEyebrow")}</span>
        <h2>{t("promo.emptyTitle")}</h2>
        <p className="experiment-empty">
          {t("promo.emptyDetail")}
        </p>
      </section>
    );
  }

  return (
    <section className="panel promotion-panel" aria-labelledby="promotion-title">
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">{t("promo.eyebrow")}</span>
          <h2 id="promotion-title">{t("promo.title")}</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>{t("promo.dispositionLabel")}</b>
            <strong>
              {DISPOSITION_KEYS[report.disposition]
                ? t(DISPOSITION_KEYS[report.disposition])
                : report.disposition}
            </strong>
          </span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("promo.scorecard")}</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>{t("promo.totalScore")}</span>
            <strong>{num(report.totalScore)}</strong>
          </div>
        </div>
        <div className="artifact-list">
          {report.componentScores.map(([name, score]) => (
            <div className="artifact-row" key={name}>
              <div>
                <strong>{name}</strong>
              </div>
              <div>
                <span>{num(score)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("promo.hardGates")}</span>
          <span>{t("promo.checks", { count: report.gates.length })}</span>
        </div>
        <div className="artifact-list">
          {report.gates.map((gate) => (
            <div className="artifact-row" key={gate.name}>
              <div>
                <span className={`evidence-dot ${gate.passed ? "is-pass" : "is-fail"}`} />
                <strong>{gate.name}</strong>
              </div>
              <div>
                <span>
                  {num(gate.observed)} / {num(gate.threshold)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("promo.rationale")}</span>
        </div>
        <p className="experiment-empty">{report.rationale}</p>
      </div>
    </section>
  );
}
