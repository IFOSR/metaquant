import Link from "next/link";

import { MARKET_LABELS } from "../lib/domain";
import type { ResearchJob } from "../lib/types";
import { StatusChip } from "./status-chip";

export function ResearchJobCard({ job }: { job: ResearchJob }) {
  const progress = job.budgetUsed
    ? Math.min(
        100,
        Math.round((job.budgetUsed.candidates / job.budget.candidateLimit) * 100),
      )
    : null;
  return (
    <Link className="job-card" href={`/research/jobs/${job.id}`}>
      <div className="job-card-top">
        <span className="mono muted">{job.id}</span>
        <StatusChip state={job.state} />
      </div>
      <h2>{job.title}</h2>
      <p className="job-market">
        {MARKET_LABELS[job.market]}
        {job.currentStage ? (
          <>
            {" "}
            <span>/</span> {job.currentStage}
          </>
        ) : null}
      </p>
      <div className="job-card-bottom">
        {job.budgetUsed && progress !== null ? (
          <div>
            <span className="eyebrow">Candidate budget</span>
            <strong>
              {job.budgetUsed.candidates} / {job.budget.candidateLimit}
            </strong>
            <div className="meter" aria-label={`Candidate budget ${progress}%`}>
              <span style={{ width: `${progress}%` }} />
            </div>
          </div>
        ) : (
          <span className="mono muted">No usage snapshot</span>
        )}
        <div className="job-card-meta">
          <span className="eyebrow">Updated</span>
          <span className="mono">{job.updatedAt.slice(11, 16)} CST</span>
        </div>
      </div>
    </Link>
  );
}
