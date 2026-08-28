"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "../../components/i18n-provider";
import { PaperConsole, type PaperLedger } from "../../components/paper-console";
import { quantApiClient } from "../../lib/client";
import type {
  PaperAccount,
  PaperDriftReport,
  PaperRunStatus,
} from "../../lib/types";

const EMPTY_LEDGER: PaperLedger = {
  orders: [],
  fills: [],
  positions: [],
  equity: [],
};

export default function PaperPage() {
  const { t } = useI18n();
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ledger, setLedger] = useState<PaperLedger>(EMPTY_LEDGER);
  const [drift, setDrift] = useState<PaperDriftReport | null>(null);
  const [driftLoading, setDriftLoading] = useState(false);
  const [runStatus, setRunStatus] = useState<PaperRunStatus | null>(null);
  const [startingNode, setStartingNode] = useState(false);
  const [runStates, setRunStates] = useState<Record<string, PaperRunStatus>>({});
  const [error, setError] = useState<string | null>(null);

  const selected = accounts.find((account) => account.id === selectedId) ?? null;

  const loadRunStates = useCallback(async (items: PaperAccount[]) => {
    try {
      const results = await Promise.all(
        items.map(async (account) => {
          try {
            return await quantApiClient.paperRunStatus(account.id);
          } catch {
            return null;
          }
        }),
      );
      const map: Record<string, PaperRunStatus> = {};
      results.forEach((status) => {
        if (status) map[status.account_id] = status;
      });
      setRunStates(map);
    } catch {
      /* 忽略单次失败，保留旧值 */
    }
  }, []);

  const refreshAccounts = useCallback(async () => {
    try {
      const items = await quantApiClient.listPaperAccounts();
      setAccounts(items);
      const preferred = new URLSearchParams(window.location.search).get(
        "account",
      );
      const running = items.find((account) => account.id === preferred)
        ? null
        : items.find(
            (account) =>
              account.state === "ACTIVE" &&
              (runStates[account.id]?.node_running ?? false),
          );
      setSelectedId(
        (current) =>
          current ?? preferred ?? running?.id ?? items[0]?.id ?? null,
      );
      await loadRunStates(items);
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : t("paper.loadFailed"));
    }
  }, [t, loadRunStates, runStates]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshAccounts();
  }, [refreshAccounts]);

  useEffect(() => {
    if (!selectedId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLedger(EMPTY_LEDGER);
      setRunStatus(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const [orders, fills, positions, equity, status] = await Promise.all([
          quantApiClient.listPaperOrders(selectedId),
          quantApiClient.listPaperFills(selectedId),
          quantApiClient.listPaperPositions(selectedId),
          quantApiClient.listPaperEquity(selectedId),
          quantApiClient.paperRunStatus(selectedId),
        ]);
        if (cancelled) return;
        setLedger({ orders, fills, positions, equity });
        setRunStatus(status);
        setRunStates((current) => ({
          ...current,
          [selectedId]: status,
        }));
        setError(null);
      } catch (reason: unknown) {
        if (!cancelled) {
          setError(
            reason instanceof Error ? reason.message : t("paper.loadFailed"),
          );
        }
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId, t]);

  const onLifecycle = useCallback(
    async (action: "pause" | "resume" | "close") => {
      if (!selectedId) return;
      if (action === "close" && !window.confirm(t("paper.close.confirm"))) {
        return;
      }
      try {
        const updated = await (action === "pause"
          ? quantApiClient.pausePaperAccount(selectedId)
          : action === "resume"
            ? quantApiClient.resumePaperAccount(selectedId)
            : quantApiClient.closePaperAccount(selectedId));
        setAccounts((current) =>
          current.map((account) =>
            account.id === updated.id ? updated : account,
          ),
        );
        setError(null);
      } catch (reason: unknown) {
        setError(reason instanceof Error ? reason.message : t("paper.loadFailed"));
      }
    },
    [selectedId, t],
  );

  const onDrift = useCallback(async () => {
    if (!selectedId) return;
    setDriftLoading(true);
    try {
      setDrift(await quantApiClient.paperDrift(selectedId));
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : t("paper.loadFailed"));
    } finally {
      setDriftLoading(false);
    }
  }, [selectedId, t]);

  const onStartNode = useCallback(async () => {
    if (!selectedId || startingNode) return;
    setStartingNode(true);
    setError(null);
    try {
      await quantApiClient.startPaperNode(selectedId);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setStartingNode(false);
    }
  }, [selectedId, startingNode]);

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">PAPER</span>
          <h1>{t("paper.title")}</h1>
          <p className="lede">{t("paper.lede")}</p>
        </div>
      </div>

      {error ? (
        <div className="freshness-banner" role="alert">
          <strong>{t("paper.loadFailed")}</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <PaperConsole
        accounts={accounts}
        selectedId={selectedId}
        selected={selected}
        ledger={ledger}
        runStatus={runStatus}
        runStates={runStates}
        drift={drift}
        driftLoading={driftLoading}
        startingNode={startingNode}
        onSelectAccount={setSelectedId}
        onLifecycle={(action) => void onLifecycle(action)}
        onDrift={() => void onDrift()}
        onStartNode={() => void onStartNode()}
      />
    </div>
  );
}
