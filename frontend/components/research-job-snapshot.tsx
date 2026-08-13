import type { ResearchJob } from "../lib/types";

export function ResearchJobSnapshot({ job }: { job: ResearchJob }) {
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
        <span className="eyebrow">Execution snapshot</span>
        <h2>No execution snapshot returned.</h2>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Execution snapshot</span>
          {job.currentStage ? <h2>{job.currentStage}</h2> : null}
        </div>
        {job.latestAttempt ? (
          <span className="mono">
            attempt {job.latestAttempt.attempt} / {job.latestAttempt.state}
          </span>
        ) : null}
      </div>

      {job.latestAttempt?.heartbeatAt ? (
        <div className="snapshot-row">
          <span className="eyebrow">Heartbeat</span>
          <span className="mono">{job.latestAttempt.heartbeatAt}</span>
        </div>
      ) : null}

      {job.budgetUsed ? (
        <div className="metrics-row">
          <div>
            <span className="eyebrow">Candidates</span>
            <strong>
              {job.budgetUsed.candidates} / {job.budget.candidateLimit}
            </strong>
          </div>
          <div>
            <span className="eyebrow">CPU hours</span>
            <strong>
              {job.budgetUsed.cpuHours} / {job.budget.cpuHours}
            </strong>
          </div>
          <div>
            <span className="eyebrow">Wall clock</span>
            <strong>
              {job.budgetUsed.wallClockMinutes}m / {job.budget.wallClockMinutes}m
            </strong>
          </div>
        </div>
      ) : null}

      {job.snapshotRefs.length || job.policyVersion || job.runFingerprint ? (
        <div className="snapshot-references">
          <span className="eyebrow">Returned references</span>
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
