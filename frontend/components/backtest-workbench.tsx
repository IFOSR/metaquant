"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { quantApiClient } from "../lib/client";
import type { MessageKey } from "../lib/i18n";
import type {
  StrategyBacktestResult,
  StrategyDataStatus,
  StrategyDraft,
  StrategyFrequency,
} from "../lib/types";
import { EquitySparkline } from "./equity-sparkline";
import { useI18n } from "./i18n-provider";

const FREQUENCY_OPTIONS: Array<{ value: StrategyFrequency; labelKey: MessageKey }> = [
  { value: "1d", labelKey: "strategyChat.freq1d" },
  { value: "1w", labelKey: "strategyChat.freq1w" },
  { value: "5m", labelKey: "strategyChat.freq5m" },
  { value: "15m", labelKey: "strategyChat.freq15m" },
  { value: "30m", labelKey: "strategyChat.freq30m" },
  { value: "60m", labelKey: "strategyChat.freq60m" },
];

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function fmtTime(value: string): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function BacktestWorkbench() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const autoRunRef = useRef(false);
  const [drafts, setDrafts] = useState<StrategyDraft[]>([]);
  const [draft, setDraft] = useState<StrategyDraft | null>(null);
  const [dataStatus, setDataStatus] = useState<StrategyDataStatus | null>(null);
  const [btFrequency, setBtFrequency] = useState<StrategyFrequency>("1d");
  const [btStart, setBtStart] = useState("");
  const [btEnd, setBtEnd] = useState("");
  const [btEdited, setBtEdited] = useState(false);
  const [result, setResult] = useState<StrategyBacktestResult | null>(null);
  const [showFills, setShowFills] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState<string | null>(null);
  const [activeHistoryIndex, setActiveHistoryIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyPlan = useCallback((loaded: StrategyDraft) => {
    const plan = loaded.backtestPlan;
    if (plan === null) {
      setBtFrequency("1d");
      setBtStart("");
      setBtEnd("");
      return;
    }
    setBtFrequency(
      FREQUENCY_OPTIONS.some((option) => option.value === plan.execTimeframe)
        ? (plan.execTimeframe as StrategyFrequency)
        : "1d",
    );
    setBtStart(plan.start);
    setBtEnd(plan.end);
  }, []);

  const runBacktest = useCallback(async () => {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await quantApiClient.backtestStrategyDraft(draft.id, {
          frequency: btFrequency,
          startDate: btStart || undefined,
          endDate: btEnd || undefined,
        }),
      );
      // 回测已沉淀进 backtest_results 历史：重取研究以刷新历史列表。
      const refreshed = await quantApiClient.getStrategyDraft(draft.id);
      setDraft(refreshed);
      setDrafts((current) =>
        current.map((item) => (item.id === refreshed.id ? refreshed : item)),
      );
      // 高亮最新一次运行（追加在历史末尾）。
      setActiveHistoryIndex(refreshed.backtestResults.length - 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, [draft, busy, btFrequency, btStart, btEnd]);

  const openHistoryEntry = useCallback(
    async (entry: { backtestHash: string }, index: number) => {
      if (!draft || busy) return;
      setLoadingHistory(entry.backtestHash);
      setActiveHistoryIndex(index);
      setError(null);
      try {
        setResult(
          await quantApiClient.getStrategyBacktestResult(
            draft.id,
            entry.backtestHash,
          ),
        );
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        setLoadingHistory(null);
      }
    },
    [draft, busy],
  );

  useEffect(() => {
    let cancelled = false;
    quantApiClient
      .listStrategyDrafts("FROZEN")
      .then((items) => {
        if (!cancelled) setDrafts(items);
      })
      .catch(() => {
        if (!cancelled) setDrafts([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 从「回测」入口跳转：?draft=<id> 自动选中该策略并自动跑一次。
  useEffect(() => {
    const draftId = searchParams.get("draft");
    if (!draftId) return;
    let cancelled = false;
    autoRunRef.current = true;
    quantApiClient
      .getStrategyDraft(draftId)
      .then((loaded) => {
        if (cancelled) return;
        setDraft(loaded);
        applyPlan(loaded);
        // 该策略可能未冻结，不在默认列表里：补进列表让下拉框能反映选中项。
        setDrafts((current) =>
          current.some((item) => item.id === loaded.id)
            ? current
            : [loaded, ...current],
        );
      })
      .catch((caught) => {
        if (!cancelled) {
          autoRunRef.current = false;
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams, applyPlan]);

  useEffect(() => {
    if (draft === null || draft.instrumentIds.length === 0) return;
    let cancelled = false;
    quantApiClient
      .getStrategyDataStatus(
        draft.id,
        btEdited ? btFrequency : undefined,
        btStart || undefined,
        btEnd || undefined,
      )
      .then((status) => {
        if (!cancelled) setDataStatus(status);
      })
      .catch(() => {
        if (!cancelled) setDataStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [draft, btFrequency, btStart, btEnd, btEdited]);

  // 数据就绪后自动跑一次（仅当从「回测」入口跳转而来）。
  useEffect(() => {
    if (
      !autoRunRef.current ||
      !draft ||
      !draft.ready ||
      !draft.code ||
      dataStatus === null ||
      !dataStatus.ready ||
      busy
    ) {
      return;
    }
    autoRunRef.current = false;
    void runBacktest();
  }, [runBacktest, draft, dataStatus, busy]);

  const availableRange =
    dataStatus?.items
      .flatMap((item) => item.checks)
      .find((check) => check.available && check.required !== null)?.required ?? null;

  function selectDraft(id: string) {
    setDraft(null);
    setResult(null);
    setError(null);
    setBtEdited(false);
    setLoadingHistory(null);
    setActiveHistoryIndex(null);
    quantApiClient
      .getStrategyDraft(id)
      .then((loaded) => {
        setDraft(loaded);
        applyPlan(loaded);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : String(caught));
      });
  }

  const runDisabled =
    !draft || !draft.ready || busy || (dataStatus !== null && !dataStatus.ready);

  return (
    <div className="sc bt-console">
      <div className="sc-columns">
        {/* ── 配置轨（左） ─────────────────────────────────────────── */}
        <section className="bt-deck" aria-label="backtest controls">
          <div className="bt-deck-head">
            <span className="eyebrow">{t("backtest.eyebrow")}</span>
            <h2>{t("backtest.config")}</h2>
            <p className="bt-deck-hint">{t("backtest.configHint")}</p>
          </div>

          <div className="bt-step" data-step="01">
            <span className="bt-step-label">
              <em>01</em>
              {t("backtest.selectLabel")}
            </span>
            {drafts.length ? (
              <select
                className="sc-bt-select"
                aria-label={t("backtest.selectLabel")}
                value={draft?.id ?? ""}
                onChange={(event) => selectDraft(event.target.value)}
              >
                <option value="" disabled>
                  {t("backtest.selectPlaceholder")}
                </option>
                {drafts.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title || item.id} · {item.frequency}
                  </option>
                ))}
              </select>
            ) : (
              <p className="muted" style={{ margin: 0 }}>
                {t("backtest.empty")}
              </p>
            )}
          </div>

          {draft ? (
            <>
              <div className="bt-strategy">
                <div className="bt-strategy-top">
                  <h3>{draft.title || draft.id}</h3>
                  <a className="text-link" href={`/research/new?draft=${draft.id}`}>
                    {t("backtest.openChat")} →
                  </a>
                </div>
                <p className="mono">
                  {draft.instrumentIds.join(" · ")}
                  <span className="sc-meta-sep" aria-hidden="true">
                    |
                  </span>
                  {draft.market}
                </p>

                {draft.backtestPlan && (
                  <div className="bt-plan">
                    <div className="bt-plan-head">
                      <span className="eyebrow">{t("strategyChat.planTitle")}</span>
                      {btEdited && (
                        <button
                          type="button"
                          className="sc-bt-reset"
                          onClick={() => {
                            applyPlan(draft);
                            setBtEdited(false);
                          }}
                        >
                          {t("strategyChat.planReset")}
                        </button>
                      )}
                    </div>
                    <p className="bt-plan-rationale">
                      {t("strategyChat.planRationale")}
                      {draft.backtestPlan.rationale}
                    </p>
                  </div>
                )}
              </div>

              <div className="bt-step" data-step="02">
                <span className="bt-step-label">
                  <em>02</em>
                  {t("bt.params")}
                </span>

                <div className="bt-field">
                  <span>{t("strategyChat.btFrequency")}</span>
                  <select
                    className="sc-bt-select"
                    aria-label={t("strategyChat.btFrequency")}
                    value={btFrequency}
                    onChange={(event) => {
                      setBtFrequency(event.target.value as StrategyFrequency);
                      setBtEdited(true);
                    }}
                  >
                    {FREQUENCY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {t(option.labelKey)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="bt-field">
                  <span>{t("strategyChat.btRange")}</span>
                  <div className="sc-bt-dates">
                    <input
                      type="date"
                      aria-label={t("strategyChat.btStart")}
                      value={btStart}
                      min={availableRange?.firstEvent.slice(0, 10)}
                      max={availableRange?.lastEvent.slice(0, 10)}
                      onChange={(event) => {
                        setBtStart(event.target.value);
                        setBtEdited(true);
                      }}
                    />
                    <span className="sc-bt-tilde">~</span>
                    <input
                      type="date"
                      aria-label={t("strategyChat.btEnd")}
                      value={btEnd}
                      min={availableRange?.firstEvent.slice(0, 10)}
                      max={availableRange?.lastEvent.slice(0, 10)}
                      onChange={(event) => {
                        setBtEnd(event.target.value);
                        setBtEdited(true);
                      }}
                    />
                  </div>
                </div>
                <small className="bt-range-hint">{t("strategyChat.btRangeHint")}</small>

                {dataStatus && draft.instrumentIds.length > 0 && (
                  <div
                    className={`sc-data-status ${
                      dataStatus.ready ? "is-ready" : "is-missing"
                    }`}
                  >
                    {dataStatus.items.map((item) =>
                      item.checks.map((check) => (
                        <div
                          className="sc-data-row"
                          key={`${item.instrumentId}-${check.frequency}`}
                        >
                          <span
                            className={`sc-data-dot ${
                              check.available ? "is-ok" : "is-missing"
                            }`}
                            aria-hidden="true"
                          />
                          <span className="sc-data-id mono">
                            {item.instrumentId} · {check.frequency}
                          </span>
                          {check.available && check.required ? (
                            <span className="sc-data-info">
                              {t("strategyChat.dataReady")} ·{" "}
                              {t("strategyChat.dataRows", {
                                rows: check.required.rows,
                              })}{" "}
                              · {check.required.firstEvent.slice(0, 10)} ~{" "}
                              {check.required.lastEvent.slice(0, 10)}
                            </span>
                          ) : (
                            <span className="sc-data-info">
                              {t("strategyChat.dataMissingFreq", {
                                frequency: check.frequency,
                              })}
                            </span>
                          )}
                        </div>
                      )),
                    )}
                  </div>
                )}
              </div>

              <button
                type="button"
                className="button button-primary bt-run"
                onClick={runBacktest}
                disabled={runDisabled}
              >
                {busy ? t("bt.running") : t("bt.run")}
              </button>
              {error && <p className="sc-error">{error}</p>}

              {draft.backtestResults.length > 0 && (
                <div className="sc-bt-history">
                  <span className="eyebrow">
                    {t("strategyChat.backtestHistory")}
                  </span>
                  <ul className="sc-bt-history-list">
                    {draft.backtestResults.map((entry, index) => {
                      const isActive = activeHistoryIndex === index;
                      const isLoading = loadingHistory === entry.backtestHash;
                      return (
                        <li key={`${entry.backtestHash}-${index}`}>
                          <button
                            type="button"
                            className={`sc-bt-history-row ${
                              isActive ? "is-active" : ""
                            }`}
                            aria-pressed={isActive}
                            disabled={busy || loadingHistory !== null}
                            onClick={() => openHistoryEntry(entry, index)}
                          >
                            <span className="sc-bt-history-idx mono">
                              {isLoading ? "…" : index + 1}
                            </span>
                            <span className="sc-bt-history-range mono">
                              {entry.start} ~ {entry.end}
                            </span>
                            <span className="sc-bt-history-metric">
                              {entry.metrics ? pct(entry.metrics.totalReturn) : "—"}
                            </span>
                            <span className="sc-bt-history-hash mono muted">
                              {entry.backtestHash.slice(0, 8)}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          ) : null}
        </section>

        {/* ── 结果台（右） ─────────────────────────────────────────── */}
        <aside className="bt-results sc-artifact" aria-label="backtest result">
          <div className="sc-artifact-head">
            <span className="eyebrow">{t("bt.results")}</span>
            {loadingHistory ? (
              <span className="mono muted">{t("bt.running")}…</span>
            ) : result ? (
              <span className="mono muted">{result.backtestHash.slice(0, 8)}…</span>
            ) : null}
          </div>

          {!draft && (
            <div className="bt-results-empty">
              <span className="bt-results-mark" aria-hidden="true">
                → 指标面板
              </span>
              <p>{t("backtest.noSelection")}</p>
            </div>
          )}

          {draft && !result && busy && (
            <div className="bt-results-empty">
              <span className="bt-results-mark" aria-hidden="true">
                ⟳ 计算中
              </span>
              <p>{t("bt.running")}</p>
            </div>
          )}

          {draft && !result && !busy && (
            <div className="bt-results-empty">
              <span className="bt-results-mark" aria-hidden="true">
                → 指标面板
              </span>
              <p>{t("backtest.runToView")}</p>
            </div>
          )}

          {result && (
            <div className="sc-artifact-body">
              {result.error ? (
                <p className="sc-error">{result.error}</p>
              ) : (
                <>
                  <div className="sc-metrics">
                    <div>
                      <span>{t("bt.totalReturn")}</span>
                      <strong
                        className={
                          result.metrics.totalReturn >= 0 ? "is-pos" : "is-neg"
                        }
                      >
                        {pct(result.metrics.totalReturn)}
                      </strong>
                    </div>
                    <div>
                      <span>{t("bt.sharpe")}</span>
                      <strong>{result.metrics.sharpe?.toFixed(2) ?? "—"}</strong>
                    </div>
                    <div>
                      <span>{t("bt.maxDrawdown")}</span>
                      <strong className="is-neg">
                        {pct(result.metrics.maxDrawdown)}
                      </strong>
                    </div>
                    <div>
                      <span>{t("bt.tradeCount")}</span>
                      <strong>{result.metrics.tradeCount}</strong>
                    </div>
                  </div>

                  {result.venueSpec && (
                    <p className="sc-data-note">
                      {t("bt.costBasis")}: {result.venueSpec.costBasis}
                      {result.venueSpec.feeModel
                        ? ` · ${t("bt.feeModel")}: ${result.venueSpec.feeModel}`
                        : ""}
                      {result.venueSpec.fillModel
                        ? ` · ${t("bt.fillModel")}: ${result.venueSpec.fillModel}`
                        : ""}
                    </p>
                  )}

                  <div className="bt-equity">
                    <span className="eyebrow">{t("bt.equityCurve")}</span>
                    <EquitySparkline
                      points={result.equityCurve}
                      trades={result.trades}
                    />
                    <p className="sc-data-note" style={{ marginTop: 6 }}>
                      {t("bt.tradeTimelineHint")}
                    </p>
                  </div>

                  {result.positions.length > 0 && (
                    <div className="bt-section">
                      <span className="eyebrow">{t("bt.tradeTimeline")}</span>
                      <div className="bt-trade-list">
                        {result.positions.map((position, index) => (
                          <div className="bt-trade-card" key={index}>
                            <div className="bt-trade-left">
                              <span className="bt-trade-side mono">
                                {position.entry === "BUY" ? t("bt.buy") : t("bt.sell")}
                              </span>
                              <span className="bt-trade-px mono">
                                {position.avgPxOpen} · {fmtTime(position.openedAt)}
                              </span>
                            </div>
                            <div className="bt-trade-instr mono">
                              {position.instrumentId}
                            </div>
                            <div className="bt-trade-right">
                              <span className="bt-trade-px mono">
                                {position.avgPxClose != null
                                  ? `${position.avgPxClose} · ${fmtTime(position.closedAt ?? "")}`
                                  : t("bt.hold")}
                              </span>
                              <span
                                className={`bt-trade-pnl mono ${
                                  position.realizedPnl >= 0 ? "is-pos" : "is-neg"
                                }`}
                              >
                                {position.realizedPnl.toFixed(2)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {result.trades.length > 0 && (
                    <div className="bt-collapse">
                      <button
                        type="button"
                        className="bt-collapse-toggle"
                        aria-expanded={showFills}
                        onClick={() => setShowFills((value) => !value)}
                      >
                        <span className="eyebrow">{t("bt.trades")}</span>
                        <span className="bt-collapse-right">
                          <span className="bt-collapse-count mono">
                            {result.trades.length} 笔
                          </span>
                          <span className="bt-collapse-caret" aria-hidden="true">
                            {showFills ? "−" : "+"}
                          </span>
                        </span>
                      </button>

                      {showFills && (
                        <div className="task-list">
                          {result.trades.slice(0, 30).map((trade, index) => (
                            <div className="task-row" key={index}>
                              <span className="task-stage">{fmtTime(trade.time)}</span>
                              <strong className="mono">{trade.instrumentId}</strong>
                              <span className="muted">
                                {trade.side === "BUY" ? t("bt.buy") : t("bt.sell")} ·{" "}
                                {trade.quantity} @ {trade.price}
                              </span>
                              <span className="task-fee mono">
                                {trade.commission != null
                                  ? `${trade.commission.toFixed(2)} 费`
                                  : "—"}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
