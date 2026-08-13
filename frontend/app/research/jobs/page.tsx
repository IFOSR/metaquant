import Link from "next/link";

import { ResearchJobCard } from "../../../components/research-job-card";
import { quantApiClient } from "../../../lib/client";

export const dynamic = "force-dynamic";

export default async function ResearchJobsPage() {
  const jobs = await quantApiClient.listResearchJobs();
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Research / index</span>
          <h1>Research jobs</h1>
          <p className="lede">Every run starts as a versioned brief inside a market boundary.</p>
        </div>
        <Link className="button button-primary" href="/research/jobs/new">
          Create job
        </Link>
      </div>
      <div className="filter-strip">
        <span className="filter-label">Scope</span>
        <button className="filter-pill is-selected" type="button">All markets</button>
        <button className="filter-pill" type="button">Running</button>
        <button className="filter-pill" type="button">Blocked</button>
        <span className="filter-spacer" />
        <span className="mono muted">{jobs.length} authorized records</span>
      </div>
      <div className="job-grid">
        {jobs.map((job) => (
          <ResearchJobCard job={job} key={job.id} />
        ))}
      </div>
    </div>
  );
}
