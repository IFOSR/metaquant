# G8 Portfolio Construction and Turnover/Capacity Gate Review

**Date:** 2026-08-14

**Decision:** `GO_FOR_G9_WITH_FRONTEND_FOLLOWUP`

## 1. Scope reviewed

G8 delivered the portfolio-construction vertical slice and closed the G7
follow-up R1. Reviewed:

- Declarative trading cost models (equity and futures).
- MVP factor combination (robust IC weighting + shrinkage + ablation).
- Constrained portfolio optimizer (objective + constraints + diagnostics).
- Turnover and capacity end-to-end wiring (historical `FactorSeries` path and
  market-data ingestion).

## 2. Delivered

### 2.1 Trading cost models (G8-001)

`EquityCostModel` and `FuturesCostModel` are frozen, versioned, per-market cost
models with deterministic single-side, impact, and round-trip cost arithmetic.
`InMemoryCostModelCatalog` resolves by id and fails closed. Stamp duty is
applied sell-side only; the futures model separates margin requirement.

### 2.2 MVP combination (G8-002)

`FactorSignal` carries training-window IC and IC volatility with direction.
`mvp_combine` computes direction-adjusted information ratios, clips, shrinks
toward `1/n`, and normalizes under non-negativity, `sum = 1`, and a
single-factor cap. The equal-weight baseline, factor ablation, and marginal
contributions are all deterministic.

### 2.3 Constrained optimizer (G8-003)

`optimize` minimizes the §11.3 objective via deterministic projected gradient
descent with full-investment, long-only, single-asset cap, and holding-count
constraints. Dimension mismatch, non-finite inputs, covariance asymmetry, and
infeasible caps produce diagnostics and an equal-weight fallback — no silent
constraint relaxation.

### 2.4 Turnover and capacity end-to-end (G8-004)

`build_factor_series` splits a multi-period computation artifact into strictly
time-ordered cross-sections for `run_turnover`. `extract_tradability` reads
per-instrument ADV and tradability from a frozen snapshot for `run_capacity`.

## 3. Verification evidence

```text
$ ruff format --check .   146 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 136 source files
$ pytest                  360 passed, 6 skipped
$ tsc --noEmit            (frontend) clean
$ vitest run              (frontend) 45 passed
$ eslint .                (frontend) clean
```

## 4. Remaining issues

- **R1 (LOW) — Frontend promotion panel.** The independence panel shipped in
  G8 (`IndependencePanel` component, `getExperimentIndependence` client method,
  snake_case→camelCase mapping, and tests). The promotion read surface (a `GET`
  endpoint over `promotion_records`) and its frontend panel remain deferred to
  G9.

## 5. Gate decision

G8 delivers the portfolio-construction vertical slice (MVP combination and
constrained optimizer) and closes the G7 R1 turnover/capacity follow-up with a
tested end-to-end wiring path.

The gate passes with one carried follow-up: **R1 (frontend panels)** moves
forward into G9 alongside strategy specification and formal backtesting.

G8 must preserve:

- deterministic factor weights estimated only on training-window IC;
- the equal-weight baseline always available;
- optimizer diagnostics with equal-weight fallback, never silent relaxation;
- immutable cost models keyed by content hash.
