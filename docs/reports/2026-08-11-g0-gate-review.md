# Gate G0 Integration Review

**Date:** 2026-08-11

**Run:** `run_0042c74363d5`

**Task:** `G0-005 Integration Review and Gate G0`

**Decision:** GO for G1 implementation, with external production gates blocked

## 1. Scope reviewed

The main agent integrated and reviewed:

- G0 backend and local infrastructure baseline.
- CN A-share and CN commodity-futures market/data baseline.
- Domain, API, event, security, and test contract review.
- P0/P1 product interaction and UI information architecture.
- Control Plane OpenAPI mock and JSON fixtures.
- PRD, integrated pipeline design, and technical design consistency.

Kimi and Pai providers were unavailable. Their assigned G0 responsibilities
were completed by explicitly identified Codex fallback workers. No fallback
result was treated as an external vendor, broker, legal, or live approval.

## 2. Gate findings resolved

### 2.1 Formal backtest dependency

The previous cycle:

```text
formal backtest requires StrategyPackage
StrategyPackage requires an accepted formal backtest
```

was replaced with:

```text
StrategySpecVersion
  -> immutable StrategyBuildArtifact
  -> formal BacktestRun
  -> immutable StrategyPackagePayload
  -> environment-specific PackageAttestation
```

Approval status is no longer stored inside the immutable package payload.

### 2.2 State ownership

The shared end-to-end `ResearchState` was rejected. ResearchJob,
ResearchBriefVersion, ExperimentSpec, ExperimentRun, Attempt, Replication,
PackageRelease, and DeploymentRun now have separate state machines.

### 2.3 Security and command consistency

- Root OIDC and Bearer JWT security schemes are defined.
- Client-supplied actor was removed from CommandMetadata.
- Every write requires `Idempotency-Key`.
- Existing aggregate mutations require `If-Match`.
- Object-level authorization uses safe non-enumerating response semantics.
- Errors use an RFC 9457-style problem schema.
- Reconnect fixtures require an authoritative GET snapshot before writes.

### 2.4 Versioned research and provenance

- ResearchBrief has draft, update, read, history, and freeze contracts.
- Candidate records include direction, lookback, and failure conditions.
- Reports include experiment spec/run IDs, code SHA, image digest,
  run fingerprint, policy versions, approvals, and evidence catalog.
- EvidenceRef can identify a page/bbox, data selector, or metric path.
- Lineage nodes carry schema/content identity and producer run context.

### 2.5 Market constraints

- Formal G1 research enables daily frequency only.
- Commodity-futures job creation requires exchange scope, actual-contract
  selection, settlement clock, and immutable roll-policy reference.
- Initial market and instrument defaults are frozen in the G0 baseline.
- Five-minute research remains disabled pending license, data, and golden-set
  approval.

## 3. Authoritative artifacts

- `docs/architecture/g0-contract-baseline.md`
- `docs/ui/control-plane-mock/openapi.yaml`
- `tests/contracts/test_control_plane_openapi.py`
- `docs/ui/g0-product-ux-spec.md`
- `docs/ui/page-acceptance-checklist.md`
- `docs/ui/dependencies-and-unknowns.md`
- `docs/reports/2026-08-11-g0-backend-baseline.md`

The architecture baseline and OpenAPI contract take precedence where older
design prose remains ambiguous.

## 4. Verification evidence

### Engineering checks

```text
ruff format --check: passed, 12 files formatted
ruff check: passed
mypy: passed, 10 source files
pytest: passed, 15 tests
```

The test total contains:

- 4 backend configuration and health tests.
- 11 Control Plane contract tests.

The contract tests cover:

- duplicate YAML key rejection;
- OIDC/Bearer security;
- authenticated actor derivation;
- idempotency and optimistic concurrency;
- safe object authorization responses;
- daily-only G0 scope and futures requirements;
- ResearchBrief version/freeze endpoints;
- independent state machines;
- candidate research constraints;
- report and lineage provenance;
- immutable package payload and separate attestation;
- mandatory snapshot refetch after reconnect.

### OpenAPI and fixtures

```text
Redocly: 0 errors, 23 warnings
JSON fixture parsing: passed
git diff --check: passed
```

The remaining Redocly warnings are non-blocking:

- the server is intentionally a localhost mock;
- some P0 operations do not yet enumerate a generic 4XX response;
- P1 schemas frozen at G0 are intentionally not referenced by P0 endpoints;
- the proprietary license has no public URL/identifier.

### Local infrastructure

```text
docker compose config --quiet: passed
docker compose --profile orchestration --profile tracking config --quiet: passed
```

The previously completed runtime smoke test confirmed healthy PostgreSQL,
MinIO, migrations, and FastAPI using alternate host ports because host port
5432 was occupied.

## 5. Gate decision

Gate G0 is approved for G1 engineering work because:

- product scope and P0/P1 UI boundaries are consistent;
- the two initial market domains and daily-frequency boundary are explicit;
- domain identities, lifecycle boundaries, and state ownership are frozen;
- security, errors, events, idempotency, and concurrency are testable;
- local infrastructure is reproducible and Docker-managed;
- UI development can proceed from a validated mock contract;
- unresolved external decisions cannot be bypassed by implementation.

## 6. Explicit non-approvals

Gate G0 does not approve:

- any production market-data supplier;
- any data license or raw-data retention right;
- any broker, CTP version, account, credential, or production network;
- any formal dataset snapshot built from an unaccepted source;
- five-minute formal research;
- any paper or live publication;
- any live actor, permission, limit, or kill-switch recovery decision.

These remain hard gates and require evidence, golden-set results, and human
approval in later phases.

## 7. G1 entry scope

G1 may proceed in parallel on:

1. Domain persistence and Control Plane API foundations.
2. Market/data contracts and golden-set harnesses for both market domains.
3. OIDC/RBAC, audit, idempotency, outbox, error, and event foundations.
4. Frontend shell and a mock-driven ResearchJob/ResearchBrief vertical slice.

G1 integration must verify generated client compatibility, migration
reversibility, state transition authorization, event replay/idempotency, and
market-specific contract tests before Gate G1.
