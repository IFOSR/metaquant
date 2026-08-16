"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "../../components/i18n-provider";
import { KillSwitch } from "../../components/kill-switch";
import { quantApiClient } from "../../lib/client";
import type { ExecutionState } from "../../lib/types";

export default function ExecutionPage() {
  const { t } = useI18n();
  const [state, setState] = useState<ExecutionState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    quantApiClient
      .getExecutionState()
      .then(setState)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : t("exec.failedToLoad")),
      );
  }, [t]);

  const onTrip = useCallback(
    (reason: string) => quantApiClient.tripKillSwitch(reason),
    [],
  );
  const onReset = useCallback(() => quantApiClient.resetKillSwitch(), []);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("exec.eyebrow")}</span>
          <h1>{t("exec.title")}</h1>
          <p className="lede">
            {t("exec.lede")}
          </p>
        </div>
      </div>

      {error ? (
        <div className="freshness-banner" role="alert">
          <strong>{t("exec.unavailable")}</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {state ? (
        <KillSwitch initialState={state} onTrip={onTrip} onReset={onReset} />
      ) : (
        <p className="muted">{t("exec.loading")}</p>
      )}

      <section className="panel panel-dark">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("exec.contractEyebrow")}</span>
            <h2>{t("exec.contractTitle")}</h2>
          </div>
        </div>
        <ul className="contract-list">
          <li>{t("exec.contract1")}</li>
          <li>{t("exec.contract2")}</li>
          <li>{t("exec.contract3")}</li>
          <li>{t("exec.contract4")}</li>
        </ul>
      </section>
    </div>
  );
}
