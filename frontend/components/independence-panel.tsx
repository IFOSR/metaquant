import type { IndependenceSummary } from "../lib/types";

interface IndependencePanelProps {
  report: IndependenceSummary | null;
}

function num(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(4);
}

export function IndependencePanel({ report }: IndependencePanelProps) {
  if (!report) {
    return (
      <section className="panel independence-panel">
        <span className="eyebrow">Independence / server record</span>
        <h2>No independence assessment</h2>
        <p className="experiment-empty">
          No independence report was committed for this run.
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
          <span className="eyebrow">Independence / server authoritative</span>
          <h2 id="independence-title">Factor independence</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>REPLICATED</b>
            <strong>{report.replicatedRiskFactor ? "YES" : "NO"}</strong>
          </span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Incremental IC</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>Baseline IC</span>
            <strong>{num(report.baselineIc)}</strong>
          </div>
          <div>
            <span>Orthogonalized IC</span>
            <strong>{num(report.orthogonalizedIc)}</strong>
          </div>
          <div>
            <span>Max abs correlation</span>
            <strong>{num(report.maxAbsCorrelation)}</strong>
          </div>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Pairwise correlation</span>
          <span>{report.pairwise.length} pool factors</span>
        </div>
        {report.pairwise.length ? (
          <div className="artifact-list">
            {report.pairwise.map((item) => (
              <div className="artifact-row" key={item.factorIrHash}>
                <div>
                  <span className="mono">{item.factorIrHash.slice(0, 16)}…</span>
                </div>
                <div>
                  <span>Pearson {num(item.pearson)}</span>
                  <span>Spearman {num(item.spearman)}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="experiment-empty">
            No pool factors to compare against.
          </p>
        )}
      </div>
    </section>
  );
}
