import type {
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
} from "../lib/types";

interface ExperimentMonitorProps {
  experiment: Experiment | null;
  run: ExperimentRun | null;
  artifacts: ExperimentArtifacts | null;
}

function shortBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function EvidenceResult({
  label,
  passed,
}: {
  label: string;
  passed: boolean;
}) {
  return (
    <div className="invariance-check">
      <span className={`evidence-dot ${passed ? "is-pass" : "is-fail"}`} />
      <div>
        <strong>{label}</strong>
        <span>{passed ? "MATCHED" : "MISMATCH"}</span>
      </div>
    </div>
  );
}

export function ExperimentMonitor({
  experiment,
  run,
  artifacts,
}: ExperimentMonitorProps) {
  if (!experiment) {
    return (
      <section className="panel experiment-monitor">
        <span className="eyebrow">Experiment / server record</span>
        <h2>No preregistered experiment</h2>
        <p className="experiment-empty">
          No experiment resource was returned for this ResearchJob.
        </p>
      </section>
    );
  }

  const summary = run?.validationSummary;
  const invariance = run?.invariance;

  return (
    <section className="panel experiment-monitor" aria-labelledby="experiment-title">
      <div className="experiment-heading">
        <div>
          <span className="eyebrow">Experiment / server authoritative</span>
          <h2 id="experiment-title">Experiment record</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>SPEC</b>
            <strong>{experiment.state}</strong>
          </span>
          <span>
            <b>RUN</b>
            <strong>{run?.state ?? "NOT_STARTED"}</strong>
          </span>
        </div>
      </div>

      <div className="experiment-identity">
        <div>
          <span className="eyebrow">Experiment</span>
          <strong className="mono">{experiment.id}</strong>
        </div>
        {run ? (
          <>
            <div>
              <span className="eyebrow">Run / attempts</span>
              <strong className="mono">{run.id}</strong>
              <span>{run.attemptCount}</span>
            </div>
            <div>
              <span className="eyebrow">Run fingerprint</span>
              <strong className="mono">{run.runFingerprint}</strong>
            </div>
          </>
        ) : null}
      </div>

      <div className="experiment-hashes">
        <div>
          <span className="eyebrow">Factor IR hash</span>
          <span className="mono">{experiment.factorIrHash}</span>
        </div>
        <div>
          <span className="eyebrow">Snapshot</span>
          <span className="mono">{experiment.snapshotId}</span>
        </div>
        <div>
          <span className="eyebrow">Snapshot manifest hash</span>
          <span className="mono">{experiment.snapshotManifestHash}</span>
        </div>
      </div>

      <div className="experiment-section-grid">
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">Validation summary</span>
          </div>
          {summary ? (
            <div className="validation-metrics">
              <div>
                <span>Coverage</span>
                <strong>{(summary.coverageRatio * 100).toFixed(2)}%</strong>
              </div>
              <div>
                <span>Finite</span>
                <strong>{summary.finiteCount.toLocaleString("en-US")}</strong>
              </div>
              <div>
                <span>Missing</span>
                <strong>{summary.missingCount.toLocaleString("en-US")}</strong>
              </div>
              <div>
                <span>Total</span>
                <strong>{summary.observationCount.toLocaleString("en-US")}</strong>
              </div>
            </div>
          ) : (
            <p className="experiment-empty">
              No validation summary was committed for this run state.
            </p>
          )}
        </div>

        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">Invariance evidence</span>
          </div>
          {invariance ? (
            <div className="invariance-grid">
              <EvidenceResult
                label="Future truncation"
                passed={invariance.futureTruncationPassed}
              />
              <EvidenceResult
                label="Sentinel isolation"
                passed={invariance.sentinelIsolationPassed}
              />
            </div>
          ) : (
            <p className="experiment-empty">
              No invariance evidence was committed for this run state.
            </p>
          )}
        </div>
      </div>

      <div className="experiment-evidence-grid">
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">Immutable artifacts</span>
            <span>{artifacts?.items.length ?? 0} records</span>
          </div>
          <div className="artifact-list">
            {artifacts?.items.map((artifact) => (
              <div className="artifact-row" key={artifact.contentHash}>
                <div>
                  <strong>{artifact.artifactType}</strong>
                  <span className="mono">{artifact.schemaVersion}</span>
                </div>
                <div>
                  <span className="mono">{artifact.contentHash}</span>
                  <span>{shortBytes(artifact.sizeBytes)}</span>
                </div>
              </div>
            ))}
            {!artifacts?.items.length ? (
              <p className="experiment-empty">No artifact metadata returned.</p>
            ) : null}
          </div>
        </div>

        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">Lineage</span>
            <span>{artifacts?.lineage.length ?? 0} edges</span>
          </div>
          <div className="lineage-list">
            {artifacts?.lineage.map((edge) => (
              <div className="lineage-row" key={edge.edgeHash}>
                <span className="mono">{edge.sourceArtifactHash}</span>
                <strong>{edge.relation}</strong>
                <span className="mono">{edge.targetArtifactHash}</span>
              </div>
            ))}
            {!artifacts?.lineage.length ? (
              <p className="experiment-empty">No lineage edges returned.</p>
            ) : null}
          </div>
        </div>
      </div>

    </section>
  );
}
