# G7 Promotion Scoring and Combination Pool Gate Review

**Date:** 2026-08-14

**Decision:** `GO_FOR_G8_WITH_TURNOVER_CAPACITY_FOLLOWUP`

## 1. Scope reviewed

G7 delivered Gate 5 (promotion) and closed two G6 follow-ups. Reviewed:

- Promotion policy and scorecard contracts.
- Hard-gate + scorecard + quarantine evaluation.
- Immutable combination pool.
- Control-plane integration (migration, `promote` command, API).
- Alpha Pool membership on promotion (closes R3).

## 2. Delivered

### 2.1 Promotion contracts

`PromotionPolicy` declares hard-gate thresholds (coverage, observations, OOS
direction, FDR bound, minimum capacity), scorecard weights (effect 25%,
stability 25%, independence 20%, cost-adjusted value 20%, interpretability
10%), the pass line, and quarantine thresholds (IC > 0.2, Sharpe > 5).

`CandidateEvidence` aggregates G4-G6 report metrics. `evaluate_promotion`
runs the hard gates first (fail => REJECT), then quarantine (suspiciously
strong => QUARANTINE), then the weighted scorecard (PROMOTE/REJECT).
`PromotionDecision` records disposition, per-gate results, per-component
scores, total, and rationale.

### 2.2 Combination pool

`PromotedFactor` and the immutable `CombinationPool` key the promoted set by
factor IR hash and fail closed on duplicates or missing entries.

### 2.3 Integration

Migration `20260814_0009` adds `promotion_records` and
`combination_pool_factors`. The `promote` command loads the factor, evaluates
promotion, persists the decision artifact and record atomically, and writes the
factor into the combination pool **and** the Alpha Pool when promoted (audit,
outbox, idempotency, trial ledger).

## 3. Verification evidence

```text
$ ruff format --check .   138 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 128 source files
$ pytest                  316 passed, 6 skipped
$ make g3-integration     migration 0008->0009 round-trip + 6 passed
```

## 4. Remaining issues

- **R1 (MEDIUM, carried from G6) — Turnover and capacity are not wired
  end-to-end.** They remain tested pure functions. Closing this requires the
  historical `FactorSeries` execution path and market-data (ADV, tradability)
  ingestion, which are deferred to G8 alongside portfolio construction.
- **R2 (LOW) — Frontend independence and promotion panels deferred.** The read
  endpoints are ready; the panels are deferred.

## 5. Gate decision

G7 delivers the Gate 5 promotion vertical slice: hard-gate + scorecard +
quarantine evaluation, persisted atomically with an integration test, and Alpha
Pool membership written on promotion (closing G6 R3).

The gate passes with one carried follow-up: **R1 (turnover and capacity
end-to-end)** remains open into G8. R2 (frontend panels) is recorded and may be
addressed alongside G8.

G7 must preserve:

- hard-gate + scorecard + quarantine, no single blended score masking failures;
- append-only trial ledger recorded before acceptance;
- deterministic promotion and combination-pool semantics;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics.
