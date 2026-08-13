# G3 Research Execution Foundation Design

**Date:** 2026-08-12

**Status:** Approved by the G2 gate entry decision

## 1. Objective

G3 delivers the first auditable, deterministic research execution vertical
slice:

```text
ResearchJob
  -> frozen ResearchBriefVersion
  -> preregistered ExperimentSpec
  -> sealed PIT DatasetSnapshot
  -> compiled Factor IR
  -> deterministic Factor Executor
  -> immutable FactorComputationArtifact
  -> immutable ValidationArtifact
  -> ExperimentRun result and lineage
```

This is a research execution foundation, not a complete factor-validation or
trading platform.

## 2. Scope

G3 includes:

- Immutable experiment, run, attempt, artifact, and lineage contracts.
- Content-addressed local/MinIO artifact storage with hash verification.
- A deterministic Factor Executor for the closed Factor IR v1 operator set.
- Formal execution preconditions for frozen briefs, sealed snapshots, formal
  licenses, compiled IR identity, market scope, and `1d` frequency.
- PostgreSQL persistence for ExperimentSpec, ExperimentRun, Attempt, artifact
  metadata, and lineage edges.
- A Control Plane command/API seam to preregister and run an experiment.
- Atomic command receipt, audit, outbox, and state transitions.
- A frontend experiment status and artifact-summary view.
- Deterministic replay proving identical fingerprints produce identical key
  results.

G3 excludes:

- FDR, DSR, PBO, lockbox, Gate 3-5, Alpha Pool, and portfolio construction.
- Formal backtesting, NautilusTrader integration, PAPER, and LIVE.
- Production data suppliers, production OIDC, and broker/CTP connectivity.
- Arbitrary user Python, UDF, SQL, shell, network, or file-system access.
- Automatic tuning after a failed validation.

## 3. Domain Model

`ExperimentSpec` is immutable after `PREREGISTERED`. It binds:

- one frozen ResearchBriefVersion;
- one compiled Factor IR and its content hash;
- one explicit sealed DatasetSnapshot;
- one market and formal `1d` frequency;
- decision time, universe, validation policy reference, random seed, and
  resource budget.

`ExperimentRun` owns the formal run lifecycle:

```text
QUEUED -> RUNNING -> SUCCEEDED
                  -> FAILED_RETRYABLE | FAILED_TERMINAL
                  -> BLOCKED_POLICY | QUARANTINED
                  -> NON_REPRODUCIBLE | CANCELLED
```

Each retry creates an immutable `Attempt`. A run never overwrites an earlier
attempt.

`FactorComputationArtifact` contains canonical factor observations and a
manifest. `ValidationArtifact` contains G3 validation only:

- observation count;
- finite and missing counts;
- coverage ratio;
- deterministic summary statistics;
- PIT/future-sentinel invariance evidence;
- input and output hashes.

It must not claim profitability, factor acceptance, or production readiness.

## 4. Execution Rules

The coordinator fails closed unless all conditions hold:

- ResearchJob is in the server-controlled `local` project and `RESEARCH`
  environment.
- The referenced brief is `FROZEN`.
- The ExperimentSpec is `PREREGISTERED`.
- Snapshot identity is explicit, immutable, formal, and sealed.
- Snapshot market, universe, and license purpose match the experiment.
- Factor IR market, universe, frequency, clocks, and input fields match the
  experiment and snapshot contract.
- Commodity futures include exchange scope, actual contract chain, and roll
  policy references.
- The request is authorized for exact project, market, and operation.

The run fingerprint is canonical SHA-256 over:

```text
experiment_spec_hash
+ factor_ir_hash
+ snapshot_id
+ snapshot_manifest_hash
+ code_sha
+ image_digest
+ dependency_lock_hash
+ executor_version
+ config_hash
+ random_seed
```

Replaying the same fingerprint must reproduce the same computation and
validation hashes. A mismatch marks the run `NON_REPRODUCIBLE`.

## 5. Storage and Transactions

PostgreSQL remains the state and metadata truth source. Large or structured
artifact payloads are content-addressed in MinIO; tests use an in-memory
adapter with identical hash semantics.

Each state-changing command atomically commits:

- domain state;
- idempotency receipt;
- AuditEvent;
- outbox event;
- artifact metadata and lineage edges when applicable.

Artifact bytes are uploaded before metadata commit and verified by SHA-256.
Orphan cleanup is safe because unreferenced content-addressed objects are not
domain truth.

## 6. API and UI

The bounded G3 API adds:

```text
POST /v1/experiments:preregister
GET  /v1/experiments/{experiment_id}
POST /v1/experiments/{experiment_id}:run
GET  /v1/experiment-runs/{run_id}
GET  /v1/experiment-runs/{run_id}/artifacts
```

Mutations require Bearer authentication, `Idempotency-Key`, reason, and
`If-Match` when mutating an existing aggregate.

The frontend adds an experiment panel to ResearchJob detail. It displays
server-authoritative state, attempt history, fingerprint, snapshot/IR hashes,
validation summary, lineage links, and blocked/quarantined/non-reproducible
states. It does not expose PAPER or LIVE actions.

## 7. Verification

Gate G3 requires:

- unit and golden tests for every executor operator used by representative
  factors;
- future truncation and sentinel isolation through the full execution path;
- deterministic replay with identical hashes;
- fail-closed tests for mutable briefs, exploratory snapshots, license
  mismatch, market mismatch, unknown fields, and unregistered operators;
- PostgreSQL migration upgrade/downgrade/upgrade;
- real PostgreSQL atomicity, idempotency, and concurrent-run tests;
- MinIO content hash round trip;
- API and frontend HTTP-mode end-to-end execution;
- full Python and frontend quality gates.

