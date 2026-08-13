"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { MARKET_LABELS, MARKET_NOTES, validateResearchJob } from "../lib/domain";
import { quantApiClient } from "../lib/client";
import type { CreateResearchJobInput, MarketId } from "../lib/types";

const initial: CreateResearchJobInput = {
  market: "CN_COMMODITY_FUTURES",
  universeRef: "futures:liquid-initial",
  frequency: "1d",
  decisionClock: "T close",
  tradeClock: "T+1 open",
  settlementClock: "T+1 settlement",
  exchangeScope: ["SHFE"],
  contractSelection: "ACTUAL_CONTRACTS_ONLY",
  rollPolicy: "roll-policy://oi-confirmed-3d/v1",
  horizon: "5 trading days",
  briefVersionId: "brief_0042_v1",
};

export function ResearchJobForm() {
  const router = useRouter();
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<
    Array<{ field: keyof CreateResearchJobInput; message: string }>
  >([]);
  const [submitted, setSubmitted] = useState(false);

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
    void quantApiClient.createResearchJob(form).then((job) => {
      router.push(`/research/jobs/${job.id}`);
    });
  }

  const errorFor = (field: keyof CreateResearchJobInput) =>
    errors.find((error) => error.field === field)?.message;

  return (
    <form className="research-form" onSubmit={submit} noValidate>
      <div className="form-section">
        <div className="form-section-heading">
          <span className="section-number">01</span>
          <div>
            <span className="eyebrow">Market boundary</span>
            <h2>Choose the facts this job can touch.</h2>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>Market</span>
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
                  update("settlementClock", "T+1 settlement");
                  update("exchangeScope", ["SHFE"]);
                  update("contractSelection", "ACTUAL_CONTRACTS_ONLY");
                  update("rollPolicy", "roll-policy://oi-confirmed-3d/v1");
                }
              }}
            >
              <option value="CN_A">{MARKET_LABELS.CN_A}</option>
              <option value="CN_COMMODITY_FUTURES">
                {MARKET_LABELS.CN_COMMODITY_FUTURES}
              </option>
            </select>
            <small>{MARKET_NOTES[form.market]}</small>
          </label>
          <label className="field">
            <span>Universe reference</span>
            <input
              value={form.universeRef}
              onChange={(event) => update("universeRef", event.target.value)}
            />
            {errorFor("universeRef") ? <em>{errorFor("universeRef")}</em> : null}
          </label>
          <label className="field">
            <span>Frequency</span>
            <select
              value={form.frequency}
              onChange={(event) =>
                update("frequency", event.target.value as CreateResearchJobInput["frequency"])
              }
            >
              <option value="1d">1d / enabled</option>
              <option value="5m" disabled>
                5m / pending gate
              </option>
            </select>
            <small>G1 formal research stays daily until data and rule golden sets pass.</small>
          </label>
          <label className="field">
            <span>Research brief version</span>
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
            <span className="eyebrow">Clock and execution</span>
            <h2>Make timing explicit before a run exists.</h2>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>Decision clock</span>
            <input
              value={form.decisionClock}
              onChange={(event) => update("decisionClock", event.target.value)}
            />
            {errorFor("decisionClock") ? <em>{errorFor("decisionClock")}</em> : null}
          </label>
          <label className="field">
            <span>Trade clock</span>
            <input
              value={form.tradeClock}
              onChange={(event) => update("tradeClock", event.target.value)}
            />
            {errorFor("tradeClock") ? <em>{errorFor("tradeClock")}</em> : null}
          </label>
          {form.market === "CN_COMMODITY_FUTURES" ? (
            <>
              <label className="field">
                <span>Settlement clock <b>required</b></span>
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
                <span>Exchange scope <b>required</b></span>
                <select
                  value={form.exchangeScope[0] ?? ""}
                  onChange={(event) => update("exchangeScope", [event.target.value])}
                  aria-invalid={Boolean(errorFor("exchangeScope"))}
                >
                  <option value="">Select exchange</option>
                  <option value="SHFE">SHFE</option>
                  <option value="INE">INE</option>
                  <option value="DCE">DCE</option>
                  <option value="CZCE">CZCE</option>
                  <option value="GFEX">GFEX</option>
                </select>
                {errorFor("exchangeScope") ? <em>{errorFor("exchangeScope")}</em> : null}
              </label>
              <label className="field">
                <span>Contract selection <b>required</b></span>
                <select
                  value={form.contractSelection}
                  onChange={(event) => update("contractSelection", event.target.value)}
                >
                  <option value="">Select contract mode</option>
                  <option value="ACTUAL_CONTRACTS_ONLY">Actual contracts only</option>
                </select>
                {errorFor("contractSelection") ? (
                  <em>{errorFor("contractSelection")}</em>
                ) : null}
              </label>
              <label className="field">
                <span>Immutable roll policy <b>required</b></span>
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
            <span>Horizon</span>
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
          <strong>Cannot create this job yet.</strong>
          <span>Resolve the market contract fields below before submitting.</span>
          <ul>
            {errors.map((error) => (
              <li key={`${error.field}-${error.message}`}>{error.message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {submitted ? (
        <div className="form-success" role="status">
          Draft accepted. Opening the new ResearchJob snapshot…
        </div>
      ) : null}
      <div className="form-actions">
        <button className="button button-primary" type="submit">
          Create ResearchJob
        </button>
        <span className="form-footnote mono">
          POST /v1/research-jobs · Idempotency-Key attached by client
        </span>
      </div>
    </form>
  );
}
