# G9-G15 Execution and Closure Gate Review

**Date:** 2026-08-14

**Decision:** `GO_FOR_G16_WITH_BROKER_AND_UI_FOLLOWUP`

## 1. Scope reviewed

G9 through G15 deliver the remaining research-platform vertical slices from
the technical design, closing the MVP acceptance gaps and the production
research-version surface:

- G9: five-clock backtest engine with A-share and commodity-futures execution.
- G10: StrategySpec and signed, content-addressed StrategyPackage.
- G11: approval, waiver, lockbox, and signed research report.
- G12: research Agent contracts (proposal, trace, gateway boundary).
- G13: paper reproduction evidence and R0-R4 grading.
- G14: factor-exposure neutrality and tracking-error constraints.
- G15: execution adapter boundary, safety controls, shadow/paper runtime.
- Golden set: transaction-cost cases for both markets.
- Frontend: promotion read endpoint and promotion panel.

## 2. Delivered

### 2.1 G9 backtest engine

`backtest/` provides `ClockKind`/`ClockEvent` five-clock ordering,
`a_share_daily_events` and `commodity_futures_daily_events`, a decimal
`Ledger`/`Order`/`Fill` model, `run_a_share_backtest` (T+1 sellability,
price-limit/halt blocking, transaction costs, next-open fills), and
`run_futures_backtest` (directional positions, margin, settlement NAV
snapshots, realized P&L on close).

### 2.2 G10 strategy package

`strategy/` provides `RiskLimits`/`StrategySpec` (market, universe, factor
weights, leverage, risk limits, cost and validation policy refs) and
`StrategyPackage`/`DataManifest` with HMAC-SHA256 signatures over a
signature-excluded content hash. Approval state is deliberately outside the
package.

### 2.3 G11 governance

`governance/` provides `ApprovalDecision`, expiring `Waiver`, two-person
`Lockbox`, and signed `ResearchReport` with `EvidenceRef` lineage.

### 2.4 G12 agent layer

`agent/` provides `ResearchProposal` (candidate factors, falsification tests,
data requests, uncertainty), `AgentTrace` (role, provider, model, prompt hash,
temperature, tokens), and the `AgentGateway` structural boundary.

### 2.5 G13 paper reproduction

`paper/` provides page-locatable `PaperClaim`/`ExtractedFormula`/
`VariableMapping`/`PaperEvidence`, and faithful/local `ReproductionResult`
graded R0-R4 where only R2+ counts as directional success.

### 2.6 G14 risk model

`portfolio/optimizer.py` now accepts factor `exposures`/`exposure_targets`
(neutrality projection) and `benchmark_weights`/`lambda_tracking_error`
(tracking-error penalty) alongside the existing long-only, cap, and
holding-count constraints.

### 2.7 G15 execution

`execution/` provides `OrderInstruction` and the `ExecutionAdapter` protocol,
`SafetyLimits`/`check_order_safety` (notional cap, kill switch, max order
quantity), `reconcile`, and `shadow_rebalance` (suggestions only, no real
orders).

## 3. Verification evidence

```text
$ ruff format --check .   178 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 168 source files
$ pytest                  445 passed, 6 skipped
$ tsc --noEmit            (frontend) clean
$ vitest run              (frontend) 47 passed
$ eslint .                (frontend) clean
```

## 4. Remaining issues

- **R1 (MEDIUM) — Real broker adapters.** The `ExecutionAdapter` protocol and
  safety controls are in place; the NautilusTrader and A-share/futures broker
  adapter implementations (with backtest/paper/live consistency tests) remain,
  as they require external dependencies not yet in `pyproject.toml`.
- **R2 (LOW) — Real historical golden data.** Golden cases are currently
  `SYNTHETIC_CONTRACT` fixtures; promotion to `formal_eligible` requires a
  licensed historical vendor with revision/PIT capability.
- **R3 (LOW) — Remaining UI pages.** Alpha Pool, StrategySpec, formal backtest,
  and paper/live operations pages (UX-007/008) remain; the promotion panel now
  ships in G15.

## 5. Gate decision

G9-G15 complete the deterministic research kernel, the strategy package, the
governance loop, the Agent boundary, paper reproduction, the risk model, and
the execution boundary, all under the existing gate discipline (content
addressing, append-only records, fail-closed safety).

The gate passes with three carried follow-ups (broker adapters, real golden
data, remaining UI pages), which move into G16.
