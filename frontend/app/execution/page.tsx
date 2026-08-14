"use client";

import { useCallback, useEffect, useState } from "react";

import { KillSwitch } from "../../components/kill-switch";
import { quantApiClient } from "../../lib/client";
import type { ExecutionState } from "../../lib/types";

export default function ExecutionPage() {
  const [state, setState] = useState<ExecutionState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    quantApiClient
      .getExecutionState()
      .then(setState)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Failed to load"),
      );
  }, []);

  const onTrip = useCallback(
    (reason: string) => quantApiClient.tripKillSwitch(reason),
    [],
  );
  const onReset = useCallback(() => quantApiClient.resetKillSwitch(), []);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FR-706 / Execution</span>
          <h1>Paper and live operations.</h1>
          <p className="lede">
            Shadow and paper state, order safety, reconciliation, and the kill
            switch that overrides every order when tripped.
          </p>
        </div>
      </div>

      {error ? (
        <div className="freshness-banner" role="alert">
          <strong>Execution state unavailable.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {state ? (
        <KillSwitch initialState={state} onTrip={onTrip} onReset={onReset} />
      ) : (
        <p className="muted">Loading execution state…</p>
      )}

      <section className="panel panel-dark">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Operating contract</span>
            <h2>Live safety invariants.</h2>
          </div>
        </div>
        <ul className="contract-list">
          <li>Notional caps and max order quantity are enforced before any order.</li>
          <li>A tripped kill switch blocks every order until explicitly reset.</li>
          <li>Shadow trading only produces suggestions — it never sends real orders.</li>
          <li>Broker positions are reconciled against expected positions.</li>
        </ul>
      </section>
    </div>
  );
}
