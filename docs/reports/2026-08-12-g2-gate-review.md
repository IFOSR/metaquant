# G2 Integration Gate Review

**Date:** 2026-08-12

**Run:** `run_0042c74363d5`

**Decision:** `GO_FOR_G3_RESEARCH_EXECUTION_FOUNDATION_WITH_EXTERNAL_PRODUCTION_GATES_BLOCKED`

## 1. Scope reviewed

Gate G2 integrated and reviewed:

- Factor IR v1 compilation kernel.
- Point-in-time Data Gateway domain and representative market adapters.
- PostgreSQL audit, outbox, consumer deduplication, idempotency, and atomic
  ResearchJob command persistence.
- A real frontend HTTP client seam aligned with the P0 ResearchJob and
  ResearchBrief API.

The implementation remains limited to `CN_A` and
`CN_COMMODITY_FUTURES`. Formal frequency remains `1d`.

The first G2 frontend worker terminal started but did not consume its dispatch.
The main agent stopped that inactive worker and completed the same bounded task
in the shared worktree using test-driven development. No backend, Factor IR,
PIT, or Alembic scope was changed by that takeover.

## 2. Delivered baseline

### 2.1 Factor IR v1

- Closed schema, restricted AST, and immutable operator registry.
- Canonical JSON and deterministic SHA-256 identity.
- Static type, unit, lookback, available-time, and market-scope validation.
- Rejection of negative lag, forward/backfill, LabelSeries, unbounded windows,
  arbitrary UDF/eval, and file, network, shell, or database IO.
- Daily `CN_A` and fully declared `CN_COMMODITY_FUTURES` scopes only.
- Six pinned representative classic-factor compilation cases.

Factor IR does not calculate returns and is not yet an execution runtime.

### 2.2 PIT Data Gateway

- Frozen-snapshot-only formal queries.
- Enforcement of `available_time <= decision_time`.
- Revision selection, license/purpose enforcement, and exploratory/formal
  separation.
- Future-truncation invariance and future-sentinel isolation.
- Representative A-share historical membership/status and commodity-futures
  actual-contract-chain adapters.

The adapters are deterministic in-memory references. No production data
supplier or licensed historical dataset is selected.

### 2.3 PostgreSQL control-plane delivery

- Reversible Alembic revisions through `20260812_0004`.
- PostgreSQL-backed AuditStore, OutboxStore, ConsumerDeduplicator, and
  IdempotencyStore.
- ResearchJob creation writes the domain record, command receipt, AuditEvent,
  and outbox event in one transaction.
- ResearchBrief create, update, and freeze write domain state, command receipt,
  AuditEvent, and outbox event in one transaction.
- Brief row locks prevent concurrent PATCH/PATCH and PATCH/freeze lost updates.
- PostgreSQL advisory transaction locks serialize competing uses of the same
  idempotency key.
- ResearchJob project scope is persisted and authorized server-side.
- Same-key/same-payload replay returns the original receipt without adding
  records.
- Injected pre-commit failure rolls back every record.
- Consumer processing commits its domain effect and deduplication receipt in
  the same transaction; unsafe pre-processing claim semantics are rejected.

### 2.4 Frontend real API seam

- `QuantApiClient` is the only interface used by pages and components.
- Deterministic mock and real HTTP adapters implement the same contract.
- Explicit snake_case DTO to camelCase UI mappers.
- Bearer, `Idempotency-Key`, strong `ETag`/`If-Match`, command receipt
  follow-up GET, and `application/problem+json` handling.
- Brief evidence references and uncertainties survive read/update round trips.
- Browser requests use a same-origin Next.js proxy; Bearer remains server-side.
- The proxy is restricted to the current P0 ResearchJob and ResearchBrief
  paths, accepts loopback request origins only, and does not expose execution,
  PAPER, or LIVE APIs.
- Real-data pages are force-dynamic and cannot freeze build-time API snapshots.
- Job detail selects the latest ResearchBrief version rather than relying on
  response ordering.

The proxy uses a local shared test Bearer and is not a production identity
architecture. It is limited to a localhost, single-user demonstration.
Production OIDC remains blocked.

## 3. Verification evidence

### 3.1 Python, contracts, Factor IR, and PIT

```text
$ make check
65 files already formatted
All checks passed!
Success: no issues found in 60 source files
163 passed
```

The 163 tests include:

- Factor IR compiler, schema, golden, and closed-postprocess tests.
- PIT Data Gateway and fail-closed market-status tests.
- 11 OpenAPI contract tests.
- PostgreSQL control-plane store, transactional command, concurrency, and
  consumer-deduplication tests.

Targeted verification also passed:

```text
OpenAPI contracts: 11 passed
Full Python suite: 163 passed
```

### 3.2 PostgreSQL 16 migration and atomicity

An isolated database `quant_gate_g2_remediation` on the Compose-managed
PostgreSQL 16 service completed:

```text
upgrade through 20260812_0004
downgrade 20260812_0004 -> 20260812_0003
upgrade 20260812_0003 -> 20260812_0004
current: 20260812_0004 (head)
```

The real PostgreSQL atomicity and concurrency smoke reported:

```text
ResearchJob: +1
ResearchCommandReceipt: +1
AuditEvent: +1
OutboxEvent: +1
same command replay: all counts unchanged
injected failure: all counts unchanged
PATCH/PATCH: one success, one STALE_OBJECT_VERSION:2
PATCH/freeze: one success, one STALE_OBJECT_VERSION:2
same idempotency key: same command receipt, one mutation
```

Host port `5432` was occupied, so Gate verification explicitly used
`POSTGRES_PORT=55432`. PostgreSQL remained Docker Compose managed.

### 3.3 Frontend

```text
$ npm test
31 passed
$ npm run lint
passed
$ npm run typecheck
passed
$ npm run build
passed
```

The HTTP-mode production build emitted dynamic routes for overview, job list,
job detail, brief detail, and the same-origin API proxy.

### 3.4 Runtime end-to-end

Compose PostgreSQL, MinIO, migrations, and FastAPI reached healthy state.
`/health/ready` returned PostgreSQL and MinIO as `ok`.

Through the production Next.js same-origin proxy:

- ResearchJob create returned an accepted command receipt.
- Authoritative GET returned strong ETag `"1"`.
- ResearchBrief create, GET, PATCH, and freeze succeeded.
- Final brief state was `FROZEN`, resource version was `3`, and a SHA-256
  content hash was present.
- Brief evidence IDs and uncertainties survived the real HTTP update and freeze
  flow.
- Overview, job list, job detail, and brief pages all returned HTTP 200.
- The created job remained `RESEARCH`, `CN_A`, and `1d`.
- A non-loopback proxy request was rejected with HTTP 403 and
  `LOCAL_DEMO_PROXY_ONLY`.
- PAPER and LIVE remained disabled.

## 4. Independent-review remediation

An independent review found blocking defects after the first verification
pass. Each actionable G2 defect was remediated and reverified:

- Authorization now preserves exact capability, project, market, and operation
  scope. V1 fixes the project to server-controlled `local`, and read, write,
  and freeze capabilities are distinct.
- ResearchBrief create, update, and freeze now have atomic domain, receipt,
  audit, and outbox persistence. Row and advisory transaction locks close
  object-version and idempotency races.
- Frontend mapping preserves evidence IDs and uncertainties across update
  round trips.
- The same-origin proxy is restricted to P0 research paths and loopback request
  origins; the shared token is documented as localhost-only demo
  infrastructure.
- Factor IR postprocessing is a closed pipeline. Only `winsorize`, `zscore`,
  and `cs_rank` are accepted, and unsupported fields, operators, arguments, or
  exposures fail closed.
- PIT A-share queries fail closed when security status is missing or was not
  available by decision time; they no longer assume `NORMAL`.
- Consumer deduplication commits the processing effect and receipt together,
  and PostgreSQL claim-before-processing behavior is rejected.
- The frontend selects the latest Brief version explicitly.

One architectural integration item is intentionally G3 entry scope rather than
an unimplemented G2 remediation: Factor IR and PIT Gateway are not yet wired
into end-to-end ResearchJob execution.

The following are deliberately not represented as complete:

- No ResearchJob execution path yet binds a frozen ResearchBrief, frozen PIT
  snapshot, compiled Factor IR, and versioned computation/validation artifact.
- Factor IR is not connected to a formal computation engine.
- PIT Gateway uses representative in-memory adapters, not accepted production
  suppliers or licensed data snapshots.
- No factor evaluation, multiple-testing control, portfolio construction,
  formal backtest, paper runtime, or live runtime is implemented.
- No production OIDC issuer, token exchange, session endpoint, or user-scoped
  browser authentication is approved.
- The frontend same-origin proxy is local-development infrastructure only.
- No broker, CTP production account, credential, network, or trading
  attestation is approved.
- NautilusTrader is not yet integrated as the formal backtest or execution
  runtime.
- Vibe Trading and TradingAgents remain untrusted proposal adapters.
- QuantDinger remains optional and disabled.
- No PAPER or LIVE capability is enabled.

## 5. Gate decision

G2 is complete for the bounded research foundation. G3 may start with
`ResearchJob -> frozen ResearchBrief -> frozen PIT snapshot -> Factor IR ->
versioned computation/validation artifact` as its first integration milestone.
G3 must not claim a formal research execution pipeline until that chain is
implemented and tested end to end.

G3 must preserve:

- no arbitrary Python, eval, SQL, shell, network, or file IO in Factor IR;
- snapshot-only PIT access;
- `CN_A` and `CN_COMMODITY_FUTURES` market constraints;
- formal `1d` frequency only;
- PostgreSQL transaction, audit, outbox, idempotency, and ETag semantics;
- explicit proposal-adapter distrust boundaries;
- production data, OIDC, broker/CTP, PAPER, and LIVE hard gates.
