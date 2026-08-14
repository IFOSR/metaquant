"use client";

import { useState } from "react";

import type { ExecutionState } from "../lib/types";

interface KillSwitchProps {
  initialState: ExecutionState;
  onTrip: (reason: string) => Promise<ExecutionState>;
  onReset: () => Promise<ExecutionState>;
}

export function KillSwitch({ initialState, onTrip, onReset }: KillSwitchProps) {
  const [state, setState] = useState(initialState);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const tripped = state.killSwitchState === "TRIPPED";

  async function trip() {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      setState(await onTrip(reason.trim()));
      setReason("");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      setState(await onReset());
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className={`panel ${tripped ? "panel-warning" : ""}`}
      aria-label="Kill switch"
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">FR-706 / Execution safety</span>
          <h2>Kill switch</h2>
        </div>
        <span
          className={`mono ${tripped ? "" : "muted"}`}
          data-testid="kill-switch-state"
        >
          {state.killSwitchState}
        </span>
      </div>

      {tripped ? (
        <div className="freshness-banner" role="alert">
          <strong>Orders blocked.</strong>
          <span>
            {state.trippedBy ?? "unknown"} · {state.reason ?? "no reason recorded"}
          </span>
          <button
            className="button button-small"
            type="button"
            onClick={reset}
            disabled={busy}
          >
            Reset kill switch
          </button>
        </div>
      ) : (
        <div className="kill-switch-form">
          <input
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason for tripping the kill switch"
            aria-label="Kill switch reason"
          />
          <button
            className="button button-small button-danger"
            type="button"
            onClick={trip}
            disabled={busy || !reason.trim()}
          >
            Trip kill switch
          </button>
        </div>
      )}

      <div className="signal-grid signal-grid-compact">
        <div className="signal-card">
          <span className="eyebrow">Shadow positions</span>
          <strong>{Object.keys(state.shadowPositions).length}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">Paper positions</span>
          <strong>{Object.keys(state.paperPositions).length}</strong>
        </div>
      </div>
    </section>
  );
}
