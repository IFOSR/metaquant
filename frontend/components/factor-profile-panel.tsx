"use client";

import type {
  Experiment,
  FactorIrExpression,
  ResearchBrief,
} from "../lib/types";
import { useI18n } from "./i18n-provider";

interface FactorProfilePanelProps {
  brief: ResearchBrief | null;
  experiment: Experiment | null;
}

function renderExpression(node: FactorIrExpression): string {
  if (node.ref !== undefined) return node.ref;
  if (node.literal !== undefined) return String(node.literal);
  if (node.op) {
    const args = (node.args ?? []).map(renderExpression);
    const params = Object.entries(node.params ?? {}).map(
      ([key, value]) => `${key}=${String(value)}`,
    );
    return `${node.op}(${[...args, ...params].join(", ")})`;
  }
  return "?";
}

export function FactorProfilePanel({
  brief,
  experiment,
}: FactorProfilePanelProps) {
  const { t } = useI18n();
  const ir = experiment?.factorIr ?? null;

  if (!experiment || !ir) {
    return (
      <section className="panel validation-report">
        <span className="eyebrow">{t("fp.eyebrow")}</span>
        <h2>{t("fp.emptyTitle")}</h2>
        <p className="experiment-empty">{t("fp.emptyDetail")}</p>
      </section>
    );
  }

  return (
    <section className="panel validation-report" aria-labelledby="factor-profile-title">
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">{t("fp.eyebrow")}</span>
          <h2 id="factor-profile-title">{t("fp.title")}</h2>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fp.identity")}</span>
        </div>
        <div className="experiment-hashes">
          <div>
            <span className="eyebrow">{t("fp.factorId")}</span>
            <span className="mono">{ir.factorId}</span>
          </div>
          <div>
            <span className="eyebrow">{t("fp.version")}</span>
            <span className="mono">{ir.version}</span>
          </div>
          <div>
            <span className="eyebrow">{t("fp.universe")}</span>
            <span className="mono">{ir.marketScope.universeRef}</span>
          </div>
          <div>
            <span className="eyebrow">{t("fp.frequency")}</span>
            <span className="mono">{ir.marketScope.frequency}</span>
          </div>
        </div>
        <div className="experiment-hashes">
          <div>
            <span className="eyebrow">{t("fp.irHash")}</span>
            <span className="mono">{experiment.factorIrHash}</span>
          </div>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fp.meaning")}</span>
        </div>
        <div className="experiment-hashes">
          <div>
            <span className="eyebrow">{t("fp.expression")}</span>
            <span className="mono">{renderExpression(ir.expression)}</span>
          </div>
          <div>
            <span className="eyebrow">{t("fp.decisionClock")}</span>
            <span className="mono">
              {t("fp.signalTime")} {ir.decisionClock.signalTime} · {t("fp.earliestTrade")}{" "}
              {ir.decisionClock.earliestTradeTime}
            </span>
          </div>
        </div>
        <div className="validation-metrics">
          {ir.inputs.map((input) => (
            <div key={input.alias}>
              <span>
                {input.alias} · {input.unit}
              </span>
              <strong className="mono">{input.fieldRef}</strong>
              <span className="mono">{input.availableTimeRule}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("fp.hypothesisSection")}</span>
        </div>
        {brief ? (
          <>
            <p>{brief.hypothesis}</p>
            <p>{brief.economicMechanism}</p>
            <span className="mono">
              {t("fp.expectedDirection")}: {brief.expectedDirection}
            </span>
          </>
        ) : (
          <p className="experiment-empty">{t("fp.noBrief")}</p>
        )}
      </div>
    </section>
  );
}
