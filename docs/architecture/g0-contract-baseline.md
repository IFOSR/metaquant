# G0 Architecture and Contract Baseline

**Status:** Approved for G1 implementation

**Date:** 2026-08-11

**Applies to:** `CN_A` and `CN_COMMODITY_FUTURES`

This document is the G0 decision record for implementation. Where the PRD,
integrated design, technical design, or UI draft conflicts with this baseline,
this document and `docs/ui/control-plane-mock/openapi.yaml` take precedence
until the source documents are revised.

## 1. G0 outcome

G0 approves the engineering baseline and the contracts needed to start G1.
It does not approve a production data vendor, broker, CTP production account,
paper deployment, live deployment, or any live credential.

G1 may implement:

- Docker-managed PostgreSQL and MinIO integrations.
- Control Plane authentication and authorization seams.
- ResearchJob and versioned ResearchBrief persistence.
- MarketDefinition, DatasetContract, DatasetSnapshot, TradingRuleVersion, and
  RuleSetSnapshot schemas.
- CN A-share and commodity-futures golden-set harnesses.
- OpenAPI-generated clients and the first P0 UI vertical slice.

G1 must not implement a shortcut that treats an Agent platform, a public data
API, or a broker's current instrument query as the system of record.

## 2. Platform composition

The product is not a fixed sequence of Vibe Trading, TradingAgents,
QuantDinger, and NautilusTrader.

- The self-built Control Plane, PIT Data Gateway, Factor IR, validation gates,
  registries, audit log, and release controls form the authoritative pipeline.
- Vibe Trading and TradingAgents are optional upstream proposal adapters.
  Their outputs are untrusted `CandidateProposal`, `ResearchProposal`,
  `RiskMemo`, or exploratory artifacts.
- QuantDinger remains disabled by default and may only be evaluated behind an
  optional POC adapter.
- NautilusTrader is the default deterministic runtime for formal backtests and
  later paper/live execution. It consumes normalized data, rule snapshots, and
  approved release artifacts; it does not own PIT data or research decisions.

No adapter may write `GateDecision`, Alpha Pool membership, package
attestations, deployment state, or orders directly.

## 3. Domain boundaries

The minimum bounded contexts are:

| Context | Owned facts |
|---|---|
| Identity and Access | principal, role binding, scoped capability, session |
| Research Intake | ResearchJob, ResearchBriefVersion, evidence, candidates |
| Factor Registry | FactorSpec, FactorVersion, CompiledIR, operator versions |
| Data Governance | DatasetContract, DatasetSnapshot, TradingRuleVersion, RuleSetSnapshot |
| Experiment and Validation | ExperimentSpec, ExperimentRun, Attempt, ValidationBundle, GateDecision |
| Alpha Governance | AlphaPoolVersion, AlphaPoolEntry |
| Strategy Research | StrategySpecVersion, StrategyBuildArtifact, BacktestRun |
| Release | StrategyPackagePayload, PackageAttestation, Approval |
| Execution | DeploymentRun, runtime instance, order, fill, ledger, reconciliation, kill switch |
| Audit and Lineage | AuditEvent, artifact manifest, lineage edge |
| Agent Gateway | proposals, risk memos, LLM traces |

Cross-context references must identify an immutable version or content hash.
`latest` references are forbidden in formal runs and releases.

## 4. Independent state machines

A single end-to-end `ResearchState` is rejected. The v1 state machines are:

```text
ResearchJob
DRAFT -> READY -> RUNNING -> SUCCEEDED | FAILED | CANCELLED -> ARCHIVED
                   |-> WAITING_INPUT | BLOCKED_POLICY

ResearchBriefVersion
DRAFT -> FROZEN -> SUPERSEDED

ExperimentSpec
DRAFT -> PREREGISTERED -> SUPERSEDED | CLOSED

ExperimentRun
QUEUED -> RUNNING -> SUCCEEDED
                  -> FAILED_RETRYABLE | FAILED_TERMINAL
                  -> WAITING_INPUT | BLOCKED_POLICY
                  -> QUARANTINED | NON_REPRODUCIBLE | CANCELLED

Attempt
QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED | TIMED_OUT

Replication
DRAFT -> RUNNING -> REPRODUCED | NON_REPRODUCIBLE | FAILED -> CLOSED

PackageRelease
DRAFT -> PENDING_APPROVAL -> APPROVED | REJECTED -> REVOKED

DeploymentRun
PENDING -> STARTING -> RUNNING -> PAUSED | STOPPING -> STOPPED
                              -> FAILED | KILLED
```

The UI may render a derived stage timeline, but it must not persist or infer a
new authoritative state.

## 5. Strategy build and release order

The circular dependency between formal backtest and StrategyPackage is
resolved as follows:

```text
AlphaPoolVersion
  -> StrategySpecVersion
  -> immutable StrategyBuildArtifact
  -> formal BacktestRun consumes StrategyBuildArtifact
  -> immutable StrategyPackagePayload references the accepted BacktestRun
  -> PackageAttestation approves the payload hash for PAPER or LIVE
  -> DeploymentRun consumes payload hash plus a currently valid attestation
```

Approval is not a mutable field inside `StrategyPackagePayload`. Revocation or
environment-specific approval creates or changes an attestation without
changing the package payload hash.

## 6. Immutable version rules

- A frozen `ResearchBriefVersion` cannot be edited.
- A formal experiment only references a `PREREGISTERED` ExperimentSpec.
- A formal run only references `SEALED` DatasetSnapshot and RuleSetSnapshot
  versions.
- Factor changes create a new FactorVersion; referenced versions are never
  overwritten.
- GateDecision binds the experiment run, factor version, validation bundle
  hash, policy version, evidence, and resource version.
- AlphaPoolVersion and StrategySpecVersion contain explicit member versions.
- StrategyPackagePayload uses canonical JSON and SHA-256 content identity.
- Package approval, rejection, expiry, and revocation are attestations.

## 7. Control Plane contract

The P0 mock contract is
`docs/ui/control-plane-mock/openapi.yaml`.

Security and consistency rules:

- Production authentication is OIDC. Bearer JWT is also defined for service
  and test clients.
- `actor` is derived from the authenticated principal and is never accepted
  from the request body.
- Every mutating operation requires `Idempotency-Key`.
- Mutations of an existing aggregate also require a strong `If-Match` ETag.
- Resource responses expose a monotonic resource version or ETag.
- Object-level authorization may return the same safe `404` response for
  absent and undisclosed objects.
- Errors use `application/problem+json` with stable code, request ID,
  retryability, current version, and field errors.
- Events are authorized hints, not the source of truth. Every reconnect must
  fetch an authoritative GET snapshot before enabling state-dependent writes.
- Schema changes are additive within v1. Breaking changes require a new
  schema version and producer/consumer contract tests.

All state-changing commands append an AuditEvent with authenticated actor,
reason, object versions, request/correlation IDs, policy decision, and
before/after hashes where applicable.

## 8. Approval separation

Research approval, paper approval, and live approval are separate decisions.

- A submitter cannot approve their own protected action.
- Waivers are scoped, time-limited, evidence-backed, and cannot override
  non-waivable safety failures.
- PAPER approval cannot be reused as LIVE approval.
- LIVE requires at least two distinct human actors with separate
  `ResearchLead` and `ExecutionOperator` roles, a matching package hash, fresh
  runtime state, and reauthentication.
- G0 defines these contracts only. It does not enable paper or live actions.

## 9. Initial market scope

### 9.1 Common scope

- Enabled market domains are only `CN_A` and `CN_COMMODITY_FUTURES`.
- Formal G1 research frequency is `1d`.
- Five-minute research remains disabled until data licensing, field
  availability, cost, and market-rule golden sets are approved.
- Each market has independent universe, clocks, rules, cost model, fill model,
  validation policy, and release eligibility.

### 9.2 CN A-share default

- Initial implementation scope is Shanghai and Shenzhen main-board equities.
- CSI 300 and CSI 500 point-in-time membership are target reference universes,
  subject to formal source licensing and history validation.
- Target history begins on 2015-01-01 at daily frequency.
- The default signal clock is after T close; the default execution policy is
  T+1 after open, with the exact fill window stored in a versioned policy.
- Trading uses raw prices and actual corporate actions. Research adjustment
  factors must be point-in-time and versioned.
- T+1, price limits, ST changes, suspensions, delistings, corporate actions,
  historical constituents, fees, and tradability are mandatory golden cases.

STAR, ChiNext, and Beijing Stock Exchange instruments may appear in golden
tests, but are not enabled in the initial formal universe.

### 9.3 CN commodity-futures default

The initial rule and data harness covers:

`AU`, `AG`, `CU`, `RB`, `SC`, `M`, `I`, `PP`, `TA`, `MA`, `SR`, and `LC`.

Every ResearchJob must declare:

- exchange scope;
- actual-contract selection;
- decision, trade, and settlement clocks;
- immutable roll-policy reference;
- no-delivery policy for the initial release.

The default research roll policy is open-interest based with a three-day
confirmation and explicit delivery-risk exit. Its thresholds remain a
versioned policy, not hard-coded runtime constants.

Night-session trade-date assignment, settlement, margin, fees,
close-today/close-yesterday, limits, delivery eligibility, actual-contract
lineage, and future-truncated roll reconstruction are mandatory golden cases.

## 10. External decisions that remain blocked

The following require evidence and human approval in G1 or later:

- selection and licensing of a production A-share or futures data vendor;
- permission to retain immutable raw snapshots and derived data;
- historical PIT/revision and delisted-instrument acceptance results;
- official index-history source and redistribution rights;
- primary and disaster-recovery futures brokers;
- CTP version, AppID/AuthCode, account permissions, and production network;
- account-specific commission, margin uplift, forced-liquidation, and
  delivery controls;
- any paper or live release.

Public aggregators and platform-provided loaders remain exploratory sources
until they pass the same contract, licensing, PIT, and golden-set gates.

## 11. Local infrastructure

- PostgreSQL is the metadata, state, audit, and transactional source of truth.
- MinIO stores immutable artifacts, manifests, reports, and large outputs.
- Large market data and factor matrices are not stored as PostgreSQL blobs.
- PostgreSQL and MinIO run under Docker Compose; PostgreSQL is not installed
  as a separately managed host service.
- Dagster and MLflow remain optional profiles until their owning G1 tasks.

## 12. G0 verification

G0 is considered implementation-ready when:

- backend format, lint, type, and test checks pass;
- Compose configuration and migrations validate;
- OpenAPI has no duplicate keys and passes Redocly structural validation;
- contract tests enforce authentication, actor derivation, idempotency,
  optimistic concurrency, market constraints, state separation, provenance,
  immutable package payloads, and reconnect recovery;
- UI flow and acceptance documents use this baseline;
- production vendor, broker, and live choices remain explicitly unapproved.
