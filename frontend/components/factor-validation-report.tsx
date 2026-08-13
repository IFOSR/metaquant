import type { FactorValidationReport } from "../lib/types";

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
  if (!report) {
    return (
      <section className="panel validation-report">
        <span className="eyebrow">Validation / server record</span>
        <h2>No factor validation</h2>
        <p className="experiment-empty">
          No validation report was committed for this run.
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
          <span className="eyebrow">Validation / server authoritative</span>
          <h2 id="validation-title">Factor validation</h2>
        </div>
      </div>

      <div className="experiment-hashes">
        <div>
          <span className="eyebrow">Policy</span>
          <span className="mono">{report.policyId}</span>
        </div>
        <div>
          <span className="eyebrow">Label</span>
          <span className="mono">{report.labelId}</span>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Predictive power</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>Mean Pearson IC</span>
            <strong>{num(power.meanPearsonIc)}</strong>
          </div>
          <div>
            <span>Mean Rank IC</span>
            <strong>{num(power.meanRankIc)}</strong>
          </div>
          <div>
            <span>ICIR</span>
            <strong>{num(power.icir)}</strong>
          </div>
          <div>
            <span>Newey-West t</span>
            <strong>{num(power.nwT)}</strong>
          </div>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Quantile returns</span>
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
          <span>Top-bottom spread</span>
          <strong>{pct(power.topBottomSpread)}</strong>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">Data quality</span>
        </div>
        <div className="validation-metrics">
          <div>
            <span>Coverage</span>
            <strong>{pct(report.dataQuality.coverageRatio)}</strong>
          </div>
          <div>
            <span>Constant ratio</span>
            <strong>{pct(report.dataQuality.constantRatio)}</strong>
          </div>
        </div>
      </div>
    </section>
  );
}
