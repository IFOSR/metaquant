# G3 Research Execution Foundation Gate Review

**Date:** 2026-08-13

**Run:** `run_deepseek_g3_recovery`

**Decision:** `GO_FOR_G4_WITH_INVARIANCE_EVIDENCE_REMEDIATION_REQUIRED`

## 1. Scope reviewed

Gate G3 integrated and reviewed:

- Immutable experiment, run, attempt, artifact, and lineage contracts.
- A deterministic Factor Executor for the closed Factor IR v1 operator set.
- Content-addressed local/MinIO artifact storage with hash verification.
- Formal execution preconditions binding frozen briefs, sealed snapshots,
  compiled IR identity, market scope, and `1d` frequency.
- PostgreSQL persistence for ExperimentSpec, ExperimentRun, Attempt, artifact
  metadata, and lineage edges.
- A Control Plane command/API seam to preregister and run an experiment.
- A frontend experiment status and artifact-summary view.

The implementation remains limited to `CN_A` and `CN_COMMODITY_FUTURES`.
Formal frequency remains `1d`.

This gate was recovered after a prior agent session interrupted G3-006
independent review and G3-007 gate verification. The worktree had no initial
commit; a baseline commit was created first, then Docker was restored and the
full verification chain was re-run.

## 2. Delivered baseline

### 2.1 Experiment and artifact contracts

- Immutable `ExperimentSpec`, `ExperimentRun`, `Attempt`, computation and
  validation artifacts, lineage edges, state machines, and canonical hashes.
- `ExperimentSpec` is immutable after `PREREGISTERED`; the run lifecycle
  (`QUEUED -> RUNNING -> SUCCEEDED | FAILED_* | BLOCKED_POLICY | QUARANTINED |
  NON_REPRODUCIBLE | CANCELLED`) and attempt transitions are enforced through
  transition methods.
- Canonical run fingerprint over spec hash, IR hash, snapshot identity,
  snapshot manifest hash, code SHA, image digest, dependency lock hash,
  executor version, config hash, and random seed.

### 2.2 Deterministic Factor Executor

- Executes the restricted AST and closed postprocess pipeline
  (`winsorize`, `zscore`, `cs_rank`).
- Deterministic tabular input/output contracts; null/Inf/divide-by-zero/window
  behavior is explicit; no dynamic evaluation or IO.
- Integrity check now verifies the expression chain **and** the full IR hash
  against the canonical document (see remediation R4).

### 2.3 Content-addressed artifact store

- Canonical bytes, SHA-256 addresses, immutable put/get/verify semantics.
- In-memory and MinIO adapters behind one protocol.
- Manifest and lineage-edge payload contracts; collision, corruption,
  overwrite, and missing-object tests.

### 2.4 Research execution integration

- Reversible Alembic revisions through `20260813_0005`.
- PostgreSQL-backed experiment repository, execution coordinator, API, and
  audit/outbox/idempotency.
- Atomic domain state, command receipt, AuditEvent, outbox event, artifact
  metadata, and lineage edges per state-changing command.
- Same-key/same-payload replay returns the original receipt; same-key with a
  different payload is rejected; identical run fingerprints replay without
  recomputation, serialized by a fingerprint advisory lock.
- Artifact bytes are uploaded before metadata commit and verified by SHA-256.

### 2.5 Frontend experiment monitoring

- HTTP/mock client types and mappers for experiment endpoints.
- Experiment status, attempt history, fingerprint, snapshot/IR hashes,
  validation summary, lineage, and failure states on the ResearchJob detail
  flow.
- The panel renders only server-authoritative state and does not expose PAPER
  or LIVE actions.

## 3. Verification evidence

### 3.1 Python quality and unit suite

```text
$ make check (equivalent, with source/tests volume-mounted)
101 files already formatted
All checks passed!
Success: no issues found in 95 source files
211 passed, 2 skipped
```

The 211 tests include the G3 experiment contract/precondition tests, factor
executor contract/executor tests, artifact store tests, and experiment
execution API tests. The 2 skipped tests are G3 infrastructure tests that
require the integration environment (see 3.3).

### 3.2 Frontend

```text
$ npm test       39 passed
$ npm run lint   passed
$ npm run typecheck  passed
$ npm run build  passed
```

### 3.3 G3 infrastructure integration

```text
$ make g3-integration
upgrade through 20260813_0005
downgrade 20260813_0005 -> 20260812_0004
upgrade 20260812_0004 -> 20260813_0005
2 passed
```

An isolated database was created, migrated up, downgraded, and re-upgraded,
and the G3 PostgreSQL/MinIO integration tests passed before cleanup.

## 4. Independent-review remediation

An independent review found eight defects. Five were remediated and
re-verified; three remain as recorded issues (section 5).

### Remediated

- **R1 (NIT)** — `experiment_runtime/__init__.py` and `repository.py` had
  unsorted import blocks. Fixed by reordering imports; ruff now passes.

- **R2 (LOW)** — `frontend/components/experiment-monitor.tsx` rendered a bare
  attempt count (`2`) instead of a unit-qualified `2 attempts`, breaking the
  component test contract and differing from the `N records` / `N edges`
  convention elsewhere. Fixed to `{run.attemptCount} attempts`.

- **R3 (MEDIUM)** — The Factor IR compiler accepted `zero_policy="clip"` for
  `div`/`safe_div`, but the executor silently treated it as `null` (only
  `"zero"` was special-cased). The compiler now rejects `"clip"` so the
  compile-time and execution-time semantics cannot diverge.

- **R4 (MEDIUM)** — `FactorExecutor._check_integrity` verified the
  AST/expression hash chain but never verified that `ir_hash` matched the full
  canonical document, so `postprocess_steps` and `input_aliases` could execute
  unverified. Added a `sha256(canonical_json) == ir_hash` check.

- **R5 (HIGH)** — Commodity-futures `exchange_scope`, `contract_chain_ref`,
  and `roll_policy_ref` were not cross-checked across experiment, job,
  snapshot binding, and IR scope, despite the design requiring them
  fail-closed. Added `EXCHANGE_SCOPE_MISMATCH`, `CONTRACT_CHAIN_MISMATCH`, and
  `ROLL_POLICY_MISMATCH` precondition checks.

## 5. Remaining issues (not remediated in this gate)

- **R6 (HIGH) — Invariance evidence is vacuous.** The executor coordinator
  computes `future_truncation_passed` and `sentinel_isolation_passed` by
  comparing the baseline execution against a second execution over a filtered
  snapshot. Because `_factor_table` already routes every query through
  `PITDataGateway` (which enforces `available_time <= decision_time` and
  projects only the IR-referenced fields), both executions operate on
  identical inputs, so both booleans are always true. The sentinel rows and
  future rows deliberately present in `config/formal-snapshots.json` are not
  actually exercised by these checks. The real no-lookahead guarantee is held
  by the gateway layer, but the `InvarianceEvidence` artifact currently
  presents a false "future-function detected" signal. This must be remediated
  through a design decision (either make the checks genuinely adversarial, or
  remove them and report gateway-level filtering honestly) before G4.

- **R7 (MEDIUM) — `code_sha`/`executor_version` are caller-asserted
  placeholders.** The run fingerprint includes `code_sha`, `image_digest`, and
  `executor_version`, but these are injected from environment variables that
  default to zero placeholders. They are not derived from the code that
  actually runs, so the fingerprint does not yet pin the executing code. This
  requires an architecture decision on how to derive and seal code identity.

- **R8 (LOW) — Attempt/Run state machines are not enforced at construction.**
  Transition validation lives in `transition()` methods; the frozen dataclass
  constructors do not reject an invalid initial state. Normal flows go through
  the repository and transition methods, so this is a defense-in-depth gap
  rather than an exploitable path.

## 6. Gate decision

G3 delivers the first auditable, deterministic research execution vertical
slice. The deterministic executor, content-addressed artifact store, formal
fail-closed preconditions, PostgreSQL transaction/audit/outbox/idempotency
semantics, reversible migration, and frontend experiment monitoring are all
implemented and pass the full verification chain.

The gate passes with one required follow-up: **R6 (invariance evidence
vacuous)** must be remediated before G4 begins, because the `ValidationArtifact`
invariance evidence is a G3-design-mandated deliverable whose current
implementation does not provide the detection it claims. R7 and R8 are recorded
and may be addressed alongside G4 planning.

G3 must preserve:

- no arbitrary Python, eval, SQL, shell, network, or file IO in Factor IR;
- snapshot-only PIT access with `available_time <= decision_time`;
- `CN_A` and `CN_COMMODITY_FUTURES` market constraints;
- formal `1d` frequency only;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics;
- production data, OIDC, broker/CTP, PAPER, and LIVE hard gates.
