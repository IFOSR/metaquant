"use client";

import { useMemo, useState } from "react";

import type { MessageKey } from "../lib/i18n";
import type {
  PaperAccount,
  PaperDriftReport,
  PaperEquityRow,
  PaperFill,
  PaperOrder,
  PaperPosition,
  PaperRunStatus,
} from "../lib/types";
import { useI18n } from "./i18n-provider";

export interface PaperLedger {
  orders: PaperOrder[];
  fills: PaperFill[];
  positions: PaperPosition[];
  equity: PaperEquityRow[];
}

interface PaperConsoleProps {
  accounts: PaperAccount[];
  selectedId: string | null;
  selected: PaperAccount | null;
  ledger: PaperLedger;
  runStatus: PaperRunStatus | null;
  runStates: Record<string, PaperRunStatus>;
  drift: PaperDriftReport | null;
  driftLoading: boolean;
  startingNode: boolean;
  onSelectAccount: (id: string) => void;
  onLifecycle: (action: "pause" | "resume" | "close") => void;
  onDrift: () => void;
  onStartNode: () => void;
}

type NodeState = "RUNNING" | "WARMUP" | "STOPPED" | "ERROR" | "CLOSED";

function nodeStateOf(
  account: PaperAccount,
  runStatus: PaperRunStatus | null,
): NodeState {
  if (account.state === "CLOSED") return "CLOSED";
  if (runStatus?.node_running) return runStatus.warmed_up ? "RUNNING" : "WARMUP";
  if (runStatus?.status === "ERROR" || runStatus?.last_error) return "ERROR";
  return "STOPPED";
}

const nodeChipClass: Record<NodeState, string> = {
  RUNNING: "chip chip-ok",
  WARMUP: "chip chip-warn",
  STOPPED: "chip chip-muted",
  ERROR: "chip chip-err",
  CLOSED: "chip chip-muted",
};

const accountStateChip: Record<PaperAccount["state"], string> = {
  ACTIVE: "chip chip-ok",
  PAUSED: "chip chip-warn",
  CLOSED: "chip chip-muted",
};

function fmtTs(ts: string | null | undefined): string {
  if (!ts) return "—";
  return ts.slice(0, 19).replace("T", " ");
}

function fmtNum(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function PaperConsole(props: PaperConsoleProps) {
  const { t } = useI18n();
  const {
    accounts,
    selectedId,
    selected,
    ledger,
    runStatus,
    runStates,
    drift,
    driftLoading,
    startingNode,
    onSelectAccount,
    onLifecycle,
    onDrift,
    onStartNode,
  } = props;

  return (
    <div className="paper-grid">
      <aside>
        <div className="account-rail-head">
          <h2>{t("paper.accounts.title")}</h2>
          <span>{t("paper.accounts.count", { count: accounts.length })}</span>
        </div>
        {accounts.length === 0 ? (
          <p style={{ fontSize: 13, marginTop: 12, opacity: 0.7 }}>
            {t("paper.empty")}
          </p>
        ) : (
          <ul className="account-list">
            {accounts.map((account) => {
              const running = runStates[account.id]?.node_running ?? false;
              const hasError = Boolean(runStates[account.id]?.last_error);
              return (
                <li key={account.id}>
                  <button
                    type="button"
                    className={
                      "account-item" +
                      (account.id === selectedId ? " is-selected" : "")
                    }
                    onClick={() => onSelectAccount(account.id)}
                  >
                    <span className="account-item-top">
                      <span
                        className={
                          "dot " +
                          (account.state === "CLOSED"
                            ? "dot-muted"
                            : hasError
                              ? "dot-err"
                              : running
                                ? "dot-ok dot-pulse"
                                : "dot-warn")
                        }
                      />
                      <strong>{account.instrumentIds.join(", ")}</strong>
                      <span className={accountStateChip[account.state]}>
                        {t(`paper.state.${account.state}` as MessageKey)}
                      </span>
                    </span>
                    <span className="account-item-meta">
                      {account.market} · {account.frequency}
                    </span>
                    <span className="account-item-id">{account.id}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>

      <section>
        {!selected ? (
          <p style={{ opacity: 0.7 }}>{t("paper.selectAccount")}</p>
        ) : (
          <>
            <TraderPanel
              account={selected}
              runStatus={runStatus}
              ledger={ledger}
              startingNode={startingNode}
              onLifecycle={onLifecycle}
              onStartNode={onStartNode}
            />
            <SnapshotStrip equity={ledger.equity} />
            <LedgerTabs
              ledger={ledger}
              runStatus={runStatus}
              drift={drift}
              driftLoading={driftLoading}
              onDrift={onDrift}
            />
          </>
        )}
      </section>
    </div>
  );
}

/* ── Trader 控制台：生命周期状态机 + NT 式组件状态表 ── */

function TraderPanel({
  account,
  runStatus,
  ledger,
  startingNode,
  onLifecycle,
  onStartNode,
}: {
  account: PaperAccount;
  runStatus: PaperRunStatus | null;
  ledger: PaperLedger;
  startingNode: boolean;
  onLifecycle: (action: "pause" | "resume" | "close") => void;
  onStartNode: () => void;
}) {
  const { t } = useI18n();
  const nodeState = nodeStateOf(account, runStatus);
  const running = nodeState === "RUNNING" || nodeState === "WARMUP";

  const lifecycle: Array<{
    key: "READY" | "RUNNING" | "PAUSED" | "CLOSED";
    current: boolean;
    terminal?: boolean;
  }> = [
    { key: "READY", current: false },
    { key: "RUNNING", current: account.state === "ACTIVE" },
    { key: "PAUSED", current: account.state === "PAUSED" },
    { key: "CLOSED", current: account.state === "CLOSED", terminal: true },
  ];

  const components: Array<{
    name: string;
    state: MessageKey;
    tone: "ok" | "warn" | "err" | "muted";
    detail: string;
    isError?: boolean;
  }> = [
    {
      name: t("paper.comp.trader"),
      state: running
        ? "paper.compState.RUNNING"
        : nodeState === "ERROR"
          ? "paper.compState.ERROR"
          : "paper.compState.STOPPED",
      tone: running ? "ok" : nodeState === "ERROR" ? "err" : "muted",
      detail:
        nodeState === "WARMUP" ? t("paper.run.warmup") : account.frequency,
    },
    {
      name: t("paper.comp.clock"),
      state: running ? "paper.compState.LIVE" : "paper.compState.STOPPED",
      tone: running ? "ok" : "muted",
      detail: fmtTs(runStatus?.last_bar_at),
    },
    {
      name: t("paper.comp.data"),
      state: running ? "paper.compState.RUNNING" : "paper.compState.STOPPED",
      tone: running ? "ok" : "muted",
      detail: `${t("paper.run.bars")} ${runStatus?.bars_total ?? 0}`,
    },
    {
      name: t("paper.comp.exec"),
      state: running ? "paper.compState.RUNNING" : "paper.compState.STOPPED",
      tone: running ? "ok" : "muted",
      detail: `${t("paper.run.cycles")} ${runStatus?.cycles_total ?? 0}`,
    },
    {
      name: t("paper.comp.portfolio"),
      state:
        ledger.equity.length > 0
          ? "paper.compState.SYNCED"
          : "paper.compState.IDLE",
      tone: ledger.equity.length > 0 ? "ok" : "muted",
      detail: t("paper.snap.days", { days: ledger.equity.length }),
    },
    {
      name: t("paper.comp.risk"),
      state: runStatus?.last_error
        ? "paper.compState.ALERT"
        : "paper.compState.OK",
      tone: runStatus?.last_error ? "err" : "ok",
      detail: runStatus?.last_error ?? "—",
      isError: Boolean(runStatus?.last_error),
    },
  ];

  return (
    <div className="panel">
      <div className="trader-head">
        <div className="trader-head-title">
          <h2>{account.instrumentIds.join(", ")}</h2>
          <span className={nodeChipClass[nodeState]}>
            {t(`paper.node.state.${nodeState}` as MessageKey)}
          </span>
          <span className="mono">{account.id}</span>
        </div>
        <div className="trader-actions">
          {account.state === "PAUSED" ? (
            <button
              type="button"
              className="button button-primary button-small"
              onClick={() => onLifecycle("resume")}
            >
              {t("paper.resume")}
            </button>
          ) : null}
          {account.state === "ACTIVE" && !running ? (
            <button
              type="button"
              className="button button-primary button-small"
              onClick={onStartNode}
              disabled={startingNode || Boolean(runStatus?.last_error)}
            >
              {startingNode ? t("paper.run.starting") : t("paper.run.startNode")}
            </button>
          ) : null}
          {account.state === "ACTIVE" ? (
            <button
              type="button"
              className="button button-secondary button-small"
              onClick={() => onLifecycle("pause")}
            >
              {t("paper.pause")}
            </button>
          ) : null}
          {account.state !== "CLOSED" ? (
            <button
              type="button"
              className="button button-secondary button-small"
              style={{ color: "var(--danger)" }}
              onClick={() => onLifecycle("close")}
            >
              {t("paper.close")}
            </button>
          ) : null}
        </div>
      </div>

      <div className="lifecycle-track" aria-label={t("paper.lifecycle.title")}>
        {lifecycle.map((step) => (
          <div
            key={step.key}
            className={
              "lifecycle-step" +
              (step.current ? " is-current" : "") +
              (step.terminal ? " is-terminal" : "")
            }
          >
            <b>{step.key}</b>
            <span>{t(`paper.lifecycle.${step.key}` as MessageKey)}</span>
          </div>
        ))}
      </div>

      <div className="comp-table">
        <div className="comp-table-head">
          <strong>{t("paper.comp.title")}</strong>
          <span>{t("paper.comp.sub")}</span>
        </div>
        {components.map((component) => (
          <div key={component.name} className="comp-row">
            <span className="comp-name">{component.name}</span>
            <span className={`chip chip-${component.tone}`}>
              {t(component.state)}
            </span>
            <span
              className={"comp-detail" + (component.isError ? " is-error" : "")}
              title={component.detail}
            >
              {component.detail}
            </span>
          </div>
        ))}
      </div>

      {!running && account.state === "ACTIVE" ? (
        <p className="opd-note">{t("paper.run.offlineHint")}</p>
      ) : null}
    </div>
  );
}

/* ── 账户快照：净值 / 现金 / 保证金 / 回撤 + sparkline ── */

function SnapshotStrip({ equity }: { equity: PaperEquityRow[] }) {
  const { t } = useI18n();
  const latest = equity.length > 0 ? equity[equity.length - 1] : null;

  return (
    <div className="snap-strip">
      <div className="snap-cell">
        <label>{t("paper.snap.equity")}</label>
        <strong>{latest ? fmtNum(latest.equity) : "—"}</strong>
        {latest ? <small>{latest.tradeDate}</small> : null}
      </div>
      <div className="snap-cell">
        <label>{t("paper.snap.cash")}</label>
        <strong>{latest ? fmtNum(latest.cash) : "—"}</strong>
      </div>
      <div className="snap-cell">
        <label>{t("paper.snap.margin")}</label>
        <strong>{latest ? fmtNum(latest.marginUsed) : "—"}</strong>
      </div>
      <div className={"snap-cell" + (latest && latest.drawdown > 0 ? " is-bad" : "")}>
        <label>{t("paper.snap.drawdown")}</label>
        <strong>{latest ? fmtNum(latest.drawdown) : "—"}</strong>
      </div>
      <div className="snap-cell snap-spark">
        {equity.length >= 2 ? (
          <EquitySpark equity={equity} />
        ) : (
          <small style={{ color: "var(--muted)" }}>{t("paper.snap.empty")}</small>
        )}
      </div>
    </div>
  );
}

function EquitySpark({ equity }: { equity: PaperEquityRow[] }) {
  const values = equity.map((row) => row.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 220;
  const height = 52;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * (width - 4) + 2;
      const y = height - 6 - ((value - min) / span) * (height - 12);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="equity curve">
      <polyline
        points={points}
        fill="none"
        stroke="var(--amber-deep)"
        strokeWidth="1.6"
      />
      <line
        x1="0"
        x2={width}
        y1={height - 6}
        y2={height - 6}
        stroke="var(--line)"
        strokeDasharray="3 3"
      />
    </svg>
  );
}

/* ── Tab 化账本 ── */

type LedgerTab = "orders" | "fills" | "positions" | "events" | "drift";

function LedgerTabs({
  ledger,
  runStatus,
  drift,
  driftLoading,
  onDrift,
}: {
  ledger: PaperLedger;
  runStatus: PaperRunStatus | null;
  drift: PaperDriftReport | null;
  driftLoading: boolean;
  onDrift: () => void;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<LedgerTab>("orders");
  const events = useMemo(
    () => buildEvents(ledger, runStatus),
    [ledger, runStatus],
  );

  const tabs: Array<{ key: LedgerTab; label: string; count?: number }> = [
    { key: "orders", label: t("paper.tab.orders"), count: ledger.orders.length },
    { key: "fills", label: t("paper.tab.fills"), count: ledger.fills.length },
    {
      key: "positions",
      label: t("paper.tab.positions"),
      count: ledger.positions.length,
    },
    { key: "events", label: t("paper.tab.events"), count: events.length },
    { key: "drift", label: t("paper.tab.drift") },
  ];

  return (
    <div className="ledger">
      <div className="ledger-tabs" role="tablist">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={"ledger-tab" + (tab === item.key ? " is-active" : "")}
            onClick={() => setTab(item.key)}
          >
            {item.label}
            {item.count !== undefined ? (
              <span className="mono">{item.count}</span>
            ) : null}
          </button>
        ))}
      </div>
      <div className="ledger-body" role="tabpanel">
        {tab === "orders" ? <OrdersTable orders={ledger.orders} fills={ledger.fills} /> : null}
        {tab === "fills" ? <FillsTable fills={ledger.fills} /> : null}
        {tab === "positions" ? <PositionsTable positions={ledger.positions} /> : null}
        {tab === "events" ? <EventFeed events={events} /> : null}
        {tab === "drift" ? (
          <DriftPanel drift={drift} loading={driftLoading} onDrift={onDrift} />
        ) : null}
      </div>
    </div>
  );
}

/* ── 订单：状态 chip + 成交进度 + 生命周期展开 ── */

const orderStatusKeys: Record<string, MessageKey> = {
  FILLED: "paper.orderStatus.FILLED",
  PARTIALLY_FILLED: "paper.orderStatus.PARTIALLY_FILLED",
  ACCEPTED: "paper.orderStatus.ACCEPTED",
  SUBMITTED: "paper.orderStatus.SUBMITTED",
  NEW: "paper.orderStatus.NEW",
  REJECTED: "paper.orderStatus.REJECTED",
  CANCELED: "paper.orderStatus.CANCELED",
  CANCELLED: "paper.orderStatus.CANCELED",
  EXPIRED: "paper.orderStatus.EXPIRED",
};

function orderChipClass(status: string): string {
  if (status === "FILLED") return "chip chip-ok";
  if (status === "REJECTED" || status === "EXPIRED") return "chip chip-err";
  if (status === "CANCELED" || status === "CANCELLED") return "chip chip-muted";
  return "chip chip-warn";
}

function OrdersTable({
  orders,
  fills,
}: {
  orders: PaperOrder[];
  fills: PaperFill[];
}) {
  const { t } = useI18n();
  const [openId, setOpenId] = useState<string | null>(null);

  if (orders.length === 0) {
    return <p style={{ fontSize: 13, opacity: 0.6 }}>{t("state.empty")}</p>;
  }

  return (
    <table className="ledger-table">
      <thead>
        <tr>
          <th>{t("paper.col.time")}</th>
          <th>{t("paper.col.instrument")}</th>
          <th>{t("paper.col.side")}</th>
          <th className="num">{t("paper.col.qty")}</th>
          <th className="num">{t("paper.col.filled")}</th>
          <th className="num">{t("paper.col.avgPx")}</th>
          <th>{t("paper.col.status")}</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order) => {
          const statusKey = orderStatusKeys[order.status];
          const fillPct =
            order.quantity > 0
              ? Math.min(100, (order.filledQty / order.quantity) * 100)
              : 0;
          const open = openId === order.id;
          return [
            <tr
              key={order.id}
              className={"is-expandable" + (open ? " is-open" : "")}
              onClick={() => setOpenId(open ? null : order.id)}
            >
              <td className="mono">{fmtTs(order.createdAt)}</td>
              <td>{order.instrumentId}</td>
              <td>
                {t(
                  order.side === "BUY" ? "paper.order.BUY" : "paper.order.SELL",
                )}
              </td>
              <td className="num">{order.quantity}</td>
              <td className="num">
                {order.filledQty}
                <span className="fill-meter">
                  <span style={{ width: `${fillPct}%` }} />
                </span>
              </td>
              <td className="num">{order.avgPx ?? "—"}</td>
              <td>
                <span className={orderChipClass(order.status)}>
                  {statusKey ? t(statusKey) : order.status}
                </span>
              </td>
            </tr>,
            open ? (
              <tr key={`${order.id}-detail`} className="order-expand">
                <td colSpan={7}>
                  <OrderLifecycle order={order} fills={fills} />
                </td>
              </tr>
            ) : null,
          ];
        })}
      </tbody>
    </table>
  );
}

function OrderLifecycle({
  order,
  fills,
}: {
  order: PaperOrder;
  fills: PaperFill[];
}) {
  const { t } = useI18n();
  const orderFills = fills.filter((fill) => fill.orderId === order.id);
  const firstFill = orderFills[0]?.tradeTs ?? null;
  const lastFill = orderFills[orderFills.length - 1]?.tradeTs ?? null;
  const rejected = order.status === "REJECTED";
  const canceled =
    order.status === "CANCELED" || order.status === "CANCELLED";

  const steps: Array<{
    key: MessageKey;
    ts: string | null;
    done: boolean;
    fail?: boolean;
  }> = [
    { key: "paper.olc.INITIALIZED", ts: order.createdAt, done: true },
    { key: "paper.olc.SUBMITTED", ts: order.createdAt, done: true },
    {
      key: "paper.olc.ACCEPTED",
      ts: firstFill ?? order.orderClock ?? order.createdAt,
      done:
        order.status !== "NEW" &&
        order.status !== "SUBMITTED" &&
        !rejected,
    },
  ];
  if (rejected) {
    steps.push({ key: "paper.olc.REJECTED", ts: null, done: true, fail: true });
  } else if (canceled) {
    steps.push({ key: "paper.olc.CANCELED", ts: null, done: true, fail: true });
  } else {
    steps.push({
      key: "paper.olc.FILLED",
      ts: lastFill,
      done: order.status === "FILLED",
    });
  }

  return (
    <div>
      <div className="olc-track" aria-label={t("paper.olc.title")}>
        {steps.map((step) => (
          <span
            key={step.key}
            className={
              "olc-step" +
              (step.fail ? " is-fail" : step.done ? " is-done" : " is-pending")
            }
          >
            <b>{t(step.key)}</b>
            <span>{step.done && step.ts ? fmtTs(step.ts) : ""}</span>
          </span>
        ))}
      </div>
      {order.rejectReason ? (
        <p className="olc-reject">{order.rejectReason}</p>
      ) : null}
      <p className="olc-id">{order.id}</p>
    </div>
  );
}

/* ── 成交 / 持仓 ── */

function FillsTable({ fills }: { fills: PaperFill[] }) {
  const { t } = useI18n();
  if (fills.length === 0) {
    return <p style={{ fontSize: 13, opacity: 0.6 }}>{t("state.empty")}</p>;
  }
  return (
    <table className="ledger-table">
      <thead>
        <tr>
          <th>{t("paper.col.time")}</th>
          <th className="num">{t("paper.col.qty")}</th>
          <th className="num">{t("paper.col.price")}</th>
          <th className="num">{t("paper.col.fee")}</th>
          <th className="num">{t("paper.col.notional")}</th>
        </tr>
      </thead>
      <tbody>
        {fills.map((fill) => (
          <tr key={fill.id}>
            <td className="mono">{fmtTs(fill.tradeTs)}</td>
            <td className="num">{fill.quantity}</td>
            <td className="num">{fmtNum(fill.price)}</td>
            <td className="num">{fmtNum(fill.fee)}</td>
            <td className="num">{fmtNum(fill.notional)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PositionsTable({ positions }: { positions: PaperPosition[] }) {
  const { t } = useI18n();
  if (positions.length === 0) {
    return <p style={{ fontSize: 13, opacity: 0.6 }}>{t("state.empty")}</p>;
  }
  return (
    <table className="ledger-table">
      <thead>
        <tr>
          <th>{t("paper.col.instrument")}</th>
          <th className="num">{t("paper.col.qty")}</th>
          <th className="num">{t("paper.col.avgPx")}</th>
          <th>{t("paper.col.updated")}</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <tr key={position.instrumentId}>
            <td>{position.instrumentId}</td>
            <td className="num">{position.quantity}</td>
            <td className="num">{position.avgPx ?? "—"}</td>
            <td className="mono">{fmtTs(position.updatedAt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── 事件流：由账本推导的 NT 日志视角 ── */

interface NodeEvent {
  ts: string;
  tag: string;
  level: "ok" | "info" | "err";
  message: string;
}

function buildEvents(
  ledger: PaperLedger,
  runStatus: PaperRunStatus | null,
): NodeEvent[] {
  const events: NodeEvent[] = [];
  for (const order of ledger.orders) {
    events.push({
      ts: order.createdAt,
      tag: "ORDER",
      level: "info",
      message: `SUBMITTED ${order.instrumentId} ${order.side} ×${order.quantity}`,
    });
    if (order.status === "REJECTED") {
      events.push({
        ts: order.createdAt,
        tag: "RISK",
        level: "err",
        message: `REJECTED ${order.instrumentId} ${order.rejectReason ?? ""}`.trim(),
      });
    }
  }
  for (const fill of ledger.fills) {
    events.push({
      ts: fill.tradeTs,
      tag: "FILL",
      level: "ok",
      message: `×${fill.quantity} @ ${fmtNum(fill.price)} fee ${fmtNum(fill.fee)}`,
    });
  }
  for (const row of ledger.equity) {
    events.push({
      ts: `${row.tradeDate} 15:00:00`,
      tag: "EQUITY",
      level: "info",
      message: `close equity ${fmtNum(row.equity)} dd ${fmtNum(row.drawdown)}`,
    });
  }
  if (runStatus?.last_error) {
    events.push({
      ts: runStatus.updated_at ?? "",
      tag: "ERROR",
      level: "err",
      message: runStatus.last_error,
    });
  }
  return events.sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 60);
}

function EventFeed({ events }: { events: NodeEvent[] }) {
  const { t } = useI18n();
  return (
    <div>
      <p className="ledger-note">{t("paper.events.note")}</p>
      {events.length === 0 ? (
        <p style={{ fontSize: 13, opacity: 0.6 }}>{t("paper.events.empty")}</p>
      ) : (
        <div className="event-feed">
          {events.map((event, index) => (
            <div key={index} className={`event-line evt-${event.level}`}>
              <span className="evt-ts">{event.ts || "—"}</span>
              <span className="evt-tag">{event.tag}</span>
              <span className="evt-msg">{event.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 对拍回测 ── */

function DriftPanel({
  drift,
  loading,
  onDrift,
}: {
  drift: PaperDriftReport | null;
  loading: boolean;
  onDrift: () => void;
}) {
  const { t } = useI18n();
  return (
    <div>
      <p className="ledger-note">{t("paper.drift.hint")}</p>
      <button
        type="button"
        className="button button-secondary button-small"
        onClick={onDrift}
        disabled={loading}
      >
        {loading ? t("paper.drift.running") : t("paper.drift.run")}
      </button>
      {drift ? (
        <div style={{ marginTop: 16 }}>
          <div className="drift-metrics">
            <div>
              <label>{t("paper.drift.maxDiff")}</label>
              <strong>{fmtNum(drift.maxAbsDiff)}</strong>
            </div>
            <div>
              <label>{t("paper.drift.commonDays")}</label>
              <strong>{drift.commonDays}</strong>
              <small style={{ color: "var(--muted)", display: "block", marginTop: 3 }}>
                {t("paper.drift.paperDays")} {drift.paperDays} ·{" "}
                {t("paper.drift.backtestDays")} {drift.backtestDays}
              </small>
            </div>
            <div>
              <label>{t("paper.drift.costBasis")}</label>
              <strong>{drift.costBasis ?? "—"}</strong>
            </div>
          </div>
          <table className="ledger-table">
            <thead>
              <tr>
                <th>{t("paper.col.date")}</th>
                <th className="num">{t("paper.col.backtest")}</th>
                <th className="num">{t("paper.col.paper")}</th>
                <th className="num">{t("paper.col.diff")}</th>
              </tr>
            </thead>
            <tbody>
              {drift.points.map((point) => (
                <tr key={point.date}>
                  <td className="mono">{point.date}</td>
                  <td className="num">{fmtNum(point.backtestEquity)}</td>
                  <td className="num">{fmtNum(point.paperEquity)}</td>
                  <td
                    className={
                      "num " + (point.diff !== 0 ? "diff-pos" : "diff-zero")
                    }
                  >
                    {fmtNum(point.diff)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
