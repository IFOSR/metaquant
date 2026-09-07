# Import Backtest Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a strategy conversation select one recorded backtest and send its verified result as context to the Agent for optimization analysis.

**Architecture:** The frontend sends only a selected `backtest_hash`. The backend verifies that the hash belongs to the current draft, replays the existing immutable backtest endpoint logic, formats a bounded context block, and persists the reference with the user message. The frontend renders the same reference in the composer and conversation history.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy JSON message metadata, Next.js 16, React 19, TypeScript, Vitest, pytest.

---

### Task 1: Define the backtest-reference contract

**Files:**
- Modify: `src/quant_platform/strategy_generation/schemas.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Test: `tests/strategy_generation/test_api.py`
- Test: `frontend/test/api-client.test.ts`

**Step 1: Write the failing backend test**

Add a request test showing that `POST /strategy-drafts/{id}/messages` accepts one optional `backtest_hash` and that the returned draft message includes a persisted backtest reference.

**Step 2: Run the backend test to verify it fails**

Run:

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py -k backtest_context_contract
```

Expected: FAIL because `PostStrategyMessageCommand` rejects or ignores `backtest_hash`.

**Step 3: Write the failing frontend client test**

Add a client test asserting `postStrategyMessage(draftId, message, attachments, backtestHash)` sends `backtest_hash` in the JSON body and maps a `kind: "backtest"` message attachment.

**Step 4: Run the frontend test to verify it fails**

Run:

```bash
cd frontend && npm test -- api-client.test.ts
```

Expected: FAIL because the client method and attachment type do not support the reference.

**Step 5: Implement the minimal contract**

- Add `backtest_hash: str | None = None` to `PostStrategyMessageCommand`.
- Extend the internal/public attachment shape with `kind: "backtest"` and optional `backtest_hash`.
- Extend `StrategyAttachment`, API message types, and client mapping.
- Keep `CreateStrategyDraftCommand` limited to normal text/image attachments.

**Step 6: Run both tests**

Run the commands above. Expected: PASS.

**Step 7: Commit**

```bash
git add src/quant_platform/strategy_generation/schemas.py frontend/lib/types.ts frontend/lib/api.ts tests/strategy_generation/test_api.py frontend/test/api-client.test.ts
git commit -m "feat: add backtest reference message contract"
```

### Task 2: Extract reusable historical backtest resolution

**Files:**
- Modify: `src/quant_platform/strategy_generation/api.py`
- Test: `tests/strategy_generation/test_api.py`

**Step 1: Write failing tests**

Add tests covering:

- A valid hash belonging to the draft is replayed through the backtest service.
- A hash belonging to another or nonexistent history entry is rejected.
- Replay errors return a problem response and do not call the Agent runner.

Use a mock backtest service with a complete payload containing metrics, venue spec, trades, positions, and equity curve.

**Step 2: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py -k "backtest_reference or imported_backtest"
```

Expected: FAIL because message posting has no reference validation or replay path.

**Step 3: Implement the resolver**

Extract the existing `get_strategy_backtest_result` history lookup and replay logic into a private helper that:

- Receives the draft and `backtest_hash`.
- Finds the matching history entry.
- Resolves stored start/end/frequency with the same defaults as the existing GET endpoint.
- Calls `backtest_service.run`.
- Raises the existing problem/not-found errors consistently.

Make the GET endpoint and message endpoint reuse this helper so replay semantics cannot diverge.

**Step 4: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py -k "backtest_reference or imported_backtest"
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/quant_platform/strategy_generation/api.py tests/strategy_generation/test_api.py
git commit -m "feat: validate and replay imported backtests"
```

### Task 3: Build a bounded Agent backtest context

**Files:**
- Create: `src/quant_platform/strategy_generation/backtest_context.py`
- Modify: `src/quant_platform/strategy_generation/api.py`
- Test: `tests/strategy_generation/test_backtest_context.py`

**Step 1: Write failing formatter tests**

Test that the formatter includes:

- Result hash, instruments, market/venue, frequency, date range, and fee basis.
- Metrics and total fees.
- Directional trade actions, with a fallback derived from `side` for old results.
- Position round-trips and realized PnL.
- Ordered equity-curve samples.

Test that a very large curve is capped to a deterministic maximum sample count and remains chronologically ordered.

**Step 2: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_backtest_context.py
```

Expected: FAIL because the formatter module does not exist.

**Step 3: Implement the formatter**

Create a pure function such as `format_backtest_context(payload, backtest_hash, market)` that returns a clearly delimited text block:

```text
[导入的历史回测结果]
...
[回测结果结束]
```

Use stable field ordering, compact numeric formatting, and deterministic curve downsampling. Do not include strategy source code or unbounded raw JSON.

**Step 4: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_backtest_context.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/quant_platform/strategy_generation/backtest_context.py src/quant_platform/strategy_generation/api.py tests/strategy_generation/test_backtest_context.py
git commit -m "feat: format bounded backtest agent context"
```

### Task 4: Inject and persist the imported result in conversations

**Files:**
- Modify: `src/quant_platform/strategy_generation/api.py`
- Modify: `src/quant_platform/strategy_generation/repository.py`
- Modify: `src/quant_platform/strategy_generation/schemas.py`
- Test: `tests/strategy_generation/test_api.py`
- Test: `tests/strategy_generation/test_repository.py`

**Step 1: Write failing integration tests**

Add tests asserting:

- The runner prompt contains the original user message plus the bounded backtest context.
- The persisted user message includes the backtest reference metadata.
- A message without `backtest_hash` has the old prompt and persistence behavior.
- A failed replay leaves no appended user/assistant turn.

**Step 2: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py tests/strategy_generation/test_repository.py -k "backtest_context or imported_backtest"
```

Expected: FAIL because the post-message endpoint does not resolve or persist the reference.

**Step 3: Implement the message path**

- Validate the reference before calling `run_turn`.
- Build the Agent history from existing messages.
- Append the formatted backtest context to the current user content only for Agent invocation.
- Persist the user message with a `kind: "backtest"` reference containing the hash and display name.
- Keep the assistant response clean; do not persist the entire context as ordinary user text.
- Extend `_attachment_text`/history reconstruction to recognize persisted backtest references without duplicating stale context into normal attachment text.

**Step 4: Run the tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py tests/strategy_generation/test_repository.py -k "backtest_context or imported_backtest"
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/quant_platform/strategy_generation/api.py src/quant_platform/strategy_generation/repository.py src/quant_platform/strategy_generation/schemas.py tests/strategy_generation/test_api.py tests/strategy_generation/test_repository.py
git commit -m "feat: inject imported backtest into strategy chat"
```

### Task 5: Add frontend selection state and API wiring

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/components/strategy-chat.tsx`
- Modify: `frontend/lib/i18n.ts`
- Test: `frontend/test/api-client.test.ts`
- Test: `frontend/test/strategy-chat-backtest-import.test.tsx`

**Step 1: Write failing component tests**

Cover:

- The import button is disabled when there is no current draft or no backtest history.
- The selector lists the current draft’s history with range, frequency, return, drawdown, and trade count.
- Selecting one entry shows a reference chip.
- Selecting another entry replaces the previous one.
- Removing the chip clears the selection.

**Step 2: Run the tests**

```bash
cd frontend && npm test -- strategy-chat-backtest-import.test.tsx api-client.test.ts
```

Expected: FAIL because the import control and state do not exist.

**Step 3: Implement the UI state**

- Add `selectedBacktestHash: string | null`.
- Derive the selected history entry from `draft.backtestResults`.
- Add a small popover/dialog controlled by local state.
- Render a clear reference chip in the composer with a remove action.
- Reset the selection when starting a new chat, changing draft, or successfully sending.
- Do not fetch full results in the browser; only send the selected hash.

**Step 4: Wire the client request**

Update `postStrategyMessage` to accept an optional hash and include `backtest_hash` only when selected.

**Step 5: Run the tests**

```bash
cd frontend && npm test -- strategy-chat-backtest-import.test.tsx api-client.test.ts
```

Expected: PASS.

**Step 6: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts frontend/components/strategy-chat.tsx frontend/lib/i18n.ts frontend/test/api-client.test.ts frontend/test/strategy-chat-backtest-import.test.tsx
git commit -m "feat: select backtest context in strategy chat"
```

### Task 6: Render historical backtest references consistently

**Files:**
- Modify: `frontend/components/strategy-chat.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/styles/globals.css`
- Modify: `frontend/lib/i18n.ts`
- Test: `frontend/test/strategy-chat-backtest-import.test.tsx`

**Step 1: Write failing history-rendering tests**

Assert that a persisted `kind: "backtest"` attachment is displayed as a backtest reference card/chip, while old text/image attachments still render exactly as before.

**Step 2: Run the test**

```bash
cd frontend && npm test -- strategy-chat-backtest-import.test.tsx
```

Expected: FAIL because the current attachment renderer only knows text/image.

**Step 3: Implement rendering**

- Map `backtest_hash` and display metadata from API messages.
- Render a compact non-editable reference with result range/frequency/hash.
- Use localized labels and preserve existing attachment behavior.

**Step 4: Run the test**

```bash
cd frontend && npm test -- strategy-chat-backtest-import.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/components/strategy-chat.tsx frontend/lib/api.ts frontend/styles/globals.css frontend/lib/i18n.ts frontend/test/strategy-chat-backtest-import.test.tsx
git commit -m "feat: render imported backtest references"
```

### Task 7: Wire sending behavior and failure recovery

**Files:**
- Modify: `frontend/components/strategy-chat.tsx`
- Test: `frontend/test/strategy-chat-backtest-import.test.tsx`
- Test: `tests/strategy_generation/test_api.py`

**Step 1: Write failing send tests**

Cover:

- A message sends the selected hash.
- The selected hash clears after success.
- The input and selected reference remain after a rejected/failed request.
- The Agent is not called when the hash is invalid.
- Existing attachment uploads can be sent together with the backtest reference.

**Step 2: Run the tests**

```bash
cd frontend && npm test -- strategy-chat-backtest-import.test.tsx
docker compose run --rm --no-deps api pytest tests/strategy_generation/test_api.py -k imported_backtest
```

Expected: FAIL until send state and backend failure handling are connected.

**Step 3: Implement minimal recovery behavior**

- Capture the selected hash alongside pending attachments before submission.
- Do not clear text or selection until the request succeeds.
- On error, restore the selected reference and keep user input available for retry.
- Preserve current busy/frozen guards.

**Step 4: Run the tests**

Run the same commands. Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/components/strategy-chat.tsx frontend/test/strategy-chat-backtest-import.test.tsx tests/strategy_generation/test_api.py
git commit -m "feat: recover strategy chat after backtest import errors"
```

### Task 8: Full verification and documentation

**Files:**
- Modify: `docs/plans/2026-09-07-import-backtest-context-design.md` only if implementation decisions materially differ
- Test: existing backend and frontend suites

**Step 1: Run focused backend tests**

```bash
docker compose run --rm --no-deps api pytest tests/strategy_generation
```

Expected: all strategy-generation tests pass.

**Step 2: Run backend static checks**

```bash
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps api mypy
```

Expected: both pass.

**Step 3: Run frontend checks**

```bash
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm test
cd frontend && npm run build
```

Expected: all pass.

**Step 4: Inspect the final diff**

```bash
git diff --check
git status --short
```

Confirm no unrelated files were reverted and the request payload never accepts a client-supplied full backtest JSON as trusted context.

**Step 5: Commit any final test-only or documentation adjustments**

```bash
git add docs/plans/ frontend/ src/ tests/
git commit -m "test: verify imported backtest context flow"
```
