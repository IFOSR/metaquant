"use client";

import { stageLabelKey } from "../lib/domain";
import type { ResearchJob } from "../lib/types";
import { useI18n } from "./i18n-provider";

export function ResearchJobSnapshot({ job }: { job: ResearchJob }) {
  const { t } = useI18n();
  const stageKey = job.currentStage ? stageLabelKey(job.currentStage) : null;
  const hasExecutionSnapshot =
    job.currentStage !== null ||
    job.latestAttempt !== null ||
    job.budgetUsed !== null ||
    job.snapshotRefs.length > 0 ||
    job.policyVersion !== null ||
    job.runFingerprint !== null;

  if (!hasExecutionSnapshot) {
    return (
      <section className="panel">
        <span className="eyebrow">{t("snapshot.eyebrow")}</span>
        <h2>{t("snapshot.empty")}</h2>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{t("snapshot.eyebrow")}</span>
          {job.currentStage ? (
            <h2>{stageKey ? t(stageKey) : job.currentStage}</h2>
          ) : null}
        </div>
        {job.latestAttempt ? (
          <span className="mono">
            {t("snapshot.attempt", {
              attempt: job.latestAttempt.attempt,
              state: job.latestAttempt.state,
            })}
          </span>
        ) : null}
      </div>

      {job.latestAttempt?.heartbeatAt ? (
        <div className="snapshot-row">
          <span className="eyebrow">{t("snapshot.heartbeat")}</span>
          <span className="mono">{job.latestAttempt.heartbeatAt}</span>
        </div>
      ) : null}

      {job.budgetUsed ? (
        <div className="metrics-row">
          <div>
            <span className="eyebrow">{t("snapshot.candidates")}</span>
            <strong>
              {job.budgetUsed.candidates} / {job.budget.candidateLimit}
            </strong>
          </div>
          <div>
            <span className="eyebrow">{t("snapshot.cpuHours")}</span>
            <strong>
              {job.budgetUsed.cpuHours} / {job.budget.cpuHours}
            </strong>
          </div>
          <div>
            <span className="eyebrow">{t("snapshot.wallClock")}</span>
            <strong>
              {job.budgetUsed.wallClockMinutes}m / {job.budget.wallClockMinutes}m
            </strong>
          </div>
        </div>
      ) : null}

      {job.snapshotRefs.length || job.policyVersion || job.runFingerprint ? (
        <div className="snapshot-references">
          <span className="eyebrow">{t("snapshot.references")}</span>
          <ul className="reference-list">
            {job.snapshotRefs.map((reference) => (
              <li className="mono" key={reference}>
                {reference}
              </li>
            ))}
            {job.policyVersion ? <li className="mono">{job.policyVersion}</li> : null}
            {job.runFingerprint ? (
              <li className="mono">{job.runFingerprint}</li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
