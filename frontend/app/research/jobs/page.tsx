import Link from "next/link";

import { ResearchJobCard } from "../../../components/research-job-card";
import { quantApiClient } from "../../../lib/client";
import { getServerT } from "../../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function ResearchJobsPage() {
  const t = await getServerT();
  const jobs = await quantApiClient.listResearchJobs();
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("jobs.eyebrow")}</span>
          <h1>{t("jobs.title")}</h1>
          <p className="lede">{t("jobs.lede")}</p>
        </div>
        <Link className="button button-primary" href="/research/jobs/new">
          {t("jobs.create")}
        </Link>
      </div>
      <div className="filter-strip">
        <span className="filter-label">{t("jobs.scope")}</span>
        <button className="filter-pill is-selected" type="button">{t("jobs.allMarkets")}</button>
        <button className="filter-pill" type="button">{t("jobs.running")}</button>
        <button className="filter-pill" type="button">{t("jobs.blocked")}</button>
        <span className="filter-spacer" />
        <span className="mono muted">{t("jobs.count", { count: jobs.length })}</span>
      </div>
      <div className="job-grid">
        {jobs.map((job) => (
          <ResearchJobCard job={job} key={job.id} />
        ))}
      </div>
    </div>
  );
}
