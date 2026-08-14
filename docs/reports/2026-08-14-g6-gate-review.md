# G6 Independence, Turnover, and Capacity Gate Review

**Date:** 2026-08-14

**Decision:** `GO_FOR_G7_WITH_CAPACITY_INTEGRATION_FOLLOWUP`

## 1. Scope reviewed

G6 delivered Gate 4 (independence, turnover, and capacity) and closed the G5
follow-up R1 (multi-candidate FDR/DSR/PBO). Reviewed:

- Alpha Pool contracts.
- Cross-sectional and orthogonalized independence analysis.
- Turnover and signal half-life.
- Declarative capacity model and AUM curve.
- Multi-candidate false-discovery flow (BH FDR, DSR, PBO).
- Control-plane integration (migration, `assess_independence` command, API).
- Independence read endpoint.

## 2. Delivered

### 2.1 Alpha Pool contracts

`AlphaPoolFactor` records a promoted factor's identity, direction, universe,
horizon, policy, risk-premium marker, lifecycle state, and OOS IC. `AlphaPool`
is an immutable set keyed by factor IR hash that fails closed on duplicates or
missing entries.

### 2.2 Independence

`run_independence_analysis` computes cross-sectional Pearson/Spearman
correlation with each pool factor, an orthogonalized candidate (Gram-Schmidt
residual), its incremental IC, and a `replicated_risk_factor` flag when the
candidate correlates above threshold with a known factor. Verified on identical
(replicated, incremental IC collapses to zero) and orthogonal (incremental IC
preserved) fixtures.

### 2.3 Turnover

`FactorSeries` is a strictly time-ordered, instrument-unique sequence of
cross-sections. `run_turnover` reports raw weight turnover, buffered rank
turnover, and signal half-life from lag-1 autocorrelation.

### 2.4 Capacity

`CapacityModel` declares ADV participation cap, impact coefficient, margin rate,
and limit-up/down and suspension exclusions. `run_capacity` returns per-name
capacity and the AUM capacity curve at participation steps.

### 2.5 Multi-candidate false discovery (closes R1)

`run_false_discovery` wires BH FDR, Deflated Sharpe Ratio, and PBO over a
candidate p-value vector and strategy-return matrix in one deterministic flow.

### 2.6 Integration

Migration `20260814_0008` adds `alpha_pool_factors` and `independence_reports`.
The `assess_independence` command loads candidate and pool factors plus the
label, runs the independence analysis, and persists the report, ledger entry,
and lineage edge atomically (audit, outbox, idempotency). Disposition is
`REJECTED` when the factor replicates a pool factor. A read endpoint returns
the latest report.

## 3. Verification evidence

```text
$ ruff format --check .   133 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 124 source files
$ pytest                  303 passed, 5 skipped
$ make g3-integration     migration 0007->0008 round-trip + 5 passed
```

## 4. Remaining issues

- **R1 (MEDIUM) — Turnover and capacity are not wired end-to-end.** They are
  delivered as tested pure functions, but the control plane does not compute
  them because turnover needs a `FactorSeries` (historical cross-sections) and
  capacity needs per-name ADV and tradability data, neither of which is
  produced by the current single-run execution path. Follow up in G7.
- **R2 (LOW) — Independence panel not presented in the frontend.** The read
  endpoint is ready; the panel is deferred.
- **R3 (LOW) — Alpha Pool membership is not mutated by `assess_independence`.**
  The report is persisted but promotion into `alpha_pool_factors` is deferred to
  Gate 5 promotion rules (G7).

## 5. Gate decision

G6 delivers the first Gate 4 vertical slice. Independence is computed and
persisted end-to-end with an atomic transaction and integration test; turnover,
capacity, and multi-candidate false discovery are delivered as deterministic,
tested contracts. The G5 R1 follow-up is closed.

The gate passes with one follow-up: **R1 (turnover and capacity end-to-end)**
must be completed in G7 alongside Gate 5 promotion scoring, since those
analyses require the historical execution and market-data path.

G6 must preserve:

- no arbitrary Python/eval/IO in Factor IR, and snapshot-only PIT access;
- deterministic independence, turnover, capacity, and false-discovery analyses;
- append-only trial ledger recorded before acceptance;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics.
