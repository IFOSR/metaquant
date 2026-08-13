# G5 Robustness and False Discovery Design

**Date:** 2026-08-13

**Status:** Proposed as G5 entry scope (follows G4 `GO_FOR_G5_WITH_SEALED_LABEL_SNAPSHOT_REQUIRED`)

## 1. Objective

G4 delivered a deterministic single-factor validation kernel (Gate 1 data
quality + Gate 2 predictive power). G5 delivers the second layer: **Gate 3
robustness and false-discovery control**, and closes the G4 follow-up by
replacing the declarative label-PIT assertion with sealed label snapshots.

```text
sealed FormalLabelSnapshot (PIT-safe)
  + FactorComputationArtifact (G3, sealed)
  + ValidationPolicy
  -> deterministic robustness checks (negative controls, parameter neighborhood)
  -> false-discovery metrics (FDR, DSR, PBO)
  -> immutable RobustnessReport + trial-ledger entries
```

## 2. Scope

G5 includes:

- **R5 remediation — sealed label snapshots.** Forward-return labels are
  resolved from a sealed formal snapshot whose fields carry `available_time`
  strictly after the factor decision time, so the PIT gateway enforces
  label availability instead of a client-supplied timestamp. The validate
  command references a label snapshot by `snapshot_id` + `manifest_hash`.
- **Negative controls.** Shuffled-label and time-shifted (mismatched) labels
  run through the same validator; the factor's true IC must clear the
  negative-control distribution.
- **Parameter neighborhood.** Perturb factor parameters (e.g. lag, window)
  within a declared neighborhood and report IC stability.
- **False-discovery metrics.** Benjamini-Hochberg FDR, Deflated Sharpe Ratio,
  and Probability of Backtest Overfitting (CSCV) over the trial ledger.
- **Trial ledger.** Every candidate and every parameter tuning attempt is
  recorded, so survivors cannot be reported without their full search history.

G5 excludes:

- Gate 4 independence, turnover, cost, and capacity (Alpha Pool).
- Gate 5 promotion scoring and Alpha Pool membership.
- Formal backtesting, NautilusTrader integration, PAPER, and LIVE.

## 3. Domain model

### 3.1 FormalLabelSnapshot

A sealed formal snapshot dedicated to labels, with the same catalog and
`available_time <= decision_time` enforcement as factor snapshots. Label
fields are `LabelSeries` typed and are rejected by the Factor IR compiler.

### 3.2 RobustnessReport

An immutable content-addressed report containing:

- negative-control IC distribution (shuffled and time-shifted) and the factor's
  percentile within it;
- parameter-neighborhood IC summary (mean, spread, pass/fail per policy);
- false-discovery metrics (BH-adjusted p-value / FDR, DSR, PBO);
- trial-ledger reference and hash.

### 3.3 Trial ledger

An append-only record of every candidate and tuning attempt (factor identity,
parameters, validation policy, decision time, result hash, and disposition).
It is written before a validation is accepted, so no survivor can escape its
history.

## 4. Execution rules

- All robustness checks are deterministic (stable ordering, fixed seeds, no IO
  beyond sealed artifacts).
- Negative controls reuse the exact validator and policy so the comparison is
  apples-to-apples.
- The trial ledger entry is committed atomically with the robustness report.
- A factor that fails its policy's negative-control, FDR, DSR, or PBO threshold
  is reported as not-passed; it is never silently accepted.

## 5. Storage, API, and UI

PostgreSQL remains the metadata truth source; report payloads are
content-addressed in MinIO. The G5 API extends the experiment-run flow with a
robustness command and report read, reusing Bearer, `Idempotency-Key`,
`If-Match`, and `application/problem+json` conventions. The frontend presents
negative-control, FDR/DSR/PBO, and trial-ledger summaries without claiming
profitability or acceptance.

## 6. Verification (Gate G5)

Gate G5 requires:

- deterministic replay of robustness reports;
- PIT-safety tests proving labels resolve only from sealed snapshots and cannot
  enter factor computation;
- golden tests for FDR, DSR, and PBO on pinned fixtures;
- fail-closed tests for missing label snapshots, invalid neighborhoods, and
  threshold violations;
- trial-ledger append-only and atomicity tests;
- full Python and frontend quality gates and real PostgreSQL/MinIO integration.
