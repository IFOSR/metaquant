"use client";

import { useEffect, useState } from "react";

import { useI18n } from "./i18n-provider";
import { quantApiClient } from "../lib/client";
import type { StrategyDataStatus, StrategyDraft } from "../lib/types";

type Props = {
  initialDraftId: string;
  onClose: () => void;
  onOpened: (accountId: string) => void;
};

export function OpenPaperDialog({
  initialDraftId,
  onClose,
  onOpened,
}: Props) {
  const { t } = useI18n();
  const [drafts, setDrafts] = useState<StrategyDraft[]>([]);
  const [selectedId, setSelectedId] = useState<string>(initialDraftId);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [initialCash, setInitialCash] = useState("1000000");
  const [dataStatus, setDataStatus] = useState<StrategyDataStatus | null>(null);
  const [provisioning, setProvisioning] = useState(false);
  const [opening, setOpening] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = drafts.find((draft) => draft.id === selectedId) ?? null;

  useEffect(() => {
    quantApiClient
      .listStrategyDrafts("FROZEN")
      .then((items) => {
        setDrafts(items);
        const preferredId = items.some(
          (draft) => draft.id === initialDraftId,
        )
          ? initialDraftId
          : items[0]?.id;
        if (preferredId) {
          setSelectedId(preferredId);
          const plan = items.find((draft) => draft.id === preferredId)
            ?.backtestPlan;
          setStart(plan?.start ?? "");
          setEnd(plan?.end ?? "");
        }
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : String(caught));
      });
  }, [initialDraftId]);

  const refreshStatus = (draftId: string, s: string, e: string) => {
    const draft = drafts.find((item) => item.id === draftId);
    if (!draft) return;
    quantApiClient
      .getStrategyDataStatus(draftId, undefined, s || undefined, e || undefined)
      .then((status) => setDataStatus(status))
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : String(caught)),
      );
  };

  useEffect(() => {
    if (!selected) return;
    refreshStatus(selected.id, start, end);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, start, end, drafts]);

  const dataReady = dataStatus?.ready ?? false;

  const onProvide = async () => {
    if (!selected) return;
    setProvisioning(true);
    setNote(null);
    setError(null);
    try {
      const result = await quantApiClient.provisionStrategyData(
        selected.id,
        undefined,
        start || undefined,
        end || undefined,
      );
      setNote(t("openPaper.provisionDone", { rows: result.rows }));
      refreshStatus(selected.id, start, end);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setProvisioning(false);
    }
  };

  const onOpen = async () => {
    if (!selected || !dataReady) return;
    setOpening(true);
    setError(null);
    try {
      const account = await quantApiClient.createPaperAccount(
        selected.id,
        Number(initialCash) || undefined,
      );
      onOpened(account.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setOpening(false);
    }
  };

  const plan = selected?.backtestPlan;
  const freq =
    plan?.execTimeframe ?? selected?.frequency ?? "";
  const trendFreq = plan?.trendTimeframe ?? null;
  const instruments = selected?.instrumentIds ?? [];

  return (
    <div
      className="opd-overlay"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="opd"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="opd-head">
          <h3>{t("openPaper.title")}</h3>
          <button type="button" className="opd-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="opd-body">
          <fieldset className="opd-field">
            <label>{t("openPaper.stepStrategy")}</label>
            <select
              className="opd-select"
              value={selectedId}
              onChange={(event) => {
                const next = event.target.value;
                setSelectedId(next);
                const draft = drafts.find((item) => item.id === next);
                setStart(draft?.backtestPlan?.start ?? "");
                setEnd(draft?.backtestPlan?.end ?? "");
                setDataStatus(null);
              }}
            >
              {drafts.map((draft) => (
                <option key={draft.id} value={draft.id}>
                  {draft.title || draft.id} · {draft.market}
                </option>
              ))}
            </select>
          </fieldset>

          {selected && (
            <>
              <fieldset className="opd-field">
                <label>{t("openPaper.stepWindow")}</label>
                <div className="opd-dates">
                  <input
                    type="date"
                    value={start}
                    onChange={(event) => setStart(event.target.value)}
                  />
                  <span>~</span>
                  <input
                    type="date"
                    value={end}
                    onChange={(event) => setEnd(event.target.value)}
                  />
                </div>
              </fieldset>

              <fieldset className="opd-field">
                <label>{t("openPaper.stepFrequency")}</label>
                <span className="opd-value mono">
                  {freq}
                  {trendFreq && trendFreq !== freq
                    ? ` · ${t("openPaper.trendFreq")} ${trendFreq}`
                    : ""}
                </span>
              </fieldset>

              <fieldset className="opd-field">
                <label>{t("openPaper.stepContract")}</label>
                <div className="opd-contracts">
                  {instruments.map((instrument) => (
                    <span key={instrument} className="opd-value mono">
                      {instrument}
                    </span>
                  ))}
                </div>
              </fieldset>

              <fieldset className="opd-field">
                <label>{t("openPaper.initialCash")}</label>
                <input
                  className="opd-input"
                  type="number"
                  min={1}
                  value={initialCash}
                  onChange={(event) => setInitialCash(event.target.value)}
                />
              </fieldset>

              <section className="opd-data">
                <div className="opd-data-head">
                  <span>{t("openPaper.dataStatus")}</span>
                  <span className={dataReady ? "ok" : "warn"}>
                    {dataReady
                      ? t("openPaper.dataReady")
                      : t("openPaper.dataMissing")}
                  </span>
                </div>
                {dataStatus?.items.map((item) =>
                  item.checks.map((check) => (
                    <div className="opd-data-row" key={`${item.instrumentId}-${check.frequency}`}>
                      <span className={"opd-dot " + (check.available ? "ok" : "warn")} />
                      <span className="mono">
                        {item.instrumentId} · {check.frequency}
                      </span>
                      {check.available
                        ? ` ${t("openPaper.dataOk")}`
                        : ` ${t("openPaper.dataMissingFreq")}`}
                    </div>
                  )),
                )}
                {!dataReady && (
                  <button
                    type="button"
                    className="opd-provision"
                    onClick={() => void onProvide()}
                    disabled={provisioning || !selected}
                  >
                    {provisioning
                      ? t("openPaper.provisioning")
                      : t("openPaper.provision")}
                  </button>
                )}
                {note && <p className="opd-note">{note}</p>}
              </section>
            </>
          )}

          {error && <p className="sc-error">{error}</p>}
        </div>

        <div className="opd-actions">
          <button type="button" className="opd-cancel" onClick={onClose}>
            {t("openPaper.cancel")}
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() => void onOpen()}
            disabled={!selected || !dataReady || opening}
          >
            {opening ? t("openPaper.opening") : t("openPaper.open")}
          </button>
        </div>
      </div>
    </div>
  );
}
