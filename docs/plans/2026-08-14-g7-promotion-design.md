# G7 Promotion Scoring and Combination Pool Design (Gate 5)

**Date:** 2026-08-14

**Status:** proposed

## 1. Goal

G7 delivers Gate 5 (promotion): a hard-gate + scorecard decision that promotes a
fully validated factor into the combination pool. It closes the G6 follow-ups
R2 (independence panel) and R3 (Alpha Pool membership), and carries R1
(turnover/capacity end-to-end) forward because that requires the historical
execution and market-data path.

## 2. Gate 5 rules

From `doc/integrated-quant-pipeline-design.md` and
`doc/codex-quant-pipeline-report.md`:

- Hard gates: time safety, data quality, OOS direction, multiple-testing
  control, and minimum capacity.
- Scorecard: effect strength 25%, stability 25%, independence 20%,
  cost-adjusted value 20%, interpretability 10%.
- Only factors passing all hard gates and reaching the policy line enter the
  combination pool.
- Suspiciously strong results are `QUARANTINED`, not promoted (e.g. daily
  cost-free Sharpe > 5, IC > 0.2).

## 3. Design

### 3.1 Promotion contracts (G7-001, G7-002, G7-003)

`PromotionPolicy` holds hard-gate thresholds (minimum coverage, minimum
observations, OOS direction, FDR bound, minimum capacity), scorecard weights,
the pass line, and the quarantine thresholds.

`CandidateEvidence` aggregates the G4-G6 report metrics for one factor: data
quality, predictive power, robustness, false discovery, independence, and
capacity.

`evaluate_promotion` runs the hard gates first (fail => `REJECT`), then checks
the quarantine thresholds (`QUARANTINE`), then the weighted scorecard
(`PROMOTE` when at or above the pass line, otherwise `REJECT`). A
`PromotionDecision` records the disposition, per-gate results, per-component
scores, total score, and rationale.

### 3.2 Combination pool (G7-004)

`PromotedFactor` records a factor promoted into the pool with its promotion
evidence hash and promotion time. `CombinationPool` is an immutable set keyed by
factor IR hash that fails closed on duplicates or missing entries.

### 3.3 Integration (G7-005)

Migration `0009` adds `promotion_records` and `combination_pool_factors`. The
`promote` command loads the factor's validation, robustness, and independence
reports from the control plane, evaluates promotion, persists the decision, and
writes the factor into the combination pool and the Alpha Pool when promoted —
atomically (audit, outbox, idempotency).

### 3.4 Frontend and gate (G7-006)

Independence summary panel (closes R2) plus promotion status, then the G7 gate
review.

## 4. Non-goals

- Factor combination, risk model, optimizer, and portfolio construction (Gate 6).
- Walk-forward/OOS backtesting, NautilusTrader, PAPER, and LIVE.
- Historical `FactorSeries` execution and market-data (ADV) ingestion, which
  are required to close R1 end-to-end and remain deferred.
