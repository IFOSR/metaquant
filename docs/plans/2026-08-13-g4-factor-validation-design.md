# G4 Factor Validation Foundation Design

**Date:** 2026-08-13

**Status:** Proposed as G4 entry scope (follows G3 `GO_FOR_G4`)

## 1. Objective

G3 delivered a deterministic research execution slice: a compiled Factor IR
executes over a sealed PIT snapshot and produces an immutable computation
artifact plus a G3-scoped validation summary (observation counts, coverage,
summary statistics, and invariance evidence). G4 upgrades that into the first
auditable single-factor validation kernel, implementing factor-gate **Gate 1
(data quality)** and **Gate 2 (predictive power)** from the integrated design.

```text
FactorComputationArtifact (G3, sealed)
  + ForwardReturnLabel (PIT-safe, sealed)
  -> deterministic Factor Validator
  -> immutable FactorValidationReport (IC, rank IC, ICIR, decay, quantiles)
  -> ExperimentRun validation summary + lineage
```

This is a single-factor validation kernel, not a portfolio or trading system.

## 2. Scope

G4 includes:

- A PIT-safe `ForwardReturnLabel` contract that never enters Factor IR
  (`LabelSeries` remains forbidden inside IR; it is a validation input only).
- Data-quality validation (Gate 1): coverage, missing pattern, constant and
  near-constant detection, extreme-value report, and deterministic replay.
- Predictive-power validation (Gate 2): Pearson IC, Rank IC, ICIR, IC decay
  (1/5/10/20/60 day), quantile (layer) returns, monotonicity, top-bottom
  spread, and Newey-West adjusted t-statistics.
- A versioned `ValidationPolicy` that supplies thresholds per market rather
  than hard-coding them.
- A deterministic `FactorValidator` that reads the sealed computation artifact
  and the sealed label snapshot and emits an immutable
  `FactorValidationReport` artifact with lineage.
- Frontend presentation of the validation report on the experiment detail.

G4 excludes:

- FDR, DSR, PBO, and the trial ledger (Gate 3).
- Alpha Pool independence, orthogonalization, turnover, cost, and capacity
  (Gate 4).
- Alpha Pool membership and factor combination (Gate 5).
- Formal backtesting, NautilusTrader integration, PAPER, and LIVE.
- Production data suppliers, production OIDC, and broker/CTP connectivity.

## 3. Domain model

### 3.1 ForwardReturnLabel

A `ForwardReturnLabel` binds, per market and horizon:

- a field reference resolved from a sealed formal snapshot whose
  `available_time` is strictly after the factor's decision time (this is what
  makes it PIT-safe: the PIT gateway would refuse it at decision time);
- a horizon (1/5/10/20/60 trading days);
- a return definition (close-to-close forward return).

The label is stored as an immutable artifact and never referenced by Factor IR.
The Factor IR compiler keeps rejecting `LabelSeries` with
`IR_LABEL_SERIES_FORBIDDEN`.

### 3.2 ValidationPolicy

A `ValidationPolicy` is an immutable, versioned, per-market policy carrying:

- minimum coverage and minimum observation thresholds;
- constant/near-constant thresholds;
- IC sign expectation (or `ANY`);
- minimum ICIR and Newey-West t thresholds;
- quantile count (default 5);
- decay horizons to report.

Policy thresholds are data, not code. `CN_A` and `CN_COMMODITY_FUTURES` use
different policies.

### 3.3 FactorValidationReport

The report is an immutable content-addressed artifact containing:

- policy reference and its hash;
- data-quality section (coverage, missing, constant, extreme-value summary);
- predictive-power section (IC series, Rank IC series, ICIR, NW t-stat, decay
  table, quantile returns, monotonicity, top-bottom spread);
- the sample alignment used (factor timestamps vs label timestamps);
- input hashes (computation artifact hash, label artifact hash) and output hash.

It must not claim profitability, factor acceptance, or production readiness.

## 4. Execution rules

The validator fails closed unless:

- the computation artifact is immutable and its hash matches the run lineage;
- the label snapshot is sealed, formal, and its `available_time` is strictly
  after the factor decision time;
- the label market, universe, and frequency match the experiment;
- the validation policy is explicit and versioned.

Determinism requirements:

- IC and rank IC use stable sorting for rank ties;
- quantile assignment uses deterministic break handling (e.g. sorted index);
- floating-point reductions use a fixed order (sorted instrument/time order);
- the report output hash is derived from canonical JSON, so identical inputs
  reproduce identical reports.

The validator does no IO beyond reading already-sealed artifacts and does not
evaluate arbitrary code.

## 5. Storage, transactions, API, and UI

PostgreSQL remains the metadata truth source; large report payloads are
content-addressed in MinIO. Each validation command atomically commits domain
state, command receipt, AuditEvent, outbox event, report metadata, and lineage
edges. Artifact bytes are uploaded and SHA-256 verified before metadata commit.

The bounded G4 API adds a validation command and report reads (exact routes to
be fixed at implementation) with the same Bearer, `Idempotency-Key`, `If-Match`,
and `application/problem+json` conventions as G3.

The frontend renders the validation report server-authoritatively: policy
reference, IC/ICIR/decay, quantile returns, and any fail-closed state. It does
not expose PAPER or LIVE actions.

## 6. Verification (Gate G4)

Gate G4 requires:

- deterministic replay producing identical validation hashes;
- PIT-safety tests proving the label cannot leak into factor computation;
- golden tests for IC, Rank IC, ICIR, decay, quantile, and NW t-stat on pinned
  fixtures;
- fail-closed tests for non-sealed labels, market/frequency mismatch, missing
  policy, and invalid horizons;
- full Python and frontend quality gates;
- real PostgreSQL/MinIO integration for the validation command and artifacts.
