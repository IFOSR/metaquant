# G16 Review-Driven Gap Closure Gate Review

**Date:** 2026-08-14

**Decision:** `GO_FOR_G17_WITH_VENDOR_DATA_LLM_AND_UI`

## 1. Scope

G16 closes the gaps identified in the independent review against the PRD
acceptance criteria and the FR table. The review surfaced four gap classes:
substantive gaps, skeleton implementations, missing data ingestion, and
frontend incompleteness. This gate closes the substantive gaps and the parts
of the data and execution layers that are implementable without external
dependencies.

## 2. Delivered

### 2.1 Gate credibility (P0)

- **Walk-forward OOS validation (FR-403)** — `validation/oos.py`: rolling
  train/embargo/test splits, per-split train and OOS IC, `OOSReport` with
  `oos_ic_mean`/`oos_ic_ir`/`oos_hit_rate`, content-addressed.
- **Server-side promotion evidence cross-check** — `promotion.cross_check_evidence`
  rejects caller-supplied coverage/observations that disagree with the stored
  `FactorValidationReport`; the promotion gate now evaluates server-side numbers.
  Wired into `repository.promote()`.
- **Two-person approval workflow (FR-407)** — `governance.ApprovalWorkflow`
  (distinct-actor approval, rejection, expiry), `approval_workflows` table,
  approval endpoints, and promotion linkage: a PROMOTE decision enters
  `PENDING_APPROVAL` and only reaches `PROMOTED` after two approvals.

### 2.2 Execution semantics (P1)

- **Futures engine (FR-506)** — daily mark-to-market settlement, close-today
  versus close-yesterday fee offsets, delivery-month forced exit, price limits,
  and margin-based forced liquidation.
- **A-share details (FR-505)** — ST buy restriction, price collar (2% main
  board), and call-auction matching.
- **PIT invariance fail-closed** — a run whose invariance evidence fails is
  recorded as `FAILED` rather than `SUCCEEDED`, so downstream validate/promote
  reject it.

### 2.3 Data ingestion (P2)

- **Market data tables** — `market_data_sources`, `pit_observations`,
  `universe_history` (migration 0011).
- **Loader** — `MarketDataSource` registration (FR-311), `RawPITRow` contract
  (FR-301), duplicate rejection, and PIT `filter_and_resolve` (availability +
  ingestion visibility with latest-revision resolution).
- **Vendor adapter boundary** — `VendorAdapter` protocol and
  `guard_exploratory` fail-closed marking for third-party exploration sources
  (FR-312).

### 2.4 Attribution and safety

- **Attribution report (FR-507)** — gross/net return, cost breakdown, factor
  exposure, capacity utilization, unfillable ratio, roll return, and factor
  ablation, content-addressed.
- **Persistent kill switch (FR-604)** — `execution.KillSwitch` tripped/armed
  state with actor, time, and reason audit fields, content-addressed.

## 3. Verification

```text
$ ruff format --check .   189 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 177 source files
$ pytest                  497 passed, 6 skipped
```

Eight commits: `35d2441`..`210de06`.

## 4. Remaining (blocked or carried to G17)

- **R1 — Real historical golden data (MVP criterion 3).** Requires a licensed
  vendor with revision/PIT capability; synthetic fixtures cannot substitute.
- **R2 — Paper reproduction execution (FR-105).** The R0-R4 grading contracts
  exist; a full reproduction run needs a PDF parser and an LLM orchestration
  runtime.
- **R3 — Agent LLM client and runtime budget enforcement (FR-005/006).**
  Contracts exist; live LLM calls and hard budget enforcement need a model
  provider integration.
- **R4 — Dagster orchestration.** The orchestration package is a stub; a real
  job graph needs the Dagster runtime.
- **R5 — Frontend.** Validation/Independence/Promotion panels are implemented
  but not mounted; login/RBAC, lineage (FR-704), strategy/backtest (FR-705),
  and paper/live ops (FR-706) pages remain.
