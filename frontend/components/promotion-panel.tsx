import type { PromotionSummary } from "../lib/types";

interface PromotionPanelProps {
  report: PromotionSummary | null;
}

function num(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(4);
}

export function PromotionPanel({ report }: PromotionPanelProps) {
  if (!report) {
    return (
      <section className="panel promotion-panel">
        <span className="eyebrow">Promotion / server record</span>
        <h2>No promotion decision</h2>
        <p className="experiment-empty">
          No promotion decision was committed for this run.
        </p>
      </section>
    );
  }

  return (
    <section className="panel promotion-panel" aria-labelledby="promotion-title">
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">Promotion / server authoritative</span>
          <h2 id="promotion-title">Promotion decision</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>DISPOSITION</b>
            <strong>{report.disposition}</strong>
          </span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Scorecard</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>Total score</span>
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
          <span className="eyebrow">Hard gates</span>
          <span>{report.gates.length} checks</span>
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
          <span className="eyebrow">Rationale</span>
        </div>
        <p className="experiment-empty">{report.rationale}</p>
      </div>
    </section>
  );
}
