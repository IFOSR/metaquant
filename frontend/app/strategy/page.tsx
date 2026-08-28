import Link from "next/link";

import { BacktestLab } from "../../components/backtest-lab";
import { quantApiClient } from "../../lib/client";
import { getServerT } from "../../lib/server-locale";

export const dynamic = "force-dynamic";

function shortHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
}

export default async function StrategyPage() {
  const t = await getServerT();
  const factors = await quantApiClient.listAlphaPool();
  const drafts = await quantApiClient.listStrategyDrafts("FROZEN");

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("strategy.eyebrow")}</span>
          <h1>{t("strategy.title")}</h1>
          <p className="lede">
            {t("strategy.lede")}
          </p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("strategy.alphaPoolEyebrow")}</span>
            <h2>{t("strategy.promotedFactors")}</h2>
          </div>
          <span className="mono muted">{t("strategy.factorCount", { count: factors.length })}</span>
        </div>

        {factors.length ? (
          <div className="task-list">
            {factors.map((factor) => (
              <div className="task-row" key={factor.factorIrHash}>
                <span className="task-stage">{factor.market}</span>
                <strong className="mono">{factor.factorId ?? shortHash(factor.factorIrHash)}</strong>
                <span className="muted">{factor.direction}</span>
                <span className="muted">{t("strategy.horizon", { horizon: factor.horizon })}</span>
                <span className="muted">{t("strategy.oosIc", { value: factor.oosIc?.toFixed(4) ?? "—" })}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">
            {t("strategy.emptyFactors")}
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("strategy.savedEyebrow")}</span>
            <h2>{t("strategy.savedTitle")}</h2>
          </div>
          <span className="mono muted">{t("strategy.savedCount", { count: drafts.length })}</span>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          {t("strategy.savedHint")}
        </p>

        {drafts.length ? (
          <div className="task-list">
            {drafts.map((draft) => (
              <Link
                href={`/strategy/chat?draft=${draft.id}`}
                key={draft.id}
                className="task-row"
                style={{ textDecoration: "none", display: "block" }}
              >
                <span className="task-stage">{draft.market}</span>
                <strong>{draft.title || shortHash(draft.id)}</strong>
                <span className="mono muted">
                  {t("strategy.savedInstruments")}: {draft.instrumentIds.join(" · ")}
                </span>
                <span className="muted">{t("strategy.savedFrequency")}: {draft.frequency}</span>
                <span className="mono muted">
                  {t("strategy.savedHash")}: {draft.contentHash ? shortHash(draft.contentHash) : "—"}
                </span>
                <span className="muted">
                  {t("strategy.savedFrozenAt")} {draft.updatedAt.slice(0, 10)}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="muted">
            {t("strategy.savedEmpty")}
          </p>
        )}
      </section>

      <BacktestLab factors={factors} />

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("strategy.specEyebrow")}</span>
            <h2>{t("strategy.combinationContract")}</h2>
          </div>
        </div>
        <ul className="contract-list">
          <li>{t("strategy.contract1")}</li>
          <li>{t("strategy.contract2")}</li>
          <li>{t("strategy.contract3")}</li>
          <li>{t("strategy.contract4")}</li>
          <li>{t("strategy.contract5")}</li>
        </ul>
      </section>
    </div>
  );
}
