import Link from "next/link";

import { StatusChip } from "../components/status-chip";
import { quantApiClient } from "../lib/client";
import { MARKET_LABEL_KEYS, stageLabelKey } from "../lib/domain";
import { getServerT } from "../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const t = await getServerT();
  const jobs = await quantApiClient.listResearchJobs();
  const running = jobs.filter((job) => job.state === "RUNNING").length;
  const blockers = jobs.reduce((count, job) => count + job.blockers.length, 0);
  return (
    <div className="page page-overview">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("home.eyebrow")}</span>
          <h1>{t("home.title")}</h1>
          <p className="lede">
            {t("home.lede")}
          </p>
        </div>
        <Link className="button button-primary" href="/research/jobs/new">
          {t("home.newJob")}
        </Link>
      </div>
      <div className="signal-grid">
        <div className="signal-card signal-card-accent">
          <span className="eyebrow">{t("home.runningJobs")}</span>
          <strong>{running}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">{t("home.policyBlockers")}</span>
          <strong>{blockers}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">{t("home.formalBoundary")}</span>
          <strong>1d</strong>
          <span>
            {t(MARKET_LABEL_KEYS.CN_A)} + {t(MARKET_LABEL_KEYS.CN_COMMODITY_FUTURES)}
          </span>
        </div>
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("home.taskCenter")}</span>
              <h2>{t("home.recentResearch")}</h2>
            </div>
            <Link href="/research/jobs">{t("home.viewAll")}</Link>
          </div>
          <div className="task-list">
            {jobs.map((job) => {
              const stageKey = job.currentStage ? stageLabelKey(job.currentStage) : null;
              const stageText = job.currentStage
                ? stageKey
                  ? t(stageKey)
                  : job.currentStage
                : t(MARKET_LABEL_KEYS[job.market]);
              return (
                <Link className="task-row" href={`/research/jobs/${job.id}`} key={job.id}>
                  <span className="task-stage">{stageText}</span>
                  <strong>{job.title}</strong>
                  <StatusChip state={job.state} />
                  <span className="mono muted">{job.updatedAt.slice(0, 10)}</span>
                </Link>
              );
            })}
          </div>
        </section>
        <section className="panel panel-dark">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("home.contractEyebrow")}</span>
              <h2>{t("home.contractTitle")}</h2>
            </div>
          </div>
          <ul className="contract-list">
            <li>{t("home.contract1")}</li>
            <li>{t("home.contract2")}</li>
            <li>{t("home.contract3")}</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
