# G5 Robustness and False Discovery Implementation Plan

**Date:** 2026-08-13

**Follows:** `docs/plans/2026-08-13-g5-robustness-design.md`

## Task breakdown

- **G5-001 — Sealed label snapshots (R5).** Add `FormalLabelSnapshot` and a
  label snapshot catalog with the same `available_time <= decision_time`
  PIT enforcement as factor snapshots. Change the validate command to accept
  `label_snapshot_id` + `label_snapshot_manifest_hash` and resolve the
  `LabelSeries` from the sealed snapshot; remove the client-supplied
  `label_available_time`. Compiler rejects label fields in Factor IR.
- **G5-002 — Negative controls.** Add deterministic shuffled-label and
  time-shifted-label controls that reuse the G4 validator, and report the
  factor IC percentile against the control distribution.
- **G5-003 — Parameter neighborhood.** Add a declared parameter neighborhood
  (perturb lag/window), run the validator per perturbation, and report IC
  stability (mean, spread, pass/fail per policy).
- **G5-004 — False discovery (BH FDR).** Add Benjamini-Hochberg adjustment
  over the ledger of candidate p-values.
- **G5-005 — DSR and PBO.** Add Deflated Sharpe Ratio and Probability of
  Backtest Overfitting (CSCV) over the trial ledger.
- **G5-006 — Trial ledger.** Add an append-only ledger recording every
  candidate and tuning attempt with identity, parameters, policy, decision
  time, result hash, and disposition; committed atomically with the report.
- **G5-007 — Integration.** Extend the validation command/API, migration, and
  repository to produce and persist `RobustnessReport` with the trial-ledger
  entry in one transaction (audit, outbox, idempotency, lineage).
- **G5-008 — Frontend and gate.** Present negative-control, FDR/DSR/PBO, and
  ledger summaries; write the G5 gate report.

## Verification per task

Each task lands with unit tests (deterministic replay, PIT-safety, fail-closed,
golden fixtures for FDR/DSR/PBO) and the full quality chain. G5-007 adds a
real PostgreSQL/MinIO integration test.

## Ordering

`G5-001` first (it is the G4 gate follow-up and a prerequisite for every other
task), then `G5-002` through `G5-005` in sequence (each depends on the prior
ledger/control scaffolding), then `G5-006`, `G5-007`, `G5-008`.
