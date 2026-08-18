"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { quantApiClient } from "../lib/client";
import type { FormalSnapshotInfo, MarketId } from "../lib/types";
import { useI18n } from "./i18n-provider";

const CN_A_TEMPLATE = {
  schema_version: "factor-ir/v1",
  factor_id: "classic.cn_a.momentum_5d",
  version: "1.0.0",
  market_scope: {
    market: "CN_A",
    frequency: "1d",
    universe_ref: "universe://csi300-pit/v1",
  },
  decision_clock: {
    signal_time: "T_CLOSE+30m",
    earliest_trade_time: "T+1_OPEN",
  },
  inputs: [
    {
      alias: "close",
      field_ref: "market.eod.close_adjusted",
      data_type: "ScalarSeries",
      unit: "CNY",
      available_time_rule: "T_CLOSE+20m",
    },
  ],
  expression: {
    op: "returns",
    args: [{ ref: "close" }],
    params: { periods: 5 },
  },
  validation_policy_ref: "policy://cn-a-daily-factor/v1",
};

const FUTURES_TEMPLATE = {
  schema_version: "factor-ir/v1",
  factor_id: "classic.cn_futures.momentum_5d",
  version: "1.0.0",
  market_scope: {
    market: "CN_COMMODITY_FUTURES",
    frequency: "1d",
    universe_ref: "futures:liquid-initial",
    exchange_scope: ["SHFE"],
    contract_chain_ref: "chain://shfe-rb/v1",
    roll_policy_ref: "roll-policy://oi-confirmed-3d/v1",
  },
  decision_clock: {
    signal_time: "T_CLOSE+30m",
    earliest_trade_time: "T+1_OPEN",
  },
  inputs: [
    {
      alias: "close",
      field_ref: "market.eod.close",
      data_type: "ScalarSeries",
      unit: "CNY",
      available_time_rule: "T_CLOSE+20m",
    },
  ],
  expression: {
    op: "returns",
    args: [{ ref: "close" }],
    params: { periods: 5 },
  },
  validation_policy_ref: "policy://cn-futures-daily-factor/v1",
};

function defaultDecisionTime(frozenAt: string | null): string {
  if (!frozenAt) return new Date().toISOString();
  const base = new Date(frozenAt);
  if (Number.isNaN(base.getTime())) return new Date().toISOString();
  base.setUTCDate(base.getUTCDate() - 5);
  return base.toISOString();
}

function isoToLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface ExperimentActionsProps {
  jobId: string;
  market: MarketId;
  experimentId: string | null;
  hasRun: boolean;
  frozenBriefId: string | null;
}

export function ExperimentActions({
  jobId,
  market,
  experimentId,
  hasRun,
  frozenBriefId,
}: ExperimentActionsProps) {
  const { t } = useI18n();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<FormalSnapshotInfo[]>([]);
  const [snapshotId, setSnapshotId] = useState("");
  const [irText, setIrText] = useState("");
  const [decisionTime, setDecisionTime] = useState(() =>
    new Date().toISOString(),
  );
  const [seed, setSeed] = useState(42);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    quantApiClient
      .listFormalSnapshots()
      .then(setSnapshots)
      .catch(() => setSnapshots([]));
  }, []);

  function openForm() {
    setIrText(
      JSON.stringify(
        market === "CN_A" ? CN_A_TEMPLATE : FUTURES_TEMPLATE,
        null,
        2,
      ),
    );
    const match =
      snapshots.find((item) => item.market === market) ?? snapshots[0];
    setSnapshotId(match?.snapshotId ?? "");
    setDecisionTime(defaultDecisionTime(match?.frozenAt ?? null));
    setError(null);
    setOpen(true);
  }

  async function submitPreregister() {
    let factorIr: Record<string, unknown>;
    try {
      factorIr = JSON.parse(irText) as Record<string, unknown>;
    } catch {
      setError(t("expAction.invalidJson"));
      return;
    }
    const snapshot = snapshots.find((item) => item.snapshotId === snapshotId);
    if (!snapshot || !frozenBriefId) return;
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.preregisterExperiment({
        researchJobId: jobId,
        briefVersionId: frozenBriefId,
        decisionTime,
        randomSeed: seed,
        resourceBudget: {
          cpuSeconds: 3600,
          wallClockSeconds: 1800,
          memoryMb: 2048,
          maxObservations: 100000,
        },
        factorIr,
        snapshotId: snapshot.snapshotId,
        snapshotManifestHash: snapshot.manifestHash,
      });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  async function run() {
    if (!experimentId) return;
    setBusy(true);
    setError(null);
    try {
      // Refresh the etag on this client instance before the write command.
      await quantApiClient.getExperiment(experimentId);
      await quantApiClient.runExperiment(experimentId);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  if (experimentId && hasRun) return null;

  if (experimentId) {
    return (
      <section className="panel">
        <div className="form-actions">
          <button
            className="button button-primary"
            type="button"
            disabled={busy}
            onClick={run}
          >
            {busy ? t("expAction.busy") : t("expAction.run")}
          </button>
          {error ? <span className="form-footnote">{error}</span> : null}
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      {!open ? (
        <div className="form-actions">
          {frozenBriefId ? (
            <button
              className="button button-primary"
              type="button"
              onClick={openForm}
            >
              {t("expAction.preregister")}
            </button>
          ) : (
            <span className="form-footnote">
              {t("expAction.needFrozenBrief")}
            </span>
          )}
        </div>
      ) : (
        <div className="research-form">
          <div className="field-grid">
            <label className="field">
              <span>{t("expAction.snapshot")}</span>
              <select
                value={snapshotId}
                onChange={(event) => setSnapshotId(event.target.value)}
              >
                {snapshots.map((item) => (
                  <option key={item.snapshotId} value={item.snapshotId}>
                    {item.snapshotId}
                    {item.market ? ` · ${item.market}` : ""}
                    {item.frequency ? ` · ${item.frequency}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("expAction.decisionTime")}</span>
              <input
                type="datetime-local"
                value={isoToLocalInput(decisionTime)}
                onChange={(event) =>
                  setDecisionTime(new Date(event.target.value).toISOString())
                }
              />
              <span className="form-footnote">
                {t("expAction.decisionTimeHint")}
              </span>
            </label>
            <label className="field">
              <span>{t("expAction.seed")}</span>
              <input
                type="number"
                value={seed}
                onChange={(event) => setSeed(Number(event.target.value))}
              />
            </label>
            <label className="field field-wide">
              <span>{t("expAction.factorIr")}</span>
              <textarea
                value={irText}
                onChange={(event) => setIrText(event.target.value)}
                rows={18}
                className="mono"
              />
            </label>
          </div>
          {error ? (
            <div className="form-errors" role="alert">
              <span>{error}</span>
            </div>
          ) : null}
          <div className="form-actions">
            <button
              className="button button-primary"
              type="button"
              disabled={busy || !snapshotId}
              onClick={submitPreregister}
            >
              {busy ? t("expAction.busy") : t("expAction.submit")}
            </button>
            <button
              className="button button-secondary"
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              {t("expAction.cancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
