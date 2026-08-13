# G6 Independence, Turnover, and Capacity Design (Gate 4)

**Date:** 2026-08-13

**Status:** proposed

## 1. Goal

G6 delivers Gate 4 (independence, turnover, and capacity) and closes the G5
follow-up R1 (multi-candidate FDR/DSR/PBO). It introduces the Alpha Pool and
the analyses that decide whether a validated factor adds information beyond
what the pool already holds, and whether it can be traded at a useful size.

## 2. What Gate 4 requires

From `doc/integrated-quant-pipeline-design.md` and
`doc/codex-quant-pipeline-report.md`:

- Cross-sectional correlation with existing Alpha Pool factors.
- Factor-return correlation with existing Alpha Pool factors.
- Incremental IC after orthogonalization.
- Raw turnover, buffered turnover, and signal half-life.
- Capacity: ADV participation, impact, limit-up/down, suspension, and
  margin constraints, and the AUM capacity curve.
- Detect unintentional replication of known risk factors, or explicitly mark
  the factor as a risk premium.

## 3. Design

### 3.1 Alpha Pool contracts (G6-001)

`AlphaPoolFactor` records a promoted factor: factor identity, direction,
universe, horizon, validation policy, OOS metrics, correlation with peers,
capacity envelope, and lifecycle state. `AlphaPool` is an immutable set with
membership resolution keyed by `factor_ir_hash`, failing closed on duplicates
or missing entries.

### 3.2 Independence (G6-002)

`run_independence_analysis` takes a candidate factor, the pool factors aligned
on the same cross-section, and the label, and produces an
`IndependenceReport`:

- cross-sectional Pearson/Spearman correlation of the candidate with each pool
  factor;
- orthogonalized candidate (residual of the candidate regressed on the pool
  factors) and its incremental IC;
- a `replicated_risk_factor` flag when the candidate correlates above the
  policy threshold with a known risk factor, unless it is marked as a risk
  premium.

### 3.3 Turnover (G6-003)

A `FactorSeries` is a time-ordered sequence of cross-sections. `run_turnover`
computes raw one-period turnover, buffered turnover (fraction of names whose
rank change exceeds a buffer), and signal half-life (autocorrelation decay).

### 3.4 Capacity (G6-004)

A declarative `CapacityModel` (ADV participation cap, impact coefficient,
limit-up/down and suspension exclusions, margin constraint) drives a
deterministic `run_capacity` that returns per-name capacity and the AUM
capacity curve at participation steps.

### 3.5 Multi-candidate FDR/DSR/PBO (G6-005, closes R1)

Wire the G5 statistics into an end-to-end flow over a candidate set: p-value
vector for BH FDR, and the strategy-return matrix for DSR/PBO. A `run_false_discovery`
function takes the candidate set and trial ledger and returns adjusted
significance and overfitting probability.

### 3.6 Integration (G6-006)

Migration `0008` adds `alpha_pool_factors` and `independence_reports`. A new
`assess_independence` command persists the `IndependenceReport` artifact,
lineage, audit, outbox, and idempotency atomically, and appends the candidate
to the trial ledger.

### 3.7 Frontend and gate (G6-007)

A read endpoint plus a minimal independence summary, then the G6 gate review.

## 4. Non-goals

- Gate 5 promotion scoring and Alpha Pool membership rules.
- Factor combination, risk model, optimizer, and portfolio construction.
- Formal backtesting, NautilusTrader, PAPER, and LIVE.
- Production data suppliers, OIDC, and broker/CTP connectivity.
