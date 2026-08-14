import { quantApiClient } from "../../lib/client";

export const dynamic = "force-dynamic";

function shortHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
}

export default async function StrategyPage() {
  const factors = await quantApiClient.listAlphaPool();

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FR-705 / Strategy</span>
          <h1>Alpha Pool and strategy surface.</h1>
          <p className="lede">
            Promoted factors, their promotion evidence, and the combination and
            attribution that turn them into a backtestable strategy.
          </p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Alpha Pool</span>
            <h2>Promoted factors</h2>
          </div>
          <span className="mono muted">{factors.length} factors</span>
        </div>

        {factors.length ? (
          <div className="task-list">
            {factors.map((factor) => (
              <div className="task-row" key={factor.factorIrHash}>
                <span className="task-stage">{factor.market}</span>
                <strong className="mono">{shortHash(factor.factorIrHash)}</strong>
                <span className="muted">{factor.direction}</span>
                <span className="muted">horizon {factor.horizon}d</span>
                <span className="muted">OOS IC {factor.oosIc?.toFixed(4) ?? "—"}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">
            No promoted factors yet. Factors enter the Alpha Pool only after they
            pass every gate and a two-person approval.
          </p>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">StrategySpec</span>
            <h2>Combination contract</h2>
          </div>
        </div>
        <ul className="contract-list">
          <li>Factor weights are IC-shrunk toward equal weight (MVP combine).</li>
          <li>Constraints: long-only, full investment, single-name cap, holding count.</li>
          <li>Risk model: factor-exposure neutrality and tracking-error penalty.</li>
          <li>Backtest: five-clock engine with T+1 and price-limit semantics.</li>
          <li>Attribution: gross/net, cost, exposure, capacity, unfillable, roll.</li>
        </ul>
      </section>
    </div>
  );
}
