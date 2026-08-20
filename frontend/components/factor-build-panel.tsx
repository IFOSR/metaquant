"use client";

import { useState } from "react";

import { quantApiClient } from "../lib/client";
import type {
  FactorBuildSpec,
  FactorBuildSpecRecord,
  FactorCodeBundleDraft,
  MarketId,
  ModelFactorValidationReport,
} from "../lib/types";

type Step =
  | "idle"
  | "extracting"
  | "generating"
  | "smoking"
  | "persisting"
  | "training"
  | "inferring"
  | "validating";

export function FactorBuildPanel({ market }: { market: MarketId }) {
  const [paperText, setPaperText] = useState("");
  const [spec, setSpec] = useState<FactorBuildSpec | null>(null);
  const [specHash, setSpecHash] = useState<string | null>(null);
  const [specRecord, setSpecRecord] = useState<FactorBuildSpecRecord | null>(null);
  const [draft, setDraft] = useState<FactorCodeBundleDraft | null>(null);
  const [weightsHash, setWeightsHash] = useState<string | null>(null);
  const [factorValuesHash, setFactorValuesHash] = useState<string | null>(null);
  const [report, setReport] = useState<ModelFactorValidationReport | null>(null);
  const [instrumentIds, setInstrumentIds] = useState(
    "A2611.DCE,AG2702.SHF,AU2612.SHF,B2611.DCE,C2611.DCE,EG2609.DCE,HC2701.SHF,I2701.DCE,JD2611.DCE,JM2701.DCE,L2701.DCE,LH2611.DCE,M2701.DCE,RB2610.SHF,RB2701.SHF,SC2609.INE,V2701.DCE,Y2701.DCE",
  );
  const [decisionTime, setDecisionTime] = useState("2026-08-20T07:00:00Z");
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);

  function push(line: string) {
    setLog((items) => [...items, line]);
  }

  async function run<T>(next: Step, fn: () => Promise<T>): Promise<T | null> {
    setStep(next);
    setError(null);
    try {
      return await fn();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      return null;
    } finally {
      setStep("idle");
    }
  }

  async function extract() {
    const result = await run("extracting", () =>
      quantApiClient.extractBuildSpec(paperText.trim(), market),
    );
    if (result) {
      setSpec(result.spec);
      setSpecHash(result.spec_hash);
      setSpecRecord(null);
      setDraft(null);
      setWeightsHash(null);
      setFactorValuesHash(null);
      setReport(null);
      push(`抽取规格完成 spec_hash=${result.spec_hash.slice(0, 16)}…`);
    }
  }

  async function generate() {
    if (!spec) return;
    const result = await run("generating", () => quantApiClient.generateCodeDraft(spec));
    if (result) {
      setDraft(result);
      push(`代码生成完成 bundle_hash=${result.bundle_hash.slice(0, 16)}…`);
    }
  }

  async function smoke() {
    if (!spec) return;
    const result = await run("smoking", () => quantApiClient.smokeSpec(spec));
    if (result) {
      setDraft(result);
      const ok = result.smoke?.exit_code === 0;
      push(
        `试运行 ${ok ? "通过" : "失败"} exit=${result.smoke?.exit_code ?? "?"}`,
      );
    }
  }

  async function persist() {
    if (!spec || !specHash) return;
    const record = await run("persisting", async () => {
      const created = await quantApiClient.createFactorBuildSpec(spec);
      return quantApiClient.freezeFactorBuildSpec(created.id, 1);
    });
    if (record) {
      setSpecRecord(record);
      setSpecHash(record.spec_hash);
      push(`规格已冻结 spec_id=${record.id}`);
    }
  }

  async function register() {
    if (!specRecord || !specHash || !draft) return;
    await run("persisting", () =>
      quantApiClient.registerCodeBundle(specRecord.id, specHash, draft),
    );
    push("代码包已注册（内容寻址冻结）");
  }

  async function train() {
    if (!specHash || !draft) return;
    const result = await run("training", () =>
      quantApiClient.trainFactor({
        spec_hash: specHash,
        bundle_hash: draft.bundle_hash,
        instrument_ids: instrumentIds.split(",").map((s) => s.trim()).filter(Boolean),
        decision_time: decisionTime,
      }),
    );
    if (result) {
      setWeightsHash(result.weights_hash);
      push(`训练完成 weights_hash=${result.weights_hash.slice(0, 16)}…`);
    }
  }

  async function infer() {
    if (!specHash || !draft || !weightsHash) return;
    const result = await run("inferring", () =>
      quantApiClient.inferFactor({
        spec_hash: specHash,
        bundle_hash: draft.bundle_hash,
        weights_hash: weightsHash,
        instrument_ids: instrumentIds.split(",").map((s) => s.trim()).filter(Boolean),
        decision_time: decisionTime,
      }),
    );
    if (result) {
      setFactorValuesHash(result.factor_values_hash);
      push(`推理完成 factor_values_hash=${result.factor_values_hash.slice(0, 16)}…`);
    }
  }

  async function validate() {
    if (!spec || !specHash || !factorValuesHash) return;
    const result = await run("validating", () =>
      quantApiClient.validateFactor({
        spec_hash: specHash,
        factor_values_hash: factorValuesHash,
        instrument_ids: instrumentIds.split(",").map((s) => s.trim()).filter(Boolean),
        price_field: spec.label.price_field,
        horizon: spec.label.horizon,
        decision_time: decisionTime,
      }),
    );
    if (result) {
      setReport(result);
      push(`验证完成 IC=${result.pearson_ic ?? "—"} RankIC=${result.rank_ic ?? "—"}`);
    }
  }

  const busy = step !== "idle";

  return (
    <section className="panel">
      <span className="eyebrow">因子构建</span>
      <h2>研报 → 可执行模型</h2>
      <p className="lede">
        抽取构建规格，生成 model/train/infer 代码，试运行后训练推理并验证。
      </p>

      <label className="field field-wide">
        <span>研报文本</span>
        <textarea
          value={paperText}
          onChange={(event) => setPaperText(event.target.value)}
          rows={5}
          placeholder="粘贴研报文本（例如 StableAlpha 的标签/权重/中性化设定）"
        />
      </label>

      <div className="brief-template-row">
        <label className="field field-wide">
          <span>训练/推理标的（逗号分隔）</span>
          <input
            value={instrumentIds}
            onChange={(event) => setInstrumentIds(event.target.value)}
          />
        </label>
        <label className="field">
          <span>决策时点（decision_time）</span>
          <input
            value={decisionTime}
            onChange={(event) => setDecisionTime(event.target.value)}
          />
        </label>
      </div>

      <div className="button-row">
        <button
          className="button"
          type="button"
          disabled={busy || !paperText.trim()}
          onClick={extract}
        >
          {step === "extracting" ? "抽取中…" : "1. 抽取规格"}
        </button>
        <button className="button" type="button" disabled={busy || !spec} onClick={generate}>
          {step === "generating" ? "生成中…" : "2. 生成代码"}
        </button>
        <button className="button" type="button" disabled={busy || !spec} onClick={smoke}>
          {step === "smoking" ? "试运行中…" : "3. 试运行"}
        </button>
        <button className="button" type="button" disabled={busy || !spec} onClick={persist}>
          4. 冻结规格
        </button>
        <button
          className="button"
          type="button"
          disabled={busy || !specRecord || !draft}
          onClick={register}
        >
          5. 注册代码包
        </button>
        <button className="button" type="button" disabled={busy || !specHash || !draft} onClick={train}>
          {step === "training" ? "训练中…" : "6. 训练"}
        </button>
        <button
          className="button"
          type="button"
          disabled={busy || !weightsHash}
          onClick={infer}
        >
          {step === "inferring" ? "推理中…" : "7. 推理"}
        </button>
        <button
          className="button"
          type="button"
          disabled={busy || !factorValuesHash}
          onClick={validate}
        >
          {step === "validating" ? "验证中…" : "8. 验证"}
        </button>
      </div>

      {error ? (
        <div className="freshness-banner" role="alert">
          <strong>失败</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {spec ? (
        <details className="code-block">
          <summary>构建规格（{specHash?.slice(0, 16)}…）</summary>
          <pre>{JSON.stringify(spec, null, 2)}</pre>
        </details>
      ) : null}

      {draft ? (
        <div className="evidence-grid">
          {Object.entries(draft.files).map(([name, source]) => (
            <details className="code-block" key={name}>
              <summary>{name}</summary>
              <pre>{source}</pre>
            </details>
          ))}
        </div>
      ) : null}

      {report ? (
        <div className="evidence-grid">
          <section className="panel">
            <span className="eyebrow">验证报告</span>
            <dl className="kv-list">
              <dt>Pearson IC</dt>
              <dd className="mono">{report.pearson_ic?.toFixed(4) ?? "—"}</dd>
              <dt>Rank IC</dt>
              <dd className="mono">{report.rank_ic?.toFixed(4) ?? "—"}</dd>
              <dt>ICIR</dt>
              <dd className="mono">{report.icir?.toFixed(4) ?? "—"}</dd>
              <dt>覆盖率</dt>
              <dd className="mono">{report.coverage_ratio.toFixed(3)}</dd>
            </dl>
          </section>
        </div>
      ) : null}

      {log.length ? (
        <details className="code-block">
          <summary>执行日志</summary>
          <pre>{log.join("\n")}</pre>
        </details>
      ) : null}
    </section>
  );
}
