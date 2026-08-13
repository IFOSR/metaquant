# G6 Independence, Turnover, and Capacity Implementation Plan

**Date:** 2026-08-13

## Tasks

- **G6-001** — `validation/alpha_pool.py`: `AlphaPoolFactor`, `AlphaPool`,
  `AlphaPoolCatalog` contracts with duplicate/missing fail-closed semantics.
  Tests.
- **G6-002** — `validation/independence.py`: `run_independence_analysis`,
  `IndependenceReport`, cross-sectional correlation, orthogonalized candidate,
  incremental IC, replication flag. Tests.
- **G6-003** — `validation/turnover.py`: `FactorSeries`, `run_turnover`,
  `TurnoverReport` (raw, buffered, half-life). Tests.
- **G6-004** — `validation/capacity.py`: `CapacityModel`, `run_capacity`,
  `CapacityReport` (per-name capacity, AUM curve). Tests.
- **G6-005** — `validation/false_discovery.py`: `run_false_discovery` wiring BH
  FDR, DSR, PBO over a candidate set. Tests. Closes R1.
- **G6-006** — migration `0008`; `assess_independence` command + repository +
  API; integration test. Persist report artifact + ledger entry atomically.
- **G6-007** — read endpoint, minimal independence summary, G6 gate review.

## Verification

Each task: ruff format/check, mypy, pytest green before commit; G6-006 also
`make g3-integration`.
