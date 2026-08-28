# MetaQuant · Containerized Quant Research Platform

**English** · [简体中文](./README.zh-CN.md)

> Turn a trading idea — in plain language, a paper, or a formula — into a **verifiable factor**, a **reproducible strategy**, and an **auditable trading package** — all behind one `./quant` command.

**MetaQuant** is a local-first, end-to-end quantitative research and trading platform for the Chinese markets (`CN_COMMODITY_FUTURES`, `CN_A`). It pairs an LLM-driven research workbench with a deterministic, market-realistic backtest/simulation kernel so that the strategy you *chat into existence* is the same one you *audit*, *simulate*, and *replay*.

```text
Idea / Paper / Formula
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  Research Workbench (LLM agents, auditable, evidence-led)│
│   • NL → NautilusTrader strategy    • factor 从研报构建   │
│   • Point-in-time data, no look-ahead / survivorship     │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Deterministic Kernel (same strategy package everywhere) │
│   • Market-realistic backtest (real CN fees & rules)     │
│   • Paper simulation venue (full order lifecycle)        │
│   • Versioned, content-addressed, replayable             │
└─────────────────────────────────────────────────────────┘
```

---

## Why MetaQuant

Quant research is usually a swamp: LLMs write plausible-looking strategy code that can't be audited, backtests silently use future data, A-share T+1 and futures contract lifecycle are modeled like stocks, and the backtest never matches live. MetaQuant attacks each of those head-on.

- **One command, no Python hell.** Everything runs in Docker (Python 3.12, CPU PyTorch). Docker checks → Postgres/MinIO → backend → frontend with a single `./quant`.
- **Natural-language to auditable code.** Describe your entry/exit in plain Chinese/English; the agent turns it into a NautilusTrader strategy, code-tests it, and runs a deterministic, hashed backtest you can revisit.
- **Market-realistic, not toy results.** Chinese futures venue models (fee model, price-limit fill model), contract lifecycle, roll policy, daily settlement; A-share T+1 + price bands + stamps. Point-in-time data blocks look-ahead; snapshot-based universes block survivorship bias.
- **Same strategy package everywhere.** Backtest → paper simulation → live use one artifact, so what you validated is what you trade — no semantic drift between engines.
- **Evidence-first & auditable.** Every conclusion carries its snapshot, strategy, and lineage. Gates, kill switch, ordering anomaly detection, reconciliation — built for research leads and risk/compliance, not just quants.
- **LLM-backend-agnostic.** Configure which CLI agent (`codex` / `pi`) and which **provider** supplies the base model. Providers are independent, global entities with auto-fetched model catalogs; `codex` maps to OpenAI-compatible endpoints, `pi` to everything.

---

## Core Capabilities

### 1 · Natural-Language → Strategy
On the **New Research** page, describe a rule ("5-day MA over 20-day MA, long; exit on close below 10-day low"). The agent clarifies intent, writes the NautilusTrader strategy, runs a code test, and produces a backtest with a deterministic content hash. Reopen any historical run from the workbench history and see the exact same equity curve.

### 2 · Backtest Workbench
Pick a frozen study, tune frequency (`1d` / `5m` / …) and date range, and run against the NautilusTrader engine. Get total return, Sharpe, max drawdown, trade count, an annotated equity curve (buy/sell markers), position round-trips with realized PnL, and per-fill fees. Every run is keyed by a backtest hash so results are reproducible and comparable.

### 3 · Factor Construction from a Paper
Upload a research paper (or paste an idea) and the agent extracts a factor build-spec → generates `model`/`train`/`infer` code → runs it in a sandbox (AST-scanned subprocess locally, or a hardened `--network=none` Docker sandbox in production) → trains/infers factor values → validates IC. An 8-step, gated pipeline with full lineage.

### 4 · Paper Simulation Trading
Freeze a strategy → a content-addressed artifact is published → a persistent NautilusTrader node opens a simulated account. Orders traverse the full lifecycle on a simulated venue that charges **Chinese-market fees**. Daily net-value reconciliation, order/position/equity views, and a global kill switch.

### 5 · Research Jobs & Market Boundary
Every run starts inside a versioned brief with an explicit **market boundary**: universe reference, decision/trade/settlement clocks, exchange scope, contract selection, roll policy. Formal research fields are pinned (declarative, machine-readable), while strategy logic stays conversational.

### 6 · Agent & Base-Model Configuration
Choose the LLM agent (`codex` / `pi`) and which **provider** (OpenAI, DeepSeek, Kimi, OpenRouter, Anthropic, Google, or a custom OpenAI-compatible endpoint) supplies the base model. Providers are independent, global entities — configure Base URL + API key once. The model catalog auto-fetches (`/v1/models`), the active agent/model is shown live in the top bar, and everything takes effect immediately.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Data | PostgreSQL, MinIO (content-addressed artifacts) |
| Research/Trading engine | NautilusTrader, custom Chinese venue models |
| ML / factor pipeline | Python 3.12, CPU PyTorch, guarded sandbox |
| LLM agents | `codex` / `pi` CLIs, provider-agnostic, DeepSeek/Zhipu fallback |
| Frontend | Next.js 16, React 19, TypeScript |
| Runtime | Docker + Docker Compose v2 |

---

## Installation

### Prerequisites

- **Docker Desktop** (or a compatible Docker Engine) and **Docker Compose v2**
- **`make`**
- Optional: network access to your LLM provider's API for the agent workbench (otherwise the built-in `deepseek`/`zhipu` fallback applies)

> PostgreSQL and MinIO are managed entirely by Docker Compose. Do **not** install or initialize PostgreSQL on your host.

### Quick start

```bash
# From the repo root — one command brings everything up
./quant
```

This performs the Docker check, then boots Postgres → MinIO → migrations → API → frontend.

Under the hood that is equivalent to:

```bash
make bootstrap
make up
curl --fail http://localhost:8091/health/live      # API live
curl --fail http://localhost:8091/health/ready     # migrations applied
```

### Default endpoints

| Service | URL |
|---|---|
| Web UI | <http://localhost:3090> |
| API / OpenAPI docs | <http://localhost:8091/docs> |
| MinIO API / Console | <http://localhost:9000> / <http://localhost:9001> |
| PostgreSQL | `localhost:55432` |

Local development access token: **`local-researcher`**.

The passwords in `.env.example` are for local development only. After `make bootstrap`, you can edit the untracked `.env` file.

### Common commands

```bash
make check            # ruff format + lint + strict mypy + pytest (inside the 3.12 image)
make g3-integration   # real Postgres/MinIO gate: bump->downgrade->bump, idempotency, content-addressing
make logs
make down             # stop, keep data
make reset            # delete all local named volumes (destructive — only when you're sure)
```

---

## Usage Walkthrough (5 minutes to a reproducible backtest)

1. **Open** <http://localhost:3090> → **New Research** (`/research/new`).
2. **Describe** a rule and send it. The agent turns it into a strategy, tests the code, and freezes it.
3. Open **Backtest** (`/backtest`), pick the frozen study, set frequency/range, and **Run**.
4. Review total return / Sharpe / max drawdown / equity curve / trades / positions.
5. Freeze the strategy and **open a paper account** on the **Paper** page — orders flow through a simulated Chinese-market venue with daily reconciliation.

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│  Workbench Shell (Next.js topbar: active agent + base model)   │
│    New Research │ Research Jobs │ Strategy │ Backtest │ Paper  │
└───────────────┬───────────────────────────────────────────────┘
                │  /v1 REST (Bearer token) via a local proxy
┌───────────────▼───────────────────────────────────────────────┐
│                          FastAPI                               │
│  strategy_generation · agent_config · factor_construction      │
│  research (PIT, snapshots, gates) · paper (sim venue, ledger)  │
└───────┬───────────────────────────────────┬───────────────────┘
        │                                   │
 ┌──────▼──────┐                     ┌──────▼──────┐
 │ PostgreSQL  │                     │    MinIO    │
 │ (config,    │                     │ (artifacts, │
 │  briefs,    │                     │  snapshots, │
 │  lineage,   │                     │  paper lets │
 │  agent cfg) │                     │  packages)  │
 └─────────────┘                     └─────────────┘
```

Key design invariants:

- **Point-in-time (PIT)** data access with **time-type checks** — unprovable factors are blocked at the source.
- **Deterministic backtesting** keyed by a content hash — same inputs, same equity curve, reproducible forever.
- **One strategy package** flows through backtest → paper → live.
- **Market rules are a single source of truth** (`markets/`), not copy-pasted assumptions.
- **Evidence-led execution**: every result carries snapshot, strategy, and lineage; gates + kill switch guard the path to paper/live.

The product vision and deeper design live in `doc/quant-platform-prd.md`, `doc/integrated-quant-pipeline-design.md`, and `doc/quant-platform-technical-design.md`.

---

## Repository Layout

```
quant/
├── src/quant_platform/         # backend: api, research, strategy_generation,
│                               # factor_construction, paper, markets/nt, agent_config
├── frontend/                   # Next.js workbench (app, components, lib, styles)
├── alembic/                    # versioned database migrations
├── doc/  docs/plans/           # PRD, technical design, implementation plans
├── scripts/                    # ingest, verify, sandbox, live-feed helpers
├── docker/                     # Dockerfiles (api, sandbox), postgres init
├── tests/                      # pytest suites (unit + integration/gates)
├── compose.yaml                # api, postgres, minio, migrate, paper/live profiles
└── quant  Makefile             # one-command dev entrypoint + task runner
```

---

## Why choose MetaQuant over a notebook or an ad-hoc script?

| You care about | MetaQuant |
|---|---|
| Getting a local dev env up fast | `./quant`, Docker, no host Python deps |
| Not fooling yourself in backtests | PIT data + time-type checks + real CN fees & rules |
| Trusting LLM-generated strategies | audited code, code-test gate, deterministic hashed backtests |
| Reproducing a result months later | hashed runs + versioned briefs + content-addressed artifacts |
| Matching paper to live | one strategy package across backtest / sim / live |
| Explaining to a research lead / risk | evidence-first snapshots, lineage, gates, kill switch, reconciliation |

---

## License

[`LICENSE`](./LICENSE) — see the file for details.

---

## Contributing

Pull requests are welcome. Run `make check` (ruff + mypy + pytest in the 3.12 image) before submitting. For larger changes, start from an implementation plan in `docs/plans/`.

**Star the repo** if MetaQuant helps you stop lying to yourself in quant research ⭐
