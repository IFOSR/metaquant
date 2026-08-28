import Link from "next/link";

import { quantApiClient } from "../lib/client";
import {
  factorStageFromState,
  MARKET_LABEL_KEYS,
  RESEARCH_KIND_LABEL_KEYS,
  RESEARCH_STAGE_LABEL_KEYS,
} from "../lib/domain";
import { getServerT } from "../lib/server-locale";
import { HomeFeed, type HomeResearch } from "../components/home-feed";

export const dynamic = "force-dynamic";

const LIFECYCLE_STAGES: Array<HomeResearch["stage"]> = [
  "CREATING",
  "READY",
  "CODE_TESTED",
  "BACKTESTED",
  "PAPER_LINKED",
];

export default async function HomePage() {
  const t = await getServerT();
  const [jobs, drafts] = await Promise.all([
    quantApiClient.listResearchJobs(),
    quantApiClient.listStrategyDrafts(),
  ]);

  const factors: HomeResearch[] = jobs.map((job) => ({
    id: job.id,
    kind: "factor",
    title: job.title,
    market: job.market,
    stage: factorStageFromState(job.state),
    updatedAt: job.updatedAt,
    href: `/research/jobs/${job.id}`,
  }));
  const strategies: HomeResearch[] = drafts.map((draft) => ({
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
  const stageCounts = research.reduce<Record<string, number>>((acc, item) => {
    acc[item.stage] = (acc[item.stage] ?? 0) + 1;
    return acc;
  }, {});

  const kpis = [
    {
      key: "research",
      label: t("home.researchCount"),
      value: research.length,
      sub: `${factors.length} ${t(RESEARCH_KIND_LABEL_KEYS.factor)} · ${strategies.length} ${t(RESEARCH_KIND_LABEL_KEYS.strategy)}`,
      accent: true,
    },
    {
      key: "running",
      label: t("home.runningJobs"),
      value: running,
      sub: t("home.runningSub"),
    },
    {
      key: "blockers",
      label: t("home.policyBlockers"),
      value: blockers,
      sub: t("home.blockerSub"),
    },
    {
      key: "paper",
      label: t("home.paperLinked"),
      value: stageCounts["PAPER_LINKED"] ?? 0,
      sub: t("home.paperSub"),
    },
  ];

  return (
    <div className="page page-overview">
      <div className="page-heading page-heading-compact">
        <div>
          <span className="eyebrow">{t("home.eyebrow")}</span>
          <h1>{t("home.title")}</h1>
          <p className="lede">{t("home.lede")}</p>
        </div>
        <Link className="button button-primary" href="/research/new">
          {t("home.newJob")}
        </Link>
      </div>

      <div className="kpi-strip">
        {kpis.map((kpi) => (
          <div
            key={kpi.key}
            className={`kpi-card ${kpi.accent ? "kpi-accent" : ""}`}
          >
            <span className="kpi-label">{kpi.label}</span>
            <strong className="kpi-value">{kpi.value}</strong>
            <span className="kpi-sub">{kpi.sub}</span>
          </div>
        ))}
      </div>

      <div className="overview-grid">
        <section className="panel home-feed">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("home.taskCenter")}</span>
              <h2>{t("home.recentResearch")}</h2>
            </div>
            <Link className="text-link" href="/research/jobs">
              {t("home.viewAll")} →
            </Link>
          </div>
          <HomeFeed items={research} />
        </section>

        <aside className="overview-rail">
          <section className="panel home-lifecycle">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("home.lifecycle")}</span>
                <h2>{t("home.lifecycle")}</h2>
              </div>
            </div>
            <ol className="home-beacon">
              {LIFECYCLE_STAGES.map((stage) => {
                const count = stageCounts[stage] ?? 0;
                const isLive = stage === "PAPER_LINKED" && count > 0;
                return (
                  <li key={stage} className="beacon-step">
                    <span
                      className={`beacon-dot ${isLive ? "is-live" : ""}`}
                      aria-hidden="true"
                    />
                    <span className="beacon-label">
                      {t(RESEARCH_STAGE_LABEL_KEYS[stage])}
                    </span>
                    <strong
                      className={`beacon-count mono ${
                        count > 0 ? "has-count" : ""
                      }`}
                    >
                      {count}
                    </strong>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="panel home-quick">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{t("home.quickStart")}</span>
                <h2>{t("home.quickStart")}</h2>
              </div>
            </div>
            <div className="quick-links">
              <Link className="quick-link" href="/research/new">
                <span className="quick-link-mark mono">01</span>
                <strong>{t("home.quickLang")}</strong>
              </Link>
              <Link className="quick-link" href="/research/new">
                <span className="quick-link-mark mono">02</span>
                <strong>{t("home.quickPaper")}</strong>
              </Link>
              <Link className="quick-link" href="/backtest">
                <span className="quick-link-mark mono">03</span>
                <strong>{t("home.quickBacktest")}</strong>
              </Link>
            </div>
          </section>
        </aside>
      </div>

      <p className="home-footer-note">{t("home.footerNote")}</p>
    </div>
  );
}
