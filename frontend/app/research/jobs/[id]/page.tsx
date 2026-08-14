import Link from "next/link";

import { ExperimentMonitor } from "../../../../components/experiment-monitor";
import { FactorValidationReportPanel } from "../../../../components/factor-validation-report";
import { IndependencePanel } from "../../../../components/independence-panel";
import { LineagePanel } from "../../../../components/lineage-panel";
import { PromotionPanel } from "../../../../components/promotion-panel";
import { ResearchJobSnapshot } from "../../../../components/research-job-snapshot";
import { StatusChip } from "../../../../components/status-chip";
import { MARKET_LABELS } from "../../../../lib/domain";
import { quantApiClient } from "../../../../lib/client";

export const dynamic = "force-dynamic";

export default async function ResearchJobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = await quantApiClient.getResearchJob(id);
  const experiment = job.experimentId
    ? await quantApiClient.getExperiment(job.experimentId)
    : null;
  const run = experiment?.latestRunId
    ? await quantApiClient.getExperimentRun(experiment.latestRunId)
    : null;
  const artifacts = run
    ? await quantApiClient.getExperimentArtifacts(run.id)
    : null;
  const validation = run
    ? await quantApiClient.getExperimentValidation(run.id).catch(() => null)
    : null;
  const independence = run
    ? await quantApiClient.getExperimentIndependence(run.id).catch(() => null)
    : null;
  const promotion = run
    ? await quantApiClient.getExperimentPromotion(run.id).catch(() => null)
    : null;
  const isStale = job.freshness?.isStale ?? false;
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href="/research/jobs">Research jobs</Link>
        <span>/</span>
        <span className="mono">{job.id}</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{MARKET_LABELS[job.market]} / ResearchJob</span>
          <h1>{job.title}</h1>
          <div className="heading-meta">
            <StatusChip state={job.state} />
            <span className="mono">v{job.version}</span>
            <span>{job.owner}</span>
          </div>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">Freshness</span>
          {job.freshness ? (
            <>
              <strong>{isStale ? "STALE SNAPSHOT" : "CURRENT SNAPSHOT"}</strong>
              <span className="mono">{job.freshness.asOf}</span>
            </>
          ) : (
            <strong>NOT RETURNED</strong>
          )}
        </div>
      </div>
      {isStale ? (
        <div className="freshness-banner" role="alert">
          <strong>Read-only until snapshot refresh.</strong>
          {job.freshness?.staleReason ? <span>{job.freshness.staleReason}</span> : null}
          <button className="button button-small" type="button">Refetch snapshot</button>
        </div>
      ) : null}
      <div className="detail-grid">
        <ResearchJobSnapshot job={job} />
        <aside className="evidence-column">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">Research brief</span>
                <h2>Version history</h2>
              </div>
            </div>
            <Link className="text-link" href={`/research/jobs/${job.id}/brief`}>Open brief editor →</Link>
          </section>
          {job.blockers.length ? (
            <section className="panel panel-warning">
              <span className="eyebrow">Blockers</span>
              {job.blockers.map((blocker) => (
                <div className="blocker" key={blocker.code}>
                  <strong>{blocker.title}</strong>
                  <p>{blocker.detail}</p>
                  <span className="mono">{blocker.responsibility}</span>
                </div>
              ))}
            </section>
          ) : null}
        </aside>
      </div>
      <ExperimentMonitor
        experiment={experiment}
        run={run}
        artifacts={artifacts}
      />
      {run ? (
        <div className="evidence-grid">
          <FactorValidationReportPanel report={validation} />
          <IndependencePanel report={independence} />
          <PromotionPanel report={promotion} />
        </div>
      ) : null}
      <LineagePanel artifacts={artifacts} />
    </div>
  );
}
