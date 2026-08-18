"use client";

import { useEffect, useState } from "react";

import { quantApiClient } from "../lib/client";
import type {
  AlphaPoolFactor,
  BacktestResult,
  MarketDataCoverageEntry,
} from "../lib/types";
import { useI18n } from "./i18n-provider";

interface BacktestLabProps {
  factors: AlphaPoolFactor[];
}

function shortHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
}

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function money(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function BacktestLab({ factors }: BacktestLabProps) {
  const { t } = useI18n();
  const [selectedHash, setSelectedHash] = useState<string | null>(
    factors[0]?.factorIrHash ?? null,
  );
  const [selectedInstruments, setSelectedInstruments] = useState<string[]>(
    factors[0]?.instruments ?? [],
  );
  const [startDate, setStartDate] = useState(factors[0]?.dataStart ?? "");
  const [endDate, setEndDate] = useState(factors[0]?.dataEnd ?? "");
  const [lotSize, setLotSize] = useState(1);
  const [initialCash, setInitialCash] = useState(100_000_000);
  const [dataSource, setDataSource] = useState<"snapshot" | "realtime">("snapshot");
  const [frequency, setFrequency] = useState<"1d" | "5m">("1d");
  const [coverage, setCoverage] = useState<MarketDataCoverageEntry[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const selected = factors.find((factor) => factor.factorIrHash === selectedHash) ?? null;

  useEffect(() => {
    if (dataSource !== "realtime" || !selected) {
      return;
    }
    let cancelled = false;
    quantApiClient
      .getMarketDataCoverage(selected.instruments)
      .then((entries) => {
        if (!cancelled) setCoverage(entries);
      })
      .catch(() => {
        if (!cancelled) setCoverage([]);
      });
    return () => {
      cancelled = true;
    };
  }, [dataSource, selected]);

  const fieldPrefix = frequency === "1d" ? "market.eod" : "market.minute";
  const realtimeEntries = (coverage ?? []).filter(
    (entry) => entry.fieldPrefix === fieldPrefix,
  );
  const realtimeStart = realtimeEntries.length
    ? realtimeEntries.map((entry) => entry.firstEvent.slice(0, 10)).sort()[0]
    : null;
  const realtimeEnd = realtimeEntries.length
    ? realtimeEntries.map((entry) => entry.lastEvent.slice(0, 10)).sort().at(-1)
    : null;
  const rangeStart = dataSource === "realtime" ? realtimeStart : selected?.dataStart;
  const rangeEnd = dataSource === "realtime" ? realtimeEnd : selected?.dataEnd;
  const artifactClasses = [
    ...new Set(realtimeEntries.map((entry) => entry.artifactClass)),
  ];

  function pickFactor(factor: AlphaPoolFactor) {
    setSelectedHash(factor.factorIrHash);
    setSelectedInstruments(factor.instruments);
    setStartDate(factor.dataStart ?? "");
    setEndDate(factor.dataEnd ?? "");
    setResult(null);
    setError(null);
  }

  function toggleInstrument(instrument: string) {
    setSelectedInstruments((current) =>
      current.includes(instrument)
        ? current.filter((item) => item !== instrument)
        : [...current, instrument],
    );
  }

  async function run() {
    if (!selected || selectedInstruments.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const outcome = await quantApiClient.runBacktest({
        factorIrHash: selected.factorIrHash,
        instrumentIds: selectedInstruments,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        frequency,
        dataSource,
        lotSize,
        initialCash,
      });
      setResult(outcome);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (factors.length === 0) {
    return (
      <section className="panel">
        <span className="eyebrow">{t("bt.eyebrow")}</span>
        <h2>{t("bt.title")}</h2>
        <p className="muted">{t("strategy.emptyFactors")}</p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="backtest-lab-title">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{t("bt.eyebrow")}</span>
          <h2 id="backtest-lab-title">{t("bt.title")}</h2>
        </div>
      </div>

      <div className="experiment-section">
        <div className="section-label">
          <span className="eyebrow">{t("bt.selectFactor")}</span>
        </div>
        <div className="task-list">
          {factors.map((factor) => (
            <label className="task-row" key={factor.factorIrHash}>
              <input
                type="radio"
                name="backtest-factor"
                checked={factor.factorIrHash === selectedHash}
                onChange={() => pickFactor(factor)}
              />
              <strong className="mono">
                {factor.factorId ?? shortHash(factor.factorIrHash)}
              </strong>
              <span className="muted">{factor.direction}</span>
              <span className="muted">
                {t("strategy.oosIc", { value: factor.oosIc?.toFixed(4) ?? "—" })}
              </span>
              <span className="muted">{factor.lifecycleState}</span>
            </label>
          ))}
        </div>
      </div>

      {selected ? (
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("bt.instruments")}</span>
          </div>
          <div className="task-list">
            {selected.instruments.map((instrument) => (
              <label className="task-row" key={instrument}>
                <input
                  type="checkbox"
                  checked={selectedInstruments.includes(instrument)}
                  onChange={() => toggleInstrument(instrument)}
                />
                <strong className="mono">{instrument}</strong>
              </label>
            ))}
          </div>

          <div className="section-label">
            <span className="eyebrow">{t("bt.params")}</span>
          </div>
          <div className="field-grid">
            <label className="field">
              <span>{t("bt.dataSource")}</span>
              <select
                value={dataSource}
                onChange={(event) => {
                  setDataSource(event.target.value as "snapshot" | "realtime");
                  setCoverage(null);
                  setResult(null);
                }}
              >
                <option value="snapshot">{t("bt.sourceSnapshot")}</option>
                <option value="realtime">{t("bt.sourceRealtime")}</option>
              </select>
            </label>
            <label className="field">
              <span>{t("bt.frequency")}</span>
              <select
                value={frequency}
                onChange={(event) => setFrequency(event.target.value as "1d" | "5m")}
              >
                <option value="1d">{t("bt.freqDaily")}</option>
                <option value="5m">{t("bt.freq5m")}</option>
              </select>
            </label>
            <label className="field">
              <span>{t("bt.startDate")}</span>
              <input
                type="date"
                value={startDate}
                min={rangeStart ?? undefined}
                max={rangeEnd ?? undefined}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{t("bt.endDate")}</span>
              <input
                type="date"
                value={endDate}
                min={rangeStart ?? undefined}
                max={rangeEnd ?? undefined}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
            <label className="field">
              <span>{t("bt.lotSize")}</span>
              <input
                type="number"
                min={1}
                step={1}
                value={lotSize}
                onChange={(event) =>
                  setLotSize(Math.max(1, Number(event.target.value) || 1))
                }
              />
            </label>
            <label className="field">
              <span>{t("bt.initialCash")}</span>
              <input
                type="number"
                min={1}
                step={100000}
                value={initialCash}
                onChange={(event) =>
                  setInitialCash(Math.max(1, Number(event.target.value) || 1))
                }
              />
            </label>
          </div>
          {dataSource === "realtime" ? (
            coverage === null ? (
              <p className="muted">{t("bt.coverageLoading")}</p>
            ) : realtimeEntries.length === 0 ? (
              <p className="muted">{t("bt.coverageEmpty")}</p>
            ) : (
              <p className="muted">
                {t("bt.dataRange", {
                  start: rangeStart ?? "?",
                  end: rangeEnd ?? "?",
                })}
                {artifactClasses.map((cls) => (
                  <span key={cls} className={`artifact-badge artifact-${cls.toLowerCase()}`}>
                    {cls}
                  </span>
                ))}
              </p>
            )
          ) : selected.dataStart && selected.dataEnd ? (
            <p className="muted">
              {t("bt.dataRange", {
                start: selected.dataStart,
                end: selected.dataEnd,
              })}
            </p>
          ) : null}

          <div className="form-actions">
            <button
              className="button button-primary"
              type="button"
              disabled={busy || selectedInstruments.length === 0}
              onClick={run}
            >
              {busy ? t("bt.running") : t("bt.run")}
            </button>
          </div>
          {error ? (
            <div className="freshness-banner" role="alert">
              <strong>{t("bt.error")}</strong>
              <span>{error}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <div className="experiment-section">
          <div className="section-label">
            <span className="eyebrow">{t("bt.results")}</span>
          </div>
          <div className="validation-metrics">
            <div>
              <span>{t("bt.totalReturn")}</span>
              <strong>{pct(result.metrics.totalReturn)}</strong>
            </div>
            <div>
              <span>{t("bt.sharpe")}</span>
              <strong>{result.metrics.sharpe?.toFixed(2) ?? "—"}</strong>
            </div>
            <div>
              <span>{t("bt.maxDrawdown")}</span>
              <strong>{pct(result.metrics.maxDrawdown)}</strong>
            </div>
            <div>
              <span>{t("bt.tradeCount")}</span>
              <strong>{result.metrics.tradeCount}</strong>
            </div>
          </div>
          <p className="muted">
            {t("bt.grossNote")} · {result.frequency}
            {result.dataSource === "realtime" && result.artifactClass
              ? ` · ${t("bt.realtimeData")} · ${result.artifactClass}`
              : ` · ${t("bt.snapshotData")}`}
          </p>

          {result.positions.length ? (
            <>
              <div className="section-label">
                <span className="eyebrow">{t("bt.positions")}</span>
              </div>
              <table className="trade-table">
                <thead>
                  <tr>
                    <th>{t("bt.colInstrument")}</th>
                    <th>{t("bt.colDirection")}</th>
                    <th>{t("bt.colQty")}</th>
                    <th>{t("bt.colOpen")}</th>
                    <th>{t("bt.colClose")}</th>
                    <th>{t("bt.colPnl")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.positions.map((position, index) => (
                    <tr key={`${position.instrumentId}-${index}`}>
                      <td className="mono">{position.instrumentId}</td>
                      <td>
                        {position.entry === "BUY" ? t("bt.long") : t("bt.short")}
                      </td>
                      <td>{position.peakQty}</td>
                      <td className="mono">{position.avgPxOpen}</td>
                      <td className="mono">{position.avgPxClose ?? "—"}</td>
                      <td
                        className={
                          position.realizedPnl >= 0 ? "pnl-positive" : "pnl-negative"
                        }
                      >
                        {money(position.realizedPnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}

          {result.trades.length ? (
            <>
              <div className="section-label">
                <span className="eyebrow">{t("bt.trades")}</span>
              </div>
              <table className="trade-table">
                <thead>
                  <tr>
                    <th>{t("bt.colTime")}</th>
                    <th>{t("bt.colInstrument")}</th>
                    <th>{t("bt.colSide")}</th>
                    <th>{t("bt.colQty")}</th>
                    <th>{t("bt.colPrice")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((trade, index) => (
                    <tr key={`${trade.time}-${index}`}>
                      <td className="mono">{trade.time.slice(0, 16).replace("T", " ")}</td>
                      <td className="mono">{trade.instrumentId}</td>
                      <td>{trade.side === "BUY" ? t("bt.buy") : t("bt.sell")}</td>
                      <td>{trade.quantity}</td>
                      <td className="mono">{trade.price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}

          <span className="mono muted">
            {t("bt.hash")}: {shortHash(result.backtestHash)}
          </span>
        </div>
      ) : null}
    </section>
  );
}
