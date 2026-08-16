"use client";

import {
  EXPERIMENT_RUN_STATE_KEYS,
  EXPERIMENT_SPEC_STATE_KEYS,
} from "../lib/domain";
import type {
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
} from "../lib/types";
import { useI18n } from "./i18n-provider";

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
  const { t } = useI18n();
  return (
    <div className="invariance-check">
      <span className={`evidence-dot ${passed ? "is-pass" : "is-fail"}`} />
      <div>
        <strong>{label}</strong>
        <span>{passed ? t("exp.matched") : t("exp.mismatch")}</span>
      </div>
    </div>
  );
}

export function ExperimentMonitor({
  experiment,
  run,
  artifacts,
}: ExperimentMonitorProps) {
  const { t } = useI18n();
  if (!experiment) {
    return (
      <section className="panel experiment-monitor">
        <span className="eyebrow">{t("exp.emptyEyebrow")}</span>
        <h2>{t("exp.emptyTitle")}</h2>
        <p className="experiment-empty">
          {t("exp.emptyDetail")}
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
          <span className="eyebrow">{t("exp.eyebrow")}</span>
          <h2 id="experiment-title">{t("exp.title")}</h2>
        </div>
        <div className="experiment-state-pair">
          <span>
            <b>{t("exp.specLabel")}</b>
            <strong>{t(EXPERIMENT_SPEC_STATE_KEYS[experiment.state])}</strong>
          </span>
          <span>
            <b>{t("exp.runLabel")}</b>
            <strong>
              {run ? t(EXPERIMENT_RUN_STATE_KEYS[run.state]) : t("exp.notStarted")}
            </strong>
          </span>
        </div>
      </div>

      <div className="experiment-identity">
        <div>
          <span className="eyebrow">{t("exp.expEyebrow")}</span>
          <strong className="mono">{experiment.id}</strong>
        </div>
        {run ? (
          <>
            <div>
              <span className="eyebrow">{t("exp.runAttempts")}</span>
              <strong className="mono">{run.id}</strong>
              <span>{t("exp.attempts", { count: run.attemptCount })}</span>
            </div>
            <div>
              <span className="eyebrow">{t("exp.runFingerprint")}</span>
              <strong className="mono">{run.runFingerprint}</strong>
            </div>
          </>
        ) : null}
      </div>

      <div className="experiment-hashes">
        <div>
          <span className="eyebrow">{t("exp.factorIrHash")}</span>
          <span className="mono">{experiment.factorIrHash}</span>
        </div>
        <div>
          <span className="eyebrow">{t("exp.snapshot")}</span>
          <span className="mono">{experiment.snapshotId}</span>
        </div>
        <div>
          <span className="eyebrow">{t("exp.manifestHash")}</span>
          <span className="mono">{experiment.snapshotManifestHash}</span>
        </div>
      </div>

      <div className="experiment-section-grid">
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("exp.validationSummary")}</span>
          </div>
          {summary ? (
            <div className="validation-metrics">
              <div>
                <span>{t("exp.coverage")}</span>
                <strong>{(summary.coverageRatio * 100).toFixed(2)}%</strong>
              </div>
              <div>
                <span>{t("exp.finite")}</span>
                <strong>{summary.finiteCount.toLocaleString("en-US")}</strong>
              </div>
              <div>
                <span>{t("exp.missing")}</span>
                <strong>{summary.missingCount.toLocaleString("en-US")}</strong>
              </div>
              <div>
                <span>{t("exp.total")}</span>
                <strong>{summary.observationCount.toLocaleString("en-US")}</strong>
              </div>
            </div>
          ) : (
            <p className="experiment-empty">
              {t("exp.noValidation")}
            </p>
          )}
        </div>

        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("exp.invariance")}</span>
          </div>
          {invariance ? (
            <div className="invariance-grid">
              <EvidenceResult
                label={t("exp.futureTruncation")}
                passed={invariance.futureTruncationPassed}
              />
              <EvidenceResult
                label={t("exp.sentinelIsolation")}
                passed={invariance.sentinelIsolationPassed}
              />
            </div>
          ) : (
            <p className="experiment-empty">
              {t("exp.noInvariance")}
            </p>
          )}
        </div>
      </div>

      <div className="experiment-evidence-grid">
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("exp.artifacts")}</span>
            <span>{t("exp.records", { count: artifacts?.items.length ?? 0 })}</span>
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
              <p className="experiment-empty">{t("exp.noArtifacts")}</p>
            ) : null}
          </div>
        </div>

        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("exp.lineage")}</span>
            <span>{t("exp.edges", { count: artifacts?.lineage.length ?? 0 })}</span>
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
              <p className="experiment-empty">{t("exp.noLineage")}</p>
            ) : null}
          </div>
        </div>
      </div>

    </section>
  );
}
