import Link from "next/link";

import { ExperimentActions } from "../../../../components/experiment-actions";
import { ExperimentMonitor } from "../../../../components/experiment-monitor";
import { FactorProfilePanel } from "../../../../components/factor-profile-panel";
import { FactorValidationReportPanel } from "../../../../components/factor-validation-report";
import { IndependencePanel } from "../../../../components/independence-panel";
import { LineagePanel } from "../../../../components/lineage-panel";
import { PromotionPanel } from "../../../../components/promotion-panel";
import { ResearchJobSnapshot } from "../../../../components/research-job-snapshot";
import { StatusChip } from "../../../../components/status-chip";
import { MARKET_LABEL_KEYS } from "../../../../lib/domain";
import { quantApiClient } from "../../../../lib/client";
import { getServerT } from "../../../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function ResearchJobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = await getServerT();
  const { id } = await params;
  const job = await quantApiClient.getResearchJob(id);
  const briefVersions = await quantApiClient.listBriefVersions(id);
  const frozenBrief = briefVersions.find((item) => item.status === "FROZEN") ?? null;
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
        <Link href="/research/jobs">{t("jobs.title")}</Link>
        <span>/</span>
        <span className="mono">{job.id}</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("detail.marketEyebrow", { market: t(MARKET_LABEL_KEYS[job.market]) })}</span>
          <h1>{job.title}</h1>
          <div className="heading-meta">
            <StatusChip state={job.state} />
            <span className="mono">v{job.version}</span>
            <span>{job.owner}</span>
          </div>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">{t("detail.freshness")}</span>
          {job.freshness ? (
            <>
              <strong>{isStale ? t("detail.stale") : t("detail.current")}</strong>
              <span className="mono">{job.freshness.asOf}</span>
            </>
          ) : (
            <strong>{t("detail.notReturned")}</strong>
          )}
        </div>
      </div>
      {isStale ? (
        <div className="freshness-banner" role="alert">
          <strong>{t("detail.readOnlyUntilRefresh")}</strong>
          {job.freshness?.staleReason ? <span>{job.freshness.staleReason}</span> : null}
          <button className="button button-small" type="button">{t("detail.refetch")}</button>
        </div>
      ) : null}
      <div className="detail-grid">
        <ResearchJobSnapshot job={job} />
        <aside className="evidence-column">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("detail.briefEyebrow")}</span>
                <h2>{t("detail.versionHistory")}</h2>
              </div>
            </div>
            <Link className="text-link" href={`/research/jobs/${job.id}/brief`}>{t("detail.openBriefEditor")}</Link>
          </section>
          {job.blockers.length ? (
            <section className="panel panel-warning">
              <span className="eyebrow">{t("detail.blockers")}</span>
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
      <ExperimentActions
        jobId={job.id}
        market={job.market}
        experimentId={experiment?.id ?? null}
        hasRun={run !== null}
        frozenBriefId={frozenBrief?.id ?? null}
      />
      <ExperimentMonitor
        experiment={experiment}
        run={run}
        artifacts={artifacts}
      />
      {experiment ? (
        <FactorProfilePanel brief={frozenBrief} experiment={experiment} />
      ) : null}
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
