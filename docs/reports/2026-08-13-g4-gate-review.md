# G4 Factor Validation Gate Review

**Date:** 2026-08-13

**Run:** `run_deepseek_g4`

**Decision:** `GO_FOR_G5_WITH_SEALED_LABEL_SNAPSHOT_REQUIRED`

## 1. Scope reviewed

Gate G4 integrated and reviewed:

- A PIT-safe `ForwardReturnLabel` contract that never enters Factor IR
  (`LabelSeries` remains forbidden inside IR).
- An immutable, versioned, per-market `ValidationPolicy` and a fail-closed
  policy catalog.
- A deterministic `FactorValidator` computing data-quality (Gate 1) and
  predictive-power (Gate 2) statistics: Pearson IC, Rank IC, ICIR, IC decay,
  quantile returns, monotonicity, top-bottom spread, and Newey-West t.
- PostgreSQL persistence for validation reports, a reversible migration
  (`20260814_0006`), and atomic report/lineage/receipt/audit/outbox commits.
- A control-plane command (`POST /experiment-runs/{run_id}:validate`) and
  report read (`GET /experiment-runs/{run_id}/validation`).
- A frontend factor-validation report panel.

The implementation remains limited to `CN_A` and `CN_COMMODITY_FUTURES` at
formal `1d` frequency, and single-horizon validation (IC decay is currently
single-point; see section 5).

## 2. Delivered baseline

### 2.1 Forward-return label contracts

- `ForwardReturnLabel` (market, horizon, field ref, return definition) and
  `LabelSeries` with deterministic content hashing.
- `assert_label_pit_safe` requires the label's available time to be strictly
  after the factor decision time.
- The Factor IR compiler keeps rejecting `LabelSeries` (`IR_LABEL_SERIES_FORBIDDEN`),
  and the PIT gateway keeps filtering snapshot rows by
  `available_time <= decision_time`, so a label can never enter factor
  computation.

### 2.2 Validation policy

- Immutable `ValidationPolicy` with coverage, constant-ratio, IC-sign, ICIR,
  Newey-West-t, quantile-count, and decay-horizon thresholds.
- In-memory and JSON catalogs that resolve policies and fail closed on missing
  or duplicate ids.

### 2.3 Deterministic validator

- `align_cross_sections` matches factor and label observations by instrument
  and event time, discarding unmatched rows and sub-2-pair sections.
- `validate_factor` computes data-quality (coverage, constant ratio) and
  predictive-power statistics with stable ordering, average-rank tie handling,
  and fixed floating-point reductions, producing a reproducible report hash.

### 2.4 Validation integration

- `FactorValidationModel` and a reversible Alembic revision.
- `validate()` reads the sealed factor computation artifact from MinIO,
  resolves the policy and label, asserts PIT safety and market consistency,
  computes the report, and commits report metadata, a lineage edge, the report
  artifact, command receipt, audit, and outbox in one transaction.
- Identical reports replay their existing validation instead of violating the
  unique `output_hash` constraint.

### 2.5 Frontend validation report

- `FactorValidationReportPanel` renders policy reference, predictive power
  (IC, rank IC, ICIR, Newey-West t), quantile returns, top-bottom spread, and
  data quality, with an explicit empty state and no profitability claims.

## 3. Verification evidence

```text
Python:   ruff clean, mypy clean (106 source files), 235 passed + 3 skipped
Frontend: 41 passed + lint + typecheck + build
g3-integration: migration round-trip through 20260814_0006 + 3 passed
           (preregister -> run -> validate end to end, report + lineage atomic)
```

## 4. Independent-review remediation

An independent review found seven defects. Four were remediated; three remain
as recorded issues (section 5).

- **R1 (MEDIUM)** — `validate()` did not check that the run, label, and policy
  shared the same market. Added a `MARKET_MISMATCH` guard.

- **R2 (MEDIUM)** — Re-validating an identical (run, label, policy) input
  under a new idempotency key produced an identical `output_hash` and hit the
  unique constraint, surfacing as a 500. The validator now replays the
  existing validation and writes a receipt/audit/outbox instead.

- **R3 (MEDIUM)** — The validation report was uploaded to MinIO but never
  written to `experiment_artifacts`, leaving the lineage target dangling.
  `validate()` now persists a `FactorValidationReport` artifact row.

- **R4 (LOW)** — `attempt_id` for the report artifact was read without a null
  guard. Added `RUN_ATTEMPT_NOT_FOUND`.

## 5. Remaining issues (not remediated in this gate)

- **R5 (HIGH) — The label PIT assertion is declarative.** `label_available_time`
  is self-reported by the client in the validate command; the server never
  derives the label's availability from its observations and does not check the
  label's event times against the decision time. The guard therefore does not
  stop a client from presenting decision-time-known data as a forward label.
  This does not compromise factor lookahead safety (Factor IR rejects
  `LabelSeries` and the PIT gateway filters factor inputs), and PAPER/LIVE
  remain hard-blocked, but it weakens the trustworthiness of validation
  results. The intended fix — resolving labels from a sealed formal snapshot
  whose `available_time` is enforced at the gateway — must land before G5.

- **R6 (MEDIUM) — Single-horizon validation.** `validate_factor` accepts one
  `LabelSeries`, so the IC decay table has a single entry. Multi-horizon decay
  requires passing multiple labels in the integration layer.

- **R7 (LOW) — Pearson IC returns 0.0 for constant series.** This is a
  deliberate convention (undefined correlation), but it can read as a real
  zero signal; a sentinel or `None` would be more honest.

## 6. Gate decision

G4 delivers the first auditable single-factor validation kernel. The
forward-return label contract, versioned policy, deterministic validator,
integration seam, and frontend report are implemented and pass the full
verification chain, with no arbitrary code or IO in the validator and no
label entry into factor computation.

The gate passes with one required follow-up: **R5 (sealed label snapshot)**
must be remediated before G5, so that forward-return labels are resolved from
sealed formal snapshots rather than client-supplied JSON with a self-reported
availability time. R6 and R7 are recorded and may be addressed alongside G5.

G4 must preserve:

- no arbitrary Python, eval, SQL, shell, network, or file IO in Factor IR or
  the validator;
- snapshot-only PIT access with `available_time <= decision_time`;
- `CN_A` and `CN_COMMODITY_FUTURES` market constraints and formal `1d`
  frequency;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics;
- production data, OIDC, broker/CTP, PAPER, and LIVE hard gates.
