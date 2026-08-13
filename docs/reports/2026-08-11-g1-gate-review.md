# G1 Integration Gate Review

**Date:** 2026-08-11

**Decision:** `GO_FOR_G2_FOUNDATION_WITH_EXTERNAL_PRODUCTION_GATES_BLOCKED`

## 1. Scope reviewed

Gate G1 reviewed the four implementation slices created from the approved G0
baseline:

- ResearchJob and ResearchBriefVersion persistence and Control Plane API.
- CN A-share and CN commodity-futures data/rule contracts and golden harness.
- Authentication, capability, problem, idempotency, concurrency, audit, outbox,
  consumer deduplication, and reconnect contracts.
- Next.js research workbench shell and ResearchJob/ResearchBrief vertical slice.

The implementation remains limited to `CN_A` and
`CN_COMMODITY_FUTURES`. Formal research frequency remains `1d`.

## 2. Delivered baseline

### 2.1 Research Control Plane

- PostgreSQL-compatible SQLAlchemy models for ResearchJob,
  ResearchBriefVersion, and persistent command receipts.
- Create/list/get ResearchJob endpoints.
- Create/list/get/update/freeze ResearchBriefVersion endpoints.
- DRAFT/FROZEN immutability, monotonic resource versions, strong ETags,
  `If-Match`, safe 404, `application/problem+json`, and idempotent command
  replay.
- Actor identity is derived from the authenticated principal adapter and is
  never accepted from command bodies.
- Reversible Alembic revision `20260811_0002`.

### 2.2 Market and data contracts

- Independent market definitions and clocks for CN A-shares and commodity
  futures.
- DatasetContract, DatasetSnapshot, TradingRuleVersion, RuleSetSnapshot,
  license propagation, sealed/revoked lifecycle, and formal-use checks.
- Deterministic cases for A-share T+1, price limits, suspension, ST status,
  point-in-time membership, and corporate actions.
- Deterministic cases for futures night-session trade-date assignment,
  settlement, margin, fees, close-today/close-yesterday, delivery exit, and
  no-future main-contract selection.
- Frozen JSON fixtures with SHA-256 manifest verification.

### 2.3 Security and event foundation

- Scoped Principal, Scope, and Capability models.
- Static test Bearer provider and OIDC/JWT provider seam.
- PAPER/LIVE capability hard blocking.
- Shared problem, strong ETag, `If-Match`, idempotency, AuditEvent, outbox,
  consumer deduplication, and reconnect snapshot-required contracts.
- Storage protocols isolate the current in-memory reference implementations
  from later PostgreSQL adapters.

### 2.4 Frontend vertical slice

- Next.js 16 App Router, React 19, and strict TypeScript application.
- Environment/market workbench shell with server-provided capability
  boundaries.
- ResearchJob list, create, and detail views.
- ResearchBrief draft and freeze interaction.
- Explicit loading, empty, error, permission, stale, and long-running states.
- Commodity-futures form enforcement for exchange scope, actual contracts,
  settlement clock, and immutable roll policy.
- Desktop and 360px responsive layouts with keyboard focus treatment.

## 3. Verification evidence

### Python and contracts

```text
$ make check
47 files already formatted
All checks passed!
Success: no issues found in 44 source files
101 passed
```

The 101 tests include 11 frozen OpenAPI contract tests, 42 market tests, 38
security/control-plane tests, and Research API/lifecycle tests.

### Database migration

An isolated PostgreSQL 16 Compose project completed:

```text
upgrade -> 20260811_0001 -> 20260811_0002
downgrade 20260811_0002 -> 20260811_0001
upgrade 20260811_0001 -> 20260811_0002
```

### Runtime smoke

An isolated Compose project started PostgreSQL, MinIO, migrations, and API.
PostgreSQL, MinIO, and API all reached healthy state. `/health/ready` returned
both dependency checks as `ok`; an authenticated, idempotent ResearchJob create
returned `202 ACCEPTED`, and the created job was returned by the list endpoint.

Default Compose and the optional orchestration/tracking profiles both passed
`docker compose config --quiet`.

### Frontend

```text
$ npm run lint
passed
$ npm run typecheck
passed
$ npm test
9 passed
$ npm run build
passed
```

The production build emitted the overview, job list, new-job, job detail, and
brief routes.

## 4. Gate findings

No G1 code or contract defect remains that blocks the next foundation phase.
The four original stalled Worker tasks are complete and their shared-worktree
changes pass integrated verification.

The following items are deliberately not represented as completed:

- No production historical or real-time data supplier is selected or approved.
- Golden cases are synthetic contract fixtures, not licensed historical truth.
- The OIDC/JWT verifier is an integration seam; no production identity issuer
  or key rotation configuration is approved.
- Generic audit, outbox, and consumer inbox stores still need PostgreSQL
  adapters and transaction wiring with domain changes.
- The frontend uses a typed mock client; generated OpenAPI client and live API
  wiring remain a later integration task.
- No broker, CTP production account, paper deployment, live deployment, or
  live credential is approved.
- No PAPER or LIVE capability is enabled.

## 5. Gate decision

G1 is complete. G2 may start deterministic Factor IR, PIT Data Gateway
adapters, PostgreSQL audit/outbox integration, and generated frontend client
work, provided each change continues to use the G0 contract baseline.

Production data, broker/CTP, PAPER, and LIVE work remain hard-blocked behind
separate evidence, security, and approval gates.
