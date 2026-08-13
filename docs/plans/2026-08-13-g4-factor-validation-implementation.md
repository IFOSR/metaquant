# G4 Factor Validation Foundation Implementation Plan

**Date:** 2026-08-13

## Task DAG

```text
G4-001 ForwardReturnLabel contract ----------\
G4-002 ValidationPolicy contract -------------+-> G4-004 Validation integration
G4-003 Deterministic FactorValidator ---------/           |
                                                          +-> G4-005 UI
                                                          +-> G4-006 review
G4-004 + G4-005 + G4-006 ---------------------------------> G4-007 Gate
```

## G4-001 ForwardReturnLabel Contract

Owner scope:

- `src/quant_platform/validation/`
- `tests/validation/`
- `docs/schemas/validation/`

Deliver:

- `ForwardReturnLabel` and `LabelSeries` contracts (horizon, return
  definition, field reference, available-time rule).
- A sealed formal label snapshot with `available_time` strictly after the
  factor decision time.
- PIT-safety tests proving a label cannot be resolved at decision time and
  cannot enter Factor IR.
- Canonical hash and deterministic serialization.

## G4-002 ValidationPolicy Contract

Owner scope:

- `src/quant_platform/validation/`
- `tests/validation/`
- `config/validation-policies.json`

Deliver:

- Immutable, versioned `ValidationPolicy` (coverage, constant, IC sign,
  ICIR, NW t, quantile count, decay horizons).
- Per-market policies for `CN_A` and `CN_COMMODITY_FUTURES`.
- Policy reference/hash resolution and fail-closed behavior for a missing or
  ambiguous policy.

## G4-003 Deterministic FactorValidator

Owner scope:

- `src/quant_platform/validation/`
- `tests/validation/`
- validator golden fixtures

Deliver:

- Data-quality validation (Gate 1): coverage, missing pattern, constant and
  near-constant detection, extreme-value summary.
- Predictive-power validation (Gate 2): Pearson IC, Rank IC, ICIR, IC decay
  (1/5/10/20/60 day), quantile returns, monotonicity, top-bottom spread, and
  Newey-West adjusted t-statistics.
- Deterministic rank/quantile/float ordering; no IO; no dynamic evaluation.
- Golden tests on pinned fixtures.

## G4-004 Validation Integration

Main Agent scope:

- PostgreSQL models and a reversible Alembic migration.
- Validation repository/coordinator, API seam, audit/outbox/idempotency.
- FactorValidationReport artifact storage and lineage edges.
- Cross-module integration and real PostgreSQL/MinIO verification.

This task starts only after G4-001 through G4-003 are integrated.

## G4-005 Frontend Validation Report

Worker scope:

- `frontend/`
- `docs/ui/` contract notes

Deliver:

- HTTP/mock client types and mappers for the validation report.
- Policy reference, IC/ICIR/decay, quantile returns, and fail-closed state UI
  on the ResearchJob detail flow.
- Responsive, accessible tests and production build.

## G4-006 Independent Review

Review only. Inspect PIT safety of the label, determinism of the statistics,
transaction boundaries, authorization, and UI truthfulness. Report findings by
severity. Do not modify implementation files.

## G4-007 Gate G4

Main Agent integrates remediation, runs all quality/runtime checks, writes
`docs/reports/2026-08-1x-g4-gate-review.md`, and records one explicit decision.
Production data, OIDC, broker/CTP, PAPER, and LIVE remain hard-blocked.
