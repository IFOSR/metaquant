# G5 Robustness and False Discovery Gate Review

**Date:** 2026-08-13

**Decision:** `GO_FOR_G6_WITH_MULTI_CANDIDATE_FDR_FOLLOWUP`

## 1. Scope reviewed

G5 delivered Gate 3 (robustness and false-discovery control) and closed the G4
follow-up R5. Reviewed:

- Sealed label snapshots replacing the declarative label-PIT assertion.
- Deterministic negative controls (shuffled and time-shifted labels).
- Parameter-neighborhood sensitivity.
- False-discovery statistics: Benjamini-Hochberg FDR, Deflated Sharpe Ratio,
  Probability of Backtest Overfitting (CSCV).
- Append-only trial ledger.
- Control-plane integration (command, migration, repository, API) persisting the
  robustness report and ledger entry atomically.

## 2. Delivered

### 2.1 Sealed label snapshots (R5 remediation)

`FormalLabelSnapshot` resolves labels from a sealed `FORMAL_LABEL` snapshot by
`snapshot_id` + `manifest_hash`. Each row's `available_time` is strictly after
its `event_time`, and `assert_pit_safe(decision_time)` rejects any row available
at or before the decision time, so label PIT safety is a property of the sealed
snapshot rather than a client-supplied timestamp. The validate command no longer
accepts a `label_available_time`.

### 2.2 Negative controls

`run_negative_controls` runs the factor against deterministically shuffled and
time-shifted labels through the same validator and reports the observed IC
percentile against the shuffled distribution. A factor that does not clear its
controls is not a real signal.

### 2.3 Parameter neighborhood

`run_parameter_neighborhood` perturbs factor values with an index-alternating
additive offset (a value-level proxy, since `FactorComputationArtifact` does not
retain the original IR) and reports baseline IC, perturbed ICs, mean/spread, and
sign stability.

### 2.4 False-discovery statistics

`benjamini_hochberg`, `deflated_sharpe_ratio` (Bailey & Lopez de Prado with a
`sqrt(2 ln N)` deflated benchmark), and `probability_of_backtest_overfitting`
(CSCV) are deterministic, dependency-free functions with golden fixtures.

### 2.5 Trial ledger

`TrialLedger` is an immutable append-only record; `append` returns a new ledger
and rejects duplicate entry ids.

### 2.6 Integration

Migration `20260814_0007` adds `trial_ledgers`. The `assess_robustness` command
loads factor/label/policy, runs the robustness pipeline, appends a ledger entry,
and persists the `RobustnessReport` artifact, ledger row, and lineage edge in one
transaction (audit, outbox, idempotency). Disposition is `ACCEPTED` only when the
factor clears 95% of shuffled controls. `GET /experiment-runs/{id}/robustness`
returns the report.

## 3. Verification evidence

```text
$ ruff format --check .   122 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 114 source files
$ pytest                  272 passed, 4 skipped
$ make g3-integration     migration 0006->0007 round-trip + 4 passed
```

## 4. Remaining issues

- **R1 (MEDIUM) — FDR/DSR/PBO are not wired into the single-factor flow.** The
  statistics are delivered as tested pure functions, but the validate/robustness
  command does not compute them because they require the full candidate history
  (a p-value vector and a strategy-return matrix) that only exists once the Alpha
  Pool produces multiple candidates. Follow up in G6/Gate 4.
- **R2 (MEDIUM) — Parameter neighborhood is value-level, not IR-level.** The
  perturbation perturbs factor values rather than re-executing perturbed IR
  parameters (lag/window), because `FactorComputationArtifact` does not retain
  the original expression. A faithful IR parameter neighborhood requires an
  architecture decision to carry the compiled IR forward.
- **R3 (LOW) — Frontend robustness summary not yet presented.** The read endpoint
  is ready; the panel is deferred to G6.

## 5. Gate decision

G5 delivers the second validation layer. The G4 follow-up (sealed label
snapshots) is closed, negative controls and parameter-neighborhood sensitivity
are deterministic and tested, the false-discovery statistics have golden
fixtures, the trial ledger is append-only, and the whole pipeline persists
atomically through a real PostgreSQL/MinIO integration test.

The gate passes with one follow-up: **R1 (multi-candidate FDR/DSR/PBO)** must be
completed alongside the Alpha Pool in G6, since those metrics are only meaningful
over a candidate set.

G5 must preserve:

- labels resolve only from sealed `FORMAL_LABEL` snapshots and never enter Factor IR;
- deterministic negative controls and parameter-neighborhood checks;
- append-only trial ledger recorded before acceptance;
- no arbitrary Python/eval/IO in Factor IR, and snapshot-only PIT access;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics.
