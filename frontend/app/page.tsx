import Link from "next/link";

import { quantApiClient } from "../lib/client";
import {
  factorStageFromState,
  MARKET_LABEL_KEYS,
  RESEARCH_KIND_LABEL_KEYS,
  RESEARCH_STAGE_LABEL_KEYS,
} from "../lib/domain";
import { getServerT } from "../lib/server-locale";

export const dynamic = "force-dynamic";

interface UnifiedResearch {
  id: string;
  kind: "factor" | "strategy";
  title: string;
  market: "CN_A" | "CN_COMMODITY_FUTURES";
  stage: "CREATING" | "READY" | "CODE_TESTED" | "BACKTESTED" | "PAPER_LINKED";
  updatedAt: string;
  href: string;
}

export default async function HomePage() {
  const t = await getServerT();
  const [jobs, drafts] = await Promise.all([
    quantApiClient.listResearchJobs(),
    quantApiClient.listStrategyDrafts(),
  ]);

  const factors: UnifiedResearch[] = jobs.map((job) => ({
    id: job.id,
    kind: "factor",
    title: job.title,
    market: job.market,
    stage: factorStageFromState(job.state),
    updatedAt: job.updatedAt,
    href: `/research/jobs/${job.id}`,
  }));
  const strategies: UnifiedResearch[] = drafts.map((draft) => ({
    id: draft.id,
    kind: draft.kind,
    title: draft.title || draft.id,
    market: draft.market,
    stage: draft.stage,
    updatedAt: draft.updatedAt,
    href: `/research/new?draft=${draft.id}`,
  }));

  const research = [...factors, ...strategies].sort((a, b) =>
    b.updatedAt.localeCompare(a.updatedAt),
  );
  const running = jobs.filter((job) => job.state === "RUNNING").length;
  const blockers = jobs.reduce((count, job) => count + job.blockers.length, 0);

  return (
    <div className="page page-overview">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("home.eyebrow")}</span>
          <h1>{t("home.title")}</h1>
          <p className="lede">{t("home.lede")}</p>
        </div>
        <Link className="button button-primary" href="/research/new">
          {t("home.newJob")}
        </Link>
      </div>
      <div className="signal-grid">
        <div className="signal-card signal-card-accent">
          <span className="eyebrow">{t("home.researchCount")}</span>
          <strong>{research.length}</strong>
          <span>
            {factors.length} {t("research.kind.factor")} · {strategies.length}{" "}
            {t("research.kind.strategy")}
          </span>
        </div>
        <div className="signal-card">
          <span className="eyebrow">{t("home.runningJobs")}</span>
          <strong>{running}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">{t("home.policyBlockers")}</span>
          <strong>{blockers}</strong>
        </div>
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("home.taskCenter")}</span>
              <h2>{t("home.recentResearch")}</h2>
            </div>
            <span className="mono muted">{research.length}</span>
          </div>
          <div className="task-list">
            {research.map((item) => (
              <Link className="task-row" href={item.href} key={`${item.kind}-${item.id}`}>
                <span className={`research-kind research-kind-${item.kind}`}>
                  {t(RESEARCH_KIND_LABEL_KEYS[item.kind])}
                </span>
                <strong>{item.title}</strong>
                <span className="task-stage">
                  {t(RESEARCH_STAGE_LABEL_KEYS[item.stage])} ·{" "}
                  {t(MARKET_LABEL_KEYS[item.market])}
                </span>
                <span className="mono muted">{item.updatedAt.slice(0, 10)}</span>
              </Link>
            ))}
            {research.length === 0 && (
              <p className="muted">{t("home.emptyResearch")}</p>
            )}
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
