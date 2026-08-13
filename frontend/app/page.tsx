import Link from "next/link";

import { StatusChip } from "../components/status-chip";
import { quantApiClient } from "../lib/client";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const jobs = await quantApiClient.listResearchJobs();
  const running = jobs.filter((job) => job.state === "RUNNING").length;
  const blockers = jobs.reduce((count, job) => count + job.blockers.length, 0);
  return (
    <div className="page page-overview">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Control plane / research</span>
          <h1>Make every result carry its evidence.</h1>
          <p className="lede">
            A narrow surface for proposing, freezing, running, and reviewing research
            without losing the market rule that made it valid.
          </p>
        </div>
        <Link className="button button-primary" href="/research/jobs/new">
          New ResearchJob
        </Link>
      </div>
      <div className="signal-grid">
        <div className="signal-card signal-card-accent">
          <span className="eyebrow">Running jobs</span>
          <strong>{running}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">Policy blockers</span>
          <strong>{blockers}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">Formal boundary</span>
          <strong>1d</strong>
          <span>CN_A + CN_COMMODITY_FUTURES</span>
        </div>
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Task center</span>
              <h2>Recent research</h2>
            </div>
            <Link href="/research/jobs">View all</Link>
          </div>
          <div className="task-list">
            {jobs.map((job) => (
              <Link className="task-row" href={`/research/jobs/${job.id}`} key={job.id}>
                <span className="task-stage">{job.currentStage ?? job.market}</span>
                <strong>{job.title}</strong>
                <StatusChip state={job.state} />
                <span className="mono muted">{job.updatedAt.slice(0, 10)}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="panel panel-dark">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Operating contract</span>
              <h2>What this surface will not pretend.</h2>
            </div>
          </div>
          <ul className="contract-list">
            <li>Agents propose. The control plane decides.</li>
            <li>Events are hints. GET snapshots are truth.</li>
            <li>Paper and live stay gated until their attestations exist.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
