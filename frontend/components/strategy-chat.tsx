"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { quantApiClient } from "../lib/client";
import { MARKET_LABEL_KEYS } from "../lib/domain";
import type { MessageKey } from "../lib/i18n";
import type {
  MarketId,
  ResearchStage,
  StrategyAttachment,
  StrategyBacktestResult,
  StrategyCodeTestResult,
  StrategyDataStatus,
  StrategyDraft,
  StrategyFrequency,
  StrategyMessage,
} from "../lib/types";
import { EquitySparkline } from "./equity-sparkline";
import { useI18n } from "./i18n-provider";
import { OpenPaperDialog } from "./open-paper-dialog";

const FREQUENCY_OPTIONS: Array<{
  value: StrategyFrequency;
  labelKey: MessageKey;
}> = [
  { value: "1d", labelKey: "strategyChat.freq1d" },
  { value: "1w", labelKey: "strategyChat.freq1w" },
  { value: "5m", labelKey: "strategyChat.freq5m" },
  { value: "15m", labelKey: "strategyChat.freq15m" },
  { value: "30m", labelKey: "strategyChat.freq30m" },
  { value: "60m", labelKey: "strategyChat.freq60m" },
];

const STATUS_KEYS = {
  DRAFT: "strategyChat.statusDraft",
  READY: "strategyChat.statusReady",
  FROZEN: "strategyChat.statusFrozen",
} as const;

const STAGE_ORDER: ResearchStage[] = [
  "CREATING",
  "READY",
  "CODE_TESTED",
  "BACKTESTED",
  "PAPER_LINKED",
];

const STAGE_LABEL_KEYS: Record<ResearchStage, MessageKey> = {
  CREATING: "research.stage.creating",
  READY: "research.stage.ready",
  CODE_TESTED: "research.stage.codeTested",
  BACKTESTED: "research.stage.backtested",
  PAPER_LINKED: "research.stage.paperLinked",
};

function StageRail({ stage }: { stage: ResearchStage }) {
  const { t } = useI18n();
  const activeIndex = STAGE_ORDER.indexOf(stage);
  return (
    <ol className="sc-stage-rail" aria-label="研究阶段">
      {STAGE_ORDER.map((item, index) => (
        <li
          key={item}
          className={`sc-stage ${
            index === activeIndex ? "is-active" : ""
          } ${index < activeIndex ? "is-done" : ""}`}
        >
          <span className="sc-stage-dot" aria-hidden="true">
            {index + 1}
          </span>
          <span className="sc-stage-label">{t(STAGE_LABEL_KEYS[item])}</span>
        </li>
      ))}
    </ol>
  );
}

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function fmtTime(value: string): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function StrategyChat() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [market, setMarket] = useState<MarketId>("CN_A");
  const [draft, setDraft] = useState<StrategyDraft | null>(null);
  const [messages, setMessages] = useState<StrategyMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<StrategyAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<StrategyBacktestResult | null>(null);
  const [codeTest, setCodeTest] = useState<StrategyCodeTestResult | null>(null);
  const [showCode, setShowCode] = useState(false);
  const [dataStatus, setDataStatus] = useState<StrategyDataStatus | null>(null);
  const [provisioning, setProvisioning] = useState(false);
  const [provisionNote, setProvisionNote] = useState<string | null>(null);
  const [btFrequency, setBtFrequency] = useState<StrategyFrequency>("1d");
  const [btStart, setBtStart] = useState("");
  const [btEnd, setBtEnd] = useState("");
  const [btEdited, setBtEdited] = useState(false);
  const [paperDialogOpen, setPaperDialogOpen] = useState(false);

  const hasConversation = messages.length > 0;
  const frozen = draft?.state === "FROZEN";
  const availableRange =
    dataStatus?.items
      .flatMap((item) => item.checks)
      .find((check) => check.available && check.required !== null)?.required ??
    null;

  useEffect(() => {
    if (draft === null || draft.instrumentIds.length === 0) {
      return;
    }
    let cancelled = false;
    quantApiClient
      .getStrategyDataStatus(
        draft.id,
        // 用户手动改过周期才覆盖；否则用方案的全周期（多周期策略查全部）
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

  useEffect(() => {
    const draftId = searchParams.get("draft");
    if (!draftId) return;
    let cancelled = false;
    quantApiClient
      .getStrategyDraft(draftId)
      .then((loaded) => {
        if (cancelled) return;
        setDraft(loaded);
        setMessages(loaded.messages ?? []);
        setCodeTest(loaded.codeTestResult ?? null);
        applyPlan(loaded);
        setBtEdited(false);
        setError(null);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  function assistantReply(next: StrategyDraft): StrategyMessage {
    return {
      role: "assistant",
      content: next.question
        ? `${next.explanation}\n\n${next.question}`
        : next.explanation,
    };
  }

  function applyPlan(draft: StrategyDraft) {
    const plan = draft.backtestPlan;
    if (plan === null) {
      setBtFrequency(
        FREQUENCY_OPTIONS.some((option) => option.value === draft.frequency)
          ? (draft.frequency as StrategyFrequency)
          : "1d",
      );
      return;
    }
    setBtFrequency(
      FREQUENCY_OPTIONS.some((option) => option.value === plan.execTimeframe)
        ? (plan.execTimeframe as StrategyFrequency)
        : "1d",
    );
    setBtStart(plan.start);
    setBtEnd(plan.end);
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const pending = attachments;
    setBusy(true);
    setError(null);
    setMessages((previous) => [...previous, { role: "user", content: trimmed }]);
    setAttachments([]);
    try {
      if (draft === null) {
        const created = await quantApiClient.createStrategyDraft(
          market,
          trimmed,
          pending,
        );
        setDraft(created);
        if (!btEdited) applyPlan(created);
        setMessages((previous) => [...previous, assistantReply(created)]);
      } else {
        const updated = await quantApiClient.postStrategyMessage(
          draft.id,
          trimmed,
          pending,
        );
        setDraft(updated);
        if (!btEdited) applyPlan(updated);
        setBacktest(null);
        setCodeTest(null);
        setMessages((previous) => [...previous, assistantReply(updated)]);
      }
      setInput("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function send() {
    void sendMessage(input);
  }

  async function sendDataFix() {
    if (!dataStatus || dataStatus.ready) return;
    const missing: string[] = [];
    for (const item of dataStatus.items) {
      for (const check of item.checks) {
        if (!check.available) {
          missing.push(`${item.instrumentId} 的 ${check.frequency}`);
        }
      }
    }
    const anyDailyAvailable = dataStatus.items.some(
      (item) => item.daily !== null,
    );
    const hint = anyDailyAvailable
      ? `标的 ${missing.join("、")} 暂无行情数据，请改用日线（1d）频率重新生成策略。`
      : `标的 ${missing.join("、")} 暂无行情数据，请换成有数据的标的或周期。`;
    await sendMessage(hint);
  }

  async function provisionData() {
    if (!draft || provisioning) return;
    setProvisioning(true);
    setProvisionNote(null);
    setError(null);
    try {
      const result = await quantApiClient.provisionStrategyData(
        draft.id,
        btEdited ? btFrequency : undefined,
        btStart || undefined,
        btEnd || undefined,
      );
      setProvisionNote(
        t("strategyChat.provisionDone", { rows: result.rows }),
      );
      const status = await quantApiClient.getStrategyDataStatus(
        draft.id,
        btEdited ? btFrequency : undefined,
        btStart || undefined,
        btEnd || undefined,
      );
      setDataStatus(status);
    } catch (caught) {
      setProvisionNote(
        `${t("strategyChat.provisionError")}：${
          caught instanceof Error ? caught.message : String(caught)
        }`,
      );
    } finally {
      setProvisioning(false);
    }
  }

  async function freeze() {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await quantApiClient.freezeStrategyDraft(draft.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function unfreeze() {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await quantApiClient.unfreezeStrategyDraft(draft.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await quantApiClient.saveStrategyDraft(draft.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function onOpenedPaper(accountId: string) {
    setPaperDialogOpen(false);
    router.push(`/paper?account=${accountId}`);
  }

  function runBacktest() {
    // 跳到「回测控制台」：带 ?draft=<id> 自动选中该策略并跑一次完整回测。
    if (!draft) return;
    router.push(`/backtest?draft=${draft.id}`);
  }

  async function runCodeTest() {
    if (!draft || busy) return;
    setBusy(true);
    setError(null);
    try {
      setCodeTest(await quantApiClient.codeTestStrategyDraft(draft.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setDraft(null);
    setMessages([]);
    setBacktest(null);
    setCodeTest(null);
    setInput("");
    setError(null);
    setShowCode(false);
    setDataStatus(null);
    setProvisionNote(null);
    setBtStart("");
    setBtEnd("");
    setBtEdited(false);
  }

  const examples = [
    t("strategyChat.example1"),
    t("strategyChat.example2"),
    t("strategyChat.example3"),
  ];

  return (
    <div className="sc">
      <div className="sc-toolbar">
        {draft === null ? (
          <div
            className="sc-segmented"
            role="radiogroup"
            aria-label={t("strategyChat.marketLabel")}
          >
            <span className="sc-segmented-label">
              {t("strategyChat.marketLabel")}
            </span>
            <button
              type="button"
              role="radio"
              aria-checked={market === "CN_A"}
              className={`sc-segment ${market === "CN_A" ? "is-active" : ""}`}
              onClick={() => setMarket("CN_A")}
            >
              {t(MARKET_LABEL_KEYS.CN_A)}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={market === "CN_COMMODITY_FUTURES"}
              className={`sc-segment ${
                market === "CN_COMMODITY_FUTURES" ? "is-active" : ""
              }`}
              onClick={() => setMarket("CN_COMMODITY_FUTURES")}
            >
              {t(MARKET_LABEL_KEYS.CN_COMMODITY_FUTURES)}
            </button>
          </div>
        ) : (
          <span className="sc-market-picked">
            {t("strategyChat.marketLabel")} · {t(MARKET_LABEL_KEYS[market])}
          </span>
        )}
        <button
          type="button"
          className="sc-new-chat"
          onClick={reset}
          disabled={busy}
        >
          {t("strategyChat.new")}
        </button>
      </div>

      <div className="sc-columns">
        <section className="sc-conversation" aria-label="conversation">
          {!hasConversation && (
            <div className="sc-empty">
              <h3>{t("strategyChat.emptyTitle")}</h3>
              <p>{t("strategyChat.emptyHint")}</p>
              <div className="sc-examples">
                {examples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="sc-example"
                    onClick={() => setInput(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          {hasConversation && (
            <div className="sc-thread">
              {messages.map((message, index) => (
                <div className={`sc-msg sc-msg-${message.role}`} key={index}>
                  <span className="sc-msg-role">
                    {message.role === "user"
                      ? t("strategyChat.roleUser")
                      : t("strategyChat.roleAgent")}
                  </span>
                  <div className="sc-msg-bubble">
                    {message.content.split("\n\n").map((paragraph, i) => (
                      <p key={i}>{paragraph}</p>
                    ))}
                    {message.attachments && message.attachments.length > 0 && (
                      <div className="sc-msg-attachments">
                        {message.attachments.map((attachment, i) => (
                          <span className="sc-msg-attachment" key={i}>
                            {attachment.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="sc-msg sc-msg-assistant">
                  <span className="sc-msg-role">
                    {t("strategyChat.roleAgent")}
                  </span>
                  <div className="sc-msg-bubble sc-thinking">
                    <span className="sc-dot" />
                    <span className="sc-dot" />
                    <span className="sc-dot" />
                    <em>{t("strategyChat.thinking")}</em>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="sc-composer">
            {attachments.length > 0 && (
              <div className="sc-attachments">
                {attachments.map((attachment, index) => (
                  <span className="sc-attachment" key={index}>
                    <span className="sc-attachment-kind">
                      {attachment.kind === "image"
                        ? t("strategyChat.attachmentImage")
                        : t("strategyChat.attachmentText")}
                    </span>
                    {attachment.name}
                    <button
                      type="button"
                      aria-label={t("strategyChat.removeAttachment")}
                      onClick={() =>
                        setAttachments((previous) =>
                          previous.filter((_, i) => i !== index),
                        )
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              value={input}
              disabled={busy || frozen}
              placeholder={t("strategyChat.placeholder")}
              rows={3}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button
              type="button"
              className="sc-attach"
              aria-label={t("strategyChat.attach")}
              onClick={() => document.getElementById("sc-attach-input")?.click()}
              disabled={busy || frozen}
            >
              {t("strategyChat.attach")}
            </button>
            <input
              id="sc-attach-input"
              type="file"
              multiple
              accept=".txt,.md,.csv,.json,.py,.pdf,image/*"
              style={{ display: "none" }}
              onChange={async (event) => {
                const files = event.target.files;
                if (files) {
                  const next: StrategyAttachment[] = [];
                  for (const file of Array.from(files)) {
                    try {
                      next.push(
                        await quantApiClient.uploadStrategyAttachment(
                          market,
                          file,
                        ),
                      );
                    } catch {
                      // 服务端抽取失败降级：纯文本仍可在客户端读取，图片仅记引用。
                      const kind: "text" | "image" = file.type.startsWith("image/")
                        ? "image"
                        : "text";
                      next.push({
                        name: file.name,
                        kind,
                        extractedText:
                          kind === "text"
                            ? await file.text().catch(() => "")
                            : "",
                      });
                    }
                  }
                  setAttachments((previous) => [...previous, ...next]);
                }
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className="sc-send"
              onClick={send}
              disabled={busy || frozen || !input.trim()}
            >
              {t("strategyChat.send")}
              <span aria-hidden="true" className="sc-send-arrow">
                →
              </span>
            </button>
            <span className="sc-composer-hint">
              {frozen
                ? t("strategyChat.frozenHint")
                : t("strategyChat.composerHint")}
            </span>
          </div>
          {error && <p className="sc-error">{error}</p>}
        </section>

        <aside className="sc-artifact" aria-label="strategy artifact">
          <div className="sc-artifact-head">
            <span className="eyebrow">{t("strategyChat.artifactTitle")}</span>
            {draft && (
              <span className={`sc-status sc-status-${draft.state.toLowerCase()}`}>
                {t(STATUS_KEYS[draft.state])}
              </span>
            )}
          </div>

          {!draft && (
            <div className="sc-artifact-empty">
              {t("strategyChat.artifactEmpty")}
            </div>
          )}

          {draft && (
            <div className="sc-artifact-body">
              <StageRail stage={draft.stage} />
              <h3 className="sc-artifact-title">
                {draft.title || t("strategyChat.artifactTitle")}
              </h3>
              <p className="sc-artifact-explanation">{draft.explanation}</p>
              {draft.instrumentIds.length > 0 && (
                <p className="sc-artifact-meta mono">
                  {draft.instrumentIds.join(" · ")}
                  <span className="sc-meta-sep" aria-hidden="true">
                    |
                  </span>
                  {draft.frequency}
                </p>
              )}

              {draft.instrumentIds.length > 0 && (
                <div className="sc-bt-settings">
                  <div className="sc-bt-head">
                    <span className="eyebrow">
                      {t("strategyChat.planTitle")}
                    </span>
                    {draft.backtestPlan && btEdited && (
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
                  {draft.backtestPlan && (
                    <p className="sc-bt-rationale">
                      {t("strategyChat.planRationale")}
                      {draft.backtestPlan.rationale}
                    </p>
                  )}
                  <div className="sc-bt-field">
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
                  <div className="sc-bt-field">
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
                    <small>{t("strategyChat.btRangeHint")}</small>
                  </div>
                </div>
              )}

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
                            {item.daily !== null &&
                              check.frequency !== "1d" &&
                              ` · ${t("strategyChat.dataDailyAvailable", {
                                rows: item.daily.rows,
                              })}`}
                          </span>
                        )}
                      </div>
                    )),
                  )}
                  {!dataStatus.ready && (
                    <div className="sc-data-actions">
                      <button
                        type="button"
                        className="sc-data-provision"
                        onClick={() => void provisionData()}
                        disabled={busy || provisioning}
                      >
                        {provisioning
                          ? t("strategyChat.provisioning")
                          : t("strategyChat.provision")}
                      </button>
                      <button
                        type="button"
                        className="sc-data-fix"
                        onClick={() => void sendDataFix()}
                        disabled={busy || provisioning}
                      >
                        {t("strategyChat.dataFix")}
                      </button>
                    </div>
                  )}
                  {provisionNote && (
                    <p className="sc-data-note">{provisionNote}</p>
                  )}
                </div>
              )}


              <div className="sc-artifact-actions">
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={saveDraft}
                  disabled={busy}
                >
                  {busy && codeTest === null
                    ? t("strategyChat.saved")
                    : t("strategyChat.save")}
                </button>
                {draft.code && (
                  <button
                    type="button"
                    className={`button ${
                      codeTest?.passed ? "button-secondary" : "button-primary"
                    }`}
                    onClick={runCodeTest}
                    disabled={
                      !draft.ready ||
                      busy ||
                      (dataStatus !== null && !dataStatus.ready)
                    }
                  >
                    {busy && codeTest === null
                      ? t("strategyChat.codeTesting")
                      : t("strategyChat.codeTest")}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-primary"
                  onClick={runBacktest}
                  disabled={
                    !draft.ready ||
                    busy ||
                    (dataStatus !== null && !dataStatus.ready) ||
                    (draft.code !== null && !codeTest?.passed)
                  }
                >
                  {busy
                    ? t("strategyChat.backtesting")
                    : t("strategyChat.backtest")}
                </button>
                {draft.state === "FROZEN" && (
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={() => setPaperDialogOpen(true)}
                    disabled={busy}
                  >
                    {t("strategyChat.openPaper")}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={freeze}
                  disabled={!draft.ready || busy || draft.state === "FROZEN"}
                >
                  {draft.state === "FROZEN"
                    ? t("strategyChat.frozen")
                    : t("strategyChat.freeze")}
                </button>
                {draft.state === "FROZEN" && (
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => void unfreeze()}
                    disabled={busy}
                  >
                    {t("strategyChat.unfreeze")}
                  </button>
                )}
                {draft.code && (
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => setShowCode((value) => !value)}
                  >
                    {showCode
                      ? t("strategyChat.hideCode")
                      : t("strategyChat.viewCode")}
                  </button>
                )}
              </div>
              {draft.code && (
                <div className="sc-code-test" style={{ marginBottom: 10 }}>
                  {dataStatus !== null && !dataStatus.ready ? (
                    <p className="sc-data-note" style={{ color: "var(--amber-deep)" }}>
                      {t("strategyChat.codeTestNeedData")}
                    </p>
                  ) : codeTest === null ? (
                    <p className="sc-data-note">{t("strategyChat.codeTestNote")}</p>
                  ) : codeTest.passed ? (
                    <p className="sc-data-note" style={{ color: "var(--success)" }}>
                      {t("strategyChat.codeTestPass", { ms: codeTest.durationMs })}
                    </p>
                  ) : (
                    <>
                      <p className="sc-error">{t("strategyChat.codeTestFail")}</p>
                      <pre className="sc-code">{codeTest.stderr}</pre>
                    </>
                  )}
                </div>
              )}
              {(draft.savedVersions?.length ?? 0) > 0 && (
                <p className="sc-data-note" style={{ margin: "0 0 10px" }}>
                  {t("strategyChat.savedCount", {
                    count: draft.savedVersions!.length,
                    time: draft.savedVersions![
                      draft.savedVersions!.length - 1
                    ].savedAt.slice(0, 10),
                  })}
                </p>
              )}
              {draft.state === "FROZEN" && (
                <p className="sc-data-note">{t("strategyChat.frozenActionHint")}</p>
              )}

              {draft.paperBinding && (
                <p className="sc-data-note" style={{ color: "var(--success)" }}>
                  {t("strategyChat.paperLinkedNote", {
                    account: draft.paperBinding.accountId,
                  })}
                </p>
              )}

              {draft.backtestResults.length > 0 && (
                <div className="sc-bt-history">
                  <span className="eyebrow">
                    {t("strategyChat.backtestHistory")}
                  </span>
                  <ul className="sc-bt-history-list">
                    {draft.backtestResults.map((entry, index) => (
                      <li className="sc-bt-history-row" key={`${entry.backtestHash}-${index}`}>
                        <span className="sc-bt-history-idx mono">{index + 1}</span>
                        <span className="sc-bt-history-range mono">
                          {entry.start} ~ {entry.end}
                        </span>
                        <span className="sc-bt-history-metric">
                          {entry.metrics
                            ? pct(entry.metrics.totalReturn)
                            : "—"}
                        </span>
                        <span className="sc-bt-history-hash mono muted">
                          {entry.backtestHash.slice(0, 8)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {showCode && draft.code && (
                <pre className="sc-code">{draft.code}</pre>
              )}

              {backtest && (
                <div className="sc-backtest">
                  <span className="eyebrow">
                    {t("strategyChat.backtestResult")}
                  </span>
                  {backtest.error ? (
                    <p className="sc-error">{backtest.error}</p>
                  ) : (
                    <>
                      <div className="sc-metrics">
                        <div>
                          <span>{t("bt.totalReturn")}</span>
                          <strong
                            className={
                              backtest.metrics.totalReturn >= 0
                                ? "is-pos"
                                : "is-neg"
                            }
                          >
                            {pct(backtest.metrics.totalReturn)}
                          </strong>
                        </div>
                        <div>
                          <span>{t("bt.sharpe")}</span>
                          <strong>
                            {backtest.metrics.sharpe?.toFixed(2) ?? "—"}
                          </strong>
                        </div>
                        <div>
                          <span>{t("bt.maxDrawdown")}</span>
                          <strong className="is-neg">
                            {pct(backtest.metrics.maxDrawdown)}
                          </strong>
                        </div>
                        <div>
                          <span>{t("bt.tradeCount")}</span>
                          <strong>{backtest.metrics.tradeCount}</strong>
                        </div>
                      </div>
                      {backtest.venueSpec && (
                        <p className="sc-data-note">
                          {t("bt.costBasis")}: {backtest.venueSpec.costBasis}
                          {backtest.venueSpec.feeModel
                            ? ` · ${t("bt.feeModel")}: ${backtest.venueSpec.feeModel}`
                            : ""}
                          {backtest.venueSpec.fillModel
                            ? ` · ${t("bt.fillModel")}: ${backtest.venueSpec.fillModel}`
                            : ""}
                        </p>
                      )}
                      <EquitySparkline
                        points={backtest.equityCurve}
                        trades={backtest.trades}
                      />

                      <p className="sc-data-note" style={{ marginTop: 6 }}>
                        {t("bt.tradeTimelineHint")}
                      </p>

                      {backtest.positions.length > 0 && (
                        <div style={{ marginTop: 14 }}>
                          <span className="eyebrow">{t("bt.tradeTimeline")}</span>
                          <div className="bt-trade-list">
                            {backtest.positions.map((position, index) => (
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
                                      ? `${position.avgPxClose} · ${fmtTime(
                                          position.closedAt ?? "",
                                        )}`
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

                      {backtest.trades.length > 0 && (
                        <div style={{ marginTop: 14 }}>
                          <span className="eyebrow">{t("bt.trades")}</span>
                          <div className="task-list">
                            {backtest.trades.slice(0, 30).map((trade, index) => (
                              <div className="task-row" key={index}>
                                <span className="task-stage">{trade.time}</span>
                                <strong className="mono">{trade.instrumentId}</strong>
                                <span className="muted">
                                  {trade.side === "BUY" ? t("bt.buy") : t("bt.sell")} ·{" "}
                                  {trade.quantity} @ {trade.price}
                                </span>
                                <span className="muted">{trade.quantity}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </aside>
      </div>

      {paperDialogOpen && draft && (
        <OpenPaperDialog
          initialDraftId={draft.id}
          onClose={() => setPaperDialogOpen(false)}
          onOpened={onOpenedPaper}
        />
      )}
    </div>
  );
}
