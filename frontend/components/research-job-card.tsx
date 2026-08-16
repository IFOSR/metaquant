"use client";

import Link from "next/link";

import { stageLabelKey } from "../lib/domain";
import type { ResearchJob } from "../lib/types";
import { useI18n } from "./i18n-provider";
import { StatusChip } from "./status-chip";

export function ResearchJobCard({ job }: { job: ResearchJob }) {
  const { t } = useI18n();
  const stageKey = job.currentStage ? stageLabelKey(job.currentStage) : null;
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
        {job.market === "CN_A" ? t("market.cnA.label") : t("market.cnFutures.label")}
        {job.currentStage ? (
          <>
            {" "}
            <span>/</span> {stageKey ? t(stageKey) : job.currentStage}
          </>
        ) : null}
      </p>
      <div className="job-card-bottom">
        {job.budgetUsed && progress !== null ? (
          <div>
            <span className="eyebrow">{t("jobCard.budget")}</span>
            <strong>
              {job.budgetUsed.candidates} / {job.budget.candidateLimit}
            </strong>
            <div className="meter" aria-label={t("jobCard.budgetAria", { progress })}>
              <span style={{ width: `${progress}%` }} />
            </div>
          </div>
        ) : (
          <span className="mono muted">{t("jobCard.noUsage")}</span>
        )}
        <div className="job-card-meta">
          <span className="eyebrow">{t("jobCard.updated")}</span>
          <span className="mono">{job.updatedAt.slice(11, 16)} CST</span>
        </div>
      </div>
    </Link>
  );
}
