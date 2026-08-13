# G0 Frontend Deliverables Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Freeze the G0 frontend information architecture, P0 research flow, interaction states, and Control Plane mock contract without changing backend design documents.

**Architecture:** Deliver documentation-first artifacts under `docs/ui` because the repository has no frontend runtime and the Control Plane API is not yet frozen. Keep all frontend data access behind a versioned OpenAPI mock contract, and mark proposed endpoints separately from endpoints already named by the technical design.

**Tech Stack:** Markdown, OpenAPI 3.1 YAML, JSON fixtures, shell-based validation.

---

### Task 1: Freeze information architecture

**Files:**
- Create: `docs/ui/g0-product-ux-spec.md`

**Step 1:** Map every PRD role to its core tasks and least-privilege navigation.

**Step 2:** Define global navigation, market/environment context, and P0/P1 page boundaries.

**Step 3:** Document the ResearchJob-to-report happy path and recovery paths.

### Task 2: Freeze interaction behavior

**Files:**
- Modify: `docs/ui/g0-product-ux-spec.md`

**Step 1:** Define loading, empty, error, permission, stale, and long-running behavior.

**Step 2:** Specify approval, waiver, lockbox, publish, cancel, retry, and kill-switch interactions.

**Step 3:** Add desktop, mobile, keyboard, screen-reader, chart, and reduced-motion requirements.

### Task 3: Create the mock contract

**Files:**
- Create: `docs/ui/control-plane-mock/openapi.yaml`
- Create: `docs/ui/control-plane-mock/examples/research-job.json`
- Create: `docs/ui/control-plane-mock/examples/research-job-events.json`
- Create: `docs/ui/control-plane-mock/examples/research-report.json`
- Create: `docs/ui/control-plane-mock/examples/problem.json`
- Create: `docs/ui/control-plane-mock/README.md`

**Step 1:** Model the P0 read/write APIs and standard write headers.

**Step 2:** Add representative long-running, report, lineage, and error fixtures.

**Step 3:** Mark API additions that require backend confirmation.

### Task 4: Package and verify

**Files:**
- Create: `docs/ui/README.md`
- Create: `docs/ui/page-acceptance-checklist.md`
- Create: `docs/ui/dependencies-and-unknowns.md`

**Step 1:** Document how to inspect and validate the artifacts.

**Step 2:** Add page-level acceptance criteria and backend dependencies.

**Step 3:** Validate JSON fixtures, inspect the diff, and confirm the three source design documents are unchanged.
