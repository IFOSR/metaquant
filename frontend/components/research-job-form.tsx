"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ENV_LABEL_KEYS, validateResearchJob } from "../lib/domain";
import { quantApiClient } from "../lib/client";
import type { MessageKey } from "../lib/i18n";
import type {
  CreateResearchJobInput,
  Environment,
  FrequencyId,
  MarketId,
} from "../lib/types";
import { RESEARCH_TEMPLATES, type ResearchTemplate } from "../lib/research-templates";
import { useI18n } from "./i18n-provider";

const FREQUENCIES: FrequencyId[] = ["1d"];
const ENVIRONMENTS: Environment[] = ["RESEARCH", "PAPER", "LIVE"];

const initial: CreateResearchJobInput = {
  market: "CN_COMMODITY_FUTURES",
  environment: "RESEARCH",
  universeRef: "futures:liquid-initial",
  frequency: "1d",
  decisionClock: "T_CLOSE+30m",
  tradeClock: "T+1_OPEN",
  settlementClock: "T+1_SETTLEMENT",
  exchangeScope: ["SHFE"],
  contractSelection: "ACTUAL_CONTRACTS_ONLY",
  rollPolicy: "roll-policy://oi-confirmed-3d/v1",
  horizon: "5 trading days",
  briefVersionId: "brief_0042_v1",
};

export function ResearchJobForm() {
  const { t } = useI18n();
  const router = useRouter();
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<
    Array<{ field: keyof CreateResearchJobInput; message: MessageKey }>
  >([]);
  const [submitted, setSubmitted] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<ResearchTemplate | null>(
    null,
  );

  function pickTemplate(template: ResearchTemplate) {
    setSelectedTemplate(template);
    setForm(template.job);
    setErrors([]);
    setSubmitted(false);
  }

  function update<K extends keyof CreateResearchJobInput>(
    field: K,
    value: CreateResearchJobInput[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => current.filter((error) => error.field !== field));
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = validateResearchJob(form);
    if (!result.valid) {
      setErrors(result.errors);
      setSubmitted(false);
      return;
    }
    setSubmitted(true);
    void (async () => {
      try {
        const job = await quantApiClient.createResearchJob(form);
        if (selectedTemplate) {
          await quantApiClient.createBrief(
            job.id,
            selectedTemplate.brief,
            parseInt(job.version, 10),
          );
          router.push(`/research/jobs/${job.id}/brief`);
        } else {
          router.push(`/research/jobs/${job.id}`);
        }
      } catch {
        setSubmitted(false);
      }
    })();
  }

  const errorFor = (field: keyof CreateResearchJobInput) => {
    const key = errors.find((error) => error.field === field)?.message;
    return key ? t(key) : undefined;
  };

  return (
    <form className="research-form" onSubmit={submit} noValidate>
      <div className="form-section template-picker-section">
        <div className="form-section-heading">
          <span className="section-number">00</span>
          <div>
            <span className="eyebrow">快速开始</span>
            <h2>选一个研究方向，字段自动填充</h2>
          </div>
        </div>
        <div className="template-grid">
          {RESEARCH_TEMPLATES.map((template) => (
            <button
              key={template.id}
              type="button"
              className={`template-card ${
                selectedTemplate?.id === template.id ? "is-selected" : ""
              }`}
              onClick={() => pickTemplate(template)}
            >
              <strong>{template.name}</strong>
              <span>{template.description}</span>
            </button>
          ))}
        </div>
        <p className="muted">
          选一个模板会自动填好下面的市场/时钟/合约字段，并在创建后自动生成研究简报，你只需微调。
        </p>
      </div>
      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">01</span>
          <div>
            <span className="eyebrow">{t("form.marketBoundaryEyebrow")}</span>
            <h2>{t("form.marketBoundaryTitle")}</h2>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>{t("form.market")}</span>
            <select
              value={form.market}
              onChange={(event) => {
                const market = event.target.value as MarketId;
                update(
                  "market",
                  market,
                );
                if (market === "CN_A") {
                  update("universeRef", "cn-a:main-board");
                  update("settlementClock", "");
                  update("exchangeScope", []);
                  update("contractSelection", "");
                  update("rollPolicy", "");
                } else {
                  update("universeRef", "futures:liquid-initial");
                  update("settlementClock", "T+1_SETTLEMENT");
                  update("exchangeScope", ["SHFE"]);
                  update("contractSelection", "ACTUAL_CONTRACTS_ONLY");
                  update("rollPolicy", "roll-policy://oi-confirmed-3d/v1");
                }
              }}
            >
              <option value="CN_A">{t("market.cnA.label")}</option>
              <option value="CN_COMMODITY_FUTURES">
                {t("market.cnFutures.label")}
              </option>
            </select>
            <small>
              {form.market === "CN_A"
                ? t("market.cnA.note")
                : t("market.cnFutures.note")}
            </small>
          </label>
          <label className="field">
            <span>{t("form.universeRef")}</span>
            <input
              value={form.universeRef}
              onChange={(event) => update("universeRef", event.target.value)}
            />
            {errorFor("universeRef") ? <em>{errorFor("universeRef")}</em> : null}
          </label>
          <label className="field">
            <span>{t("form.frequency")}</span>
            <select
              value={form.frequency}
              onChange={(event) =>
                update("frequency", event.target.value as FrequencyId)
              }
            >
              {FREQUENCIES.map((frequency) => (
                <option key={frequency} value={frequency}>
                  {frequency}
                </option>
              ))}
            </select>
            <small>{t("form.freqNote")}</small>
          </label>
          <label className="field">
            <span>{t("form.environment")}</span>
            <select
              value={form.environment}
              onChange={(event) =>
                update("environment", event.target.value as Environment)
              }
            >
              {ENVIRONMENTS.map((environment) => (
                <option key={environment} value={environment}>
                  {t(ENV_LABEL_KEYS[environment])}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t("form.briefVersion")}</span>
            <input
              value={form.briefVersionId}
              onChange={(event) => update("briefVersionId", event.target.value)}
            />
            {errorFor("briefVersionId") ? <em>{errorFor("briefVersionId")}</em> : null}
          </label>
        </div>
      </div>

      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">02</span>
          <div>
            <span className="eyebrow">{t("form.clockEyebrow")}</span>
            <h2>{t("form.clockTitle")}</h2>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>{t("form.decisionClock")}</span>
            <input
              value={form.decisionClock}
              onChange={(event) => update("decisionClock", event.target.value)}
            />
            {errorFor("decisionClock") ? <em>{errorFor("decisionClock")}</em> : null}
          </label>
          <label className="field">
            <span>{t("form.tradeClock")}</span>
            <input
              value={form.tradeClock}
              onChange={(event) => update("tradeClock", event.target.value)}
            />
            {errorFor("tradeClock") ? <em>{errorFor("tradeClock")}</em> : null}
          </label>
          {form.market === "CN_COMMODITY_FUTURES" ? (
            <>
              <label className="field">
                <span>{t("form.settlementClock")} <b>{t("form.requiredTag")}</b></span>
                <input
                  value={form.settlementClock}
                  onChange={(event) => update("settlementClock", event.target.value)}
                  aria-invalid={Boolean(errorFor("settlementClock"))}
                />
                {errorFor("settlementClock") ? (
                  <em>{errorFor("settlementClock")}</em>
                ) : null}
              </label>
              <label className="field">
                <span>{t("form.exchangeScope")} <b>{t("form.requiredTag")}</b></span>
                <select
                  value={form.exchangeScope[0] ?? ""}
                  onChange={(event) => update("exchangeScope", [event.target.value])}
                  aria-invalid={Boolean(errorFor("exchangeScope"))}
                >
                  <option value="">{t("form.selectExchange")}</option>
                  <option value="SHFE">SHFE</option>
                  <option value="INE">INE</option>
                  <option value="DCE">DCE</option>
                  <option value="CZCE">CZCE</option>
                  <option value="GFEX">GFEX</option>
                </select>
                {errorFor("exchangeScope") ? <em>{errorFor("exchangeScope")}</em> : null}
              </label>
              <label className="field">
                <span>{t("form.contractSelection")} <b>{t("form.requiredTag")}</b></span>
                <select
                  value={form.contractSelection}
                  onChange={(event) => update("contractSelection", event.target.value)}
                >
                  <option value="">{t("form.selectContractMode")}</option>
                  <option value="ACTUAL_CONTRACTS_ONLY">{t("form.actualContractsOnly")}</option>
                </select>
                {errorFor("contractSelection") ? (
                  <em>{errorFor("contractSelection")}</em>
                ) : null}
              </label>
              <label className="field">
                <span>{t("form.rollPolicy")} <b>{t("form.requiredTag")}</b></span>
                <input
                  value={form.rollPolicy}
                  onChange={(event) => update("rollPolicy", event.target.value)}
                  aria-invalid={Boolean(errorFor("rollPolicy"))}
                />
                {errorFor("rollPolicy") ? <em>{errorFor("rollPolicy")}</em> : null}
              </label>
            </>
          ) : null}
          <label className="field">
            <span>{t("form.horizon")}</span>
            <input
              value={form.horizon}
              onChange={(event) => update("horizon", event.target.value)}
            />
            {errorFor("horizon") ? <em>{errorFor("horizon")}</em> : null}
          </label>
        </div>
      </div>

      {errors.length ? (
        <div className="form-errors" role="alert">
          <strong>{t("form.errorTitle")}</strong>
          <span>{t("form.errorDetail")}</span>
          <ul>
            {errors.map((error) => (
              <li key={`${error.field}-${error.message}`}>{t(error.message)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {submitted ? (
        <div className="form-success" role="status">
          {t("form.success")}
        </div>
      ) : null}
      <div className="form-actions">
        <button className="button button-primary" type="submit">
          {t("form.submit")}
        </button>
        <span className="form-footnote mono">
          {t("form.footnote")}
        </span>
      </div>
    </form>
  );
}
