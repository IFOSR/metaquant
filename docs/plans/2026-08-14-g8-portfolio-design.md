# G8 Portfolio Construction and Turnover/Capacity End-to-End Design

**Date:** 2026-08-14

**Status:** proposed

## 1. Goal

G8 delivers the portfolio-construction vertical slice from the technical design
§11.2/§11.3 and closes the G7 follow-up R1 (turnover and capacity end-to-end).
It also lands the trading cost models that Gate 6 requires. The remaining G7
follow-up R2 (frontend independence and promotion panels) is carried forward.

## 2. Scope

- Declarative, versioned trading cost models per market (Gate 6 cost).
- MVP factor combination: robust IC-weighted combination with shrinkage toward
  equal weight, the equal-weight baseline, factor ablation, and marginal
  contribution (technical design §11.2).
- Constrained portfolio optimizer: the §11.3 objective with full-investment,
  long-only, single-asset cap, and holding-count constraints, deterministic
  projected gradient descent, conflict diagnostics, and equal-weight fallback
  (technical design §11.3).
- R1 wiring: the historical `FactorSeries` execution path (splitting a sealed
  multi-period computation artifact into time-ordered cross-sections) and the
  market-data (ADV, tradability) ingestion path into `run_capacity`.

## 3. Design

### 3.1 Trading cost models (G8-001)

`EquityCostModel` and `FuturesCostModel` are frozen, versioned, per-market cost
models. The equity model covers commission, minimum commission, stamp duty
(sell only), transfer fee, slippage, ADV-based impact, funding, and borrow. The
futures model covers fee, slippage, impact, margin, and funding. Each exposes
single-side cost, impact cost, round-trip cost, margin requirement, a canonical
payload, and a content hash. `InMemoryCostModelCatalog` resolves by model id and
fails closed.

### 3.2 MVP combination (G8-002)

`FactorSignal` carries a factor's training-window IC, IC volatility, and
direction. Directional strength is the direction-adjusted information ratio:
`LONG_ONLY` credits positive IC, `SHORT_ONLY` credits negative IC, and
`LONG_SHORT` credits absolute IC.

`mvp_combine` computes `clip(strength)`, shrinks toward `1/n` by
`(1 - lambda) * raw + lambda * (1/n)`, then normalizes under non-negativity,
`sum = 1`, and a single-factor cap. A cap tighter than `1/n` relaxes to the
equal-weight point rather than failing. The equal-weight baseline is always
available. `factor_ablation` drops each factor in turn and measures the
expected-IC impact; `marginal_contributions` reports each factor's
weighted-IC share.

### 3.3 Constrained optimizer (G8-003)

`optimize` minimizes `-alpha'w + lambda_risk * w'Cov w + lambda_turnover *
sum|w - w_prev| + lambda_concentration * sum w^2` with deterministic projected
gradient descent. The projection enforces `sum w = 1`, `w >= 0`, and the
single-asset cap; an optional holding-count cap applies top-k truncation.
Turnover is penalized through the objective, keeping the projection convex.

Input validation short-circuits: dimension mismatch, non-finite inputs, and
covariance asymmetry each produce a diagnostic and an equal-weight fallback. An
infeasible cap (`cap * n < 1`) also falls back with a diagnostic. No constraint
is ever silently relaxed.

### 3.4 Turnover and capacity end-to-end (G8-004)

`build_factor_series` splits a multi-period `FactorComputationArtifact` into one
single-period artifact per event time and wraps them as a strictly
time-ordered `FactorSeries` ready for `run_turnover`.

`extract_tradability` reads per-instrument ADV and tradability fields from a
frozen snapshot, keeping the latest (highest event time) observation per
instrument and skipping non-positive ADV, then feeds `run_capacity`.

## 4. Non-goals

- StrategySpec, formal backtest, StrategyPackage, and PAPER/LIVE execution
  (Phase 5).
- Industry/style/beta-neutral and tracking-error constraints as hard solver
  constraints; these remain future work on top of the G8 optimizer.
- Frontend promotion panel (R2, carried forward). The independence panel
  shipped in G8 (`IndependencePanel` component plus its client method and
  mapping).
