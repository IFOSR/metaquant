# G3 Research Execution Foundation Implementation Plan

**Date:** 2026-08-12

**Run:** `run_0042c74363d5`

## Task DAG

```text
G3-001 Experiment and artifact contracts ----\
G3-002 Deterministic Factor Executor ----------+-> G3-004 Execution integration
G3-003 Content-addressed artifact store -------/             |
                                                               +-> G3-005 UI
                                                               +-> G3-006 review
G3-004 + G3-005 + G3-006 ------------------------------------> G3-007 Gate
```

## G3-001 Experiment and Artifact Contracts

Owner scope:

- `src/quant_platform/experiments/`
- `tests/experiments/`
- `docs/schemas/experiments/`

Deliver:

- ExperimentSpec, ExperimentRun, Attempt, computation/validation artifact,
  lineage, state-machine, canonical hash, and fingerprint contracts.
- Formal precondition validation independent of persistence and HTTP.
- Contract and state-transition tests.

## G3-002 Deterministic Factor Executor

Owner scope:

- `src/quant_platform/factor_executor/`
- `tests/factor_executor/`
- executor golden fixtures

Deliver:

- Execution of the existing restricted AST and closed postprocess pipeline.
- Deterministic tabular input/output contracts.
- Null/Inf/divide-by-zero/window behavior.
- No dynamic evaluation or IO.
- Replay, truncation, and sentinel-isolation tests.

## G3-003 Content-Addressed Artifact Store

Owner scope:

- `src/quant_platform/artifacts/`
- `tests/artifacts/`

Deliver:

- Canonical bytes, SHA-256 addresses, immutable put/get/verify semantics.
- In-memory and MinIO adapters behind one protocol.
- Manifest and lineage-edge payload contracts.
- Collision, corruption, overwrite, and missing-object tests.

## G3-004 Research Execution Integration

Main Agent scope:

- PostgreSQL models and reversible Alembic migration.
- Experiment repository, execution coordinator, API, audit/outbox/idempotency.
- Dagster asset/job seam without making Dagster the state truth source.
- Cross-module integration and real PostgreSQL/MinIO verification.

This task starts only after G3-001 through G3-003 are integrated.

## G3-005 Frontend Experiment Monitoring

Worker scope:

- `frontend/`
- necessary `docs/ui/` contract notes

Deliver:

- HTTP/mock client types and mappers for experiment endpoints.
- Experiment status, attempts, fingerprint, validation summary, lineage, and
  failure-state UI on the ResearchJob detail flow.
- Responsive, accessible tests and production build.

## G3-006 Independent Review

Review only. Inspect domain safety, PIT/IR binding, transaction boundaries,
authorization, reproducibility claims, UI truthfulness, and missing tests.
Report findings by severity. Do not modify implementation files.

## G3-007 Gate G3

Main Agent integrates remediation, runs all quality/runtime checks, writes
`docs/reports/2026-08-12-g3-gate-review.md`, and records one explicit decision.
Production data, OIDC, broker/CTP, PAPER, and LIVE remain hard-blocked.

## Shared Worktree Rule

The repository has no initial commit, so G3 workers use the current shared
worktree. Parallel workers must only modify their assigned directories. The
main Agent owns all cross-cutting files, migrations, API wiring, dependency
changes, and final integration.

