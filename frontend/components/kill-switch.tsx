"use client";

import { useState } from "react";

import type { ExecutionState } from "../lib/types";
import { useI18n } from "./i18n-provider";

interface KillSwitchProps {
  initialState: ExecutionState;
  onTrip: (reason: string) => Promise<ExecutionState>;
  onReset: () => Promise<ExecutionState>;
}

export function KillSwitch({ initialState, onTrip, onReset }: KillSwitchProps) {
  const { t } = useI18n();
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
      aria-label={t("kill.ariaLabel")}
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{t("kill.eyebrow")}</span>
          <h2>{t("kill.title")}</h2>
        </div>
        <span
          className={`mono ${tripped ? "" : "muted"}`}
          data-testid="kill-switch-state"
        >
          {t(state.killSwitchState === "TRIPPED" ? "killState.TRIPPED" : "killState.ARMED")}
        </span>
      </div>

      {tripped ? (
        <div className="freshness-banner" role="alert">
          <strong>{t("kill.ordersBlocked")}</strong>
          <span>
            {state.trippedBy ?? t("kill.unknown")} · {state.reason ?? t("kill.noReason")}
          </span>
          <button
            className="button button-small"
            type="button"
            onClick={reset}
            disabled={busy}
          >
            {t("kill.reset")}
          </button>
        </div>
      ) : (
        <div className="kill-switch-form">
          <input
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={t("kill.reasonPlaceholder")}
            aria-label={t("kill.reasonAria")}
          />
          <button
            className="button button-small button-danger"
            type="button"
            onClick={trip}
            disabled={busy || !reason.trim()}
          >
            {t("kill.trip")}
          </button>
        </div>
      )}

      <div className="signal-grid signal-grid-compact">
        <div className="signal-card">
          <span className="eyebrow">{t("kill.shadowPositions")}</span>
          <strong>{Object.keys(state.shadowPositions).length}</strong>
        </div>
        <div className="signal-card">
          <span className="eyebrow">{t("kill.paperPositions")}</span>
          <strong>{Object.keys(state.paperPositions).length}</strong>
        </div>
      </div>
    </section>
  );
}
