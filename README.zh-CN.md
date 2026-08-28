# MetaQuant · 容器化量化研究与交易平台

[English](./README.md) · **简体中文**

> 把一句话想法、一篇研报或一个公式，变成**可验证的因子**、**可复现的策略**与**可审计的交易包**——统统藏在一条 `./quant` 命令后面。

**MetaQuant** 是面向中国市场的本地优先、端到端量化研究与交易平台（`CN_COMMODITY_FUTURES` / `CN_A`）。它把「LLM 驱动的研究工作台」和「确定性、贴近市场的回测/仿真内核」拼在一起，让你**聊出来的策略**，和你**审计、仿真、回看的策略**是同一个。

```text
想法 / 论文 / 公式
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  研究工作组（LLM Agent，可审计、证据优先）                │
│   • 自然语言 → NautilusTrader 策略     • 从研报构建因子    │
│   • 时点（PIT）数据，无未来函数 / 无幸存者偏差           │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│  确定性内核（同一策略包处处一致）                          │
│   • 贴近市场的回测（真实中国费率和规则）                   │
│   • 仿真撮合场所（完整订单生命周期）                       │
│   • 版本化、内容寻址、可重放                              │
└─────────────────────────────────────────────────────────┘
```

---

## 为什么选择 MetaQuant

量化研究通常一团糟：LLM 写出的策略代码"看起来像那么回事"却不可审计；回测悄悄用上未来数据；A 股的 T+1 和商品期货的合约生命周期被当成股票来建模；回测和实盘永远对不上。MetaQuant 逐个击破。

- **一条命令，免去 Python 环境折磨。** 全部用 Docker（Python 3.12、CPU 版 PyTorch）。Docker 检查 → Postgres/MinIO → 后端 → 前端，一条 `./quant` 搞定。
- **自然语言 → 可审计代码。** 用中文/英文描述你的买卖条件，agent 把它编译成 NautilusTrader 策略、跑代码测试、跑一个**确定性哈希回测**，之后随时可回看。
- **贴近市场，不是玩具结果。** 中国期货交易所的费率/撮合模型、合约生命周期、移仓规则、每日结算；A 股 T+1、涨跌停、印花税。时点（PIT）数据挡住未来函数；快照式标的池挡住幸存者偏差。
- **处处同一策略包。** 回测 → 仿真 → 实盘用同一个工件，验证的就是要交易的，引擎间零语义漂移。
- **证据优先、可审计。** 每个结论都带快照、策略与血缘；门禁、kill switch、异常订单检测、对账——给研究负责人和风控/合规用，不只是给量化工程师用。
- **LLM 后端可配置。** 选哪个 CLI agent（`codex` / `pi`）、由哪个 **provider** 提供基座模型。provider 是独立、全局的实体，自动拉取模型目录；`codex` 走 OpenAI 兼容端点，`pi` 支持全部。

---

## 核心能力

### 1 · 自然语言 → 策略
在「新建研究」页描述一条规则（如"5 日均线上穿 20 日均线做多，跌破 10 日低点平仓"）。agent 澄清意图、写出 NautilusTrader 策略、跑代码测试、产出带确定性内容哈希的回测。从工作台历史重新打开任意一次运行，看到的净值曲线一模一样。

### 2 · 回测工作台
选一个已冻结的研究，调频率（`1d` / `5m` / …）与区间，跑 NautilusTrader 引擎。拿到总收益率、夏普、最大回撤、成交次数、带买卖点标注的净值曲线、含已实现盈亏的持仓回合、逐笔费用。每次运行按回测哈希落库，结果可复现、可比对。

### 3 · 从研报构建因子
上传研报（或粘贴想法），agent 抽取因子构建规格 → 生成 `model`/`train`/`infer` 代码 → 在沙箱中运行（本地为 AST 白名单扫描的子进程；生产为 `--network=none` 的硬化 Docker 沙箱）→ 训练/推理出因子值 → 校验 IC。8 步、带门禁、全血缘。

### 4 · 仿真盘（策略 → 常驻模拟撮合）
冻结策略 → 发布内容寻址工件 → 常驻 NautilusTrader 节点开设仿真账户。订单走完整生命周期，由**收取中国市场费率**的模拟交易所撮合。每日净值对账、持仓/订单/成交/净值视图、全局 kill switch。

### 5 · 研究任务与市场边界
每次运行都始于一份带版本简报，里面明确**市场边界**：标的范围引用、决策/交易/结算时钟、交易所范围、合约选择、移仓规则。正式研究字段以声明式、机器可读的方式钉死；策略逻辑则交给对话。

### 6 · Agent 与基座模型配置
选择 LLM agent（`codex` / `pi`）以及由哪个 **provider**（OpenAI、DeepSeek、Kimi、OpenRouter、Anthropic、Google，或自定义 OpenAI 兼容端点）提供基座模型。provider 是独立、全局的实体——Base URL 与 API Key 配一次即可。模型目录自动拉取（`/v1/models`），顶栏实时显示当前 agent/基座模型，配置即时生效。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy、Alembic、Pydantic |
| 数据 | PostgreSQL、MinIO（内容寻址工件） |
| 研究/交易引擎 | NautilusTrader + 自定义中国市场模型 |
| ML / 因子管线 | Python 3.12、CPU PyTorch、受控沙箱 |
| LLM Agent | `codex` / `pi` CLI、provider 无关、DeepSeek/Zhipu 兜底 |
| 前端 | Next.js 16、React 19、TypeScript |
| 运行环境 | Docker + Docker Compose v2 |

---

## 安装

### 前置要求

- **Docker Desktop**（或兼容的 Docker Engine）与 **Docker Compose v2**
- **`make`**
- 可选：能访问你 LLM provider 的 API（用于研究工作台；否则用内置 deepseek/zhipu 兜底）

> PostgreSQL 和 MinIO 全部由 Docker Compose 管理。**不要**在宿主机安装或初始化 PostgreSQL。

### 快速开始

```bash
# 项目根目录——一条命令拉起全部
./quant
```

该命令先做 Docker 检查，然后依次启动 Postgres → MinIO → 迁移 → 后端 → 前端。

等价的手动方式：

```bash
make bootstrap
make up
curl --fail http://localhost:8091/health/live      # API 存活
curl --fail http://localhost:8091/health/ready     # 迁移已完成
```

### 默认端口

| 服务 | 地址 |
|---|---|
| Web UI | <http://localhost:3090> |
| API / OpenAPI 文档 | <http://localhost:8091/docs> |
| MinIO API / Console | <http://localhost:9000> / <http://localhost:9001> |
| PostgreSQL | `localhost:55432` |

本地开发访问令牌：**`local-researcher`**。

`.env.example` 中的密码仅用于本地开发。执行 `make bootstrap` 后可在未跟踪的 `.env` 中修改。

### 常用命令

```bash
make check            # ruff 格式 + lint + 严格 mypy + pytest（在 3.12 镜像内跑）
make g3-integration   # 真实 Postgres/MinIO 门禁：upgrade->downgrade->upgrade、幂等、内容寻址往返
make logs
make down             # 停止，保留数据
make reset            # 删除全部本地 named volumes（破坏性——仅在确认不需要本地数据时用）
```

---

## 使用导览（5 分钟跑出一个可复现回测）

1. **打开** <http://localhost:3090> → **新建研究**（`/research/new`）。
2. **描述**一条规则并发送。agent 把它变成策略、测试代码、冻结。
3. 打开 **回测**（`/backtest`），选冻结的研究，设频率/区间，点 **运行**。
4. 看总收益率 / 夏普 / 最大回撤 / 净值曲线 / 成交 / 持仓。
5. 冻结策略并在 **仿真** 页开设仿真账户——订单流经收取中国市场费率的模拟交易所，逐日对账。

---

## 架构总览

```
┌───────────────────────────────────────────────────────────────┐
│ 工作台壳（Next.js 顶栏：当前 agent + 基座模型）                  │
│   新建研究 │ 研究任务 │ 策略 │ 回测 │ 仿真                        │
└───────────────┬───────────────────────────────────────────────┘
                │  /v1 REST（Bearer token）经本地代理
┌───────────────▼───────────────────────────────────────────────┐
│                          FastAPI                               │
│  strategy_generation · agent_config · factor_construction      │
│  research（PIT、快照、门禁） · paper（仿真场所、账本）           │
└───────┬───────────────────────────────────┬───────────────────┘
        │                                   │
 ┌──────▼──────┐                     ┌──────▼──────┐
 │ PostgreSQL  │                     │    MinIO    │
 │ (配置、简报，│                     │ (工件、快照， │
 │  血缘、agent │                     │  仿真账本、  │
 │  配置)       │                     │  策略包)     │
 └─────────────┘                     └─────────────┘
```

关键设计不变量：

- **时点（PIT）**数据访问 + **时间类型检查**——不可证明安全的因子在源头就被拦截。
- **确定性回测**按内容哈希落库——输入相同，净值曲线一致，永远可复现。
- **同一个策略包**贯穿回测 → 仿真 → 实盘。
- **市场规则是唯一事实源**（`markets/`），不复制粘贴假设。
- **证据优先**：每个结果都带快照、策略与血缘；门禁 + kill switch 守护进入仿真/实盘的路径。

产品愿景与更细的设计见 `doc/quant-platform-prd.md`、`doc/integrated-quant-pipeline-design.md`、`doc/quant-platform-technical-design.md`。

---

## 仓库结构

```
quant/
├── src/quant_platform/         # 后端：api、research、strategy_generation、
│                               # factor_construction、paper、markets/nt、agent_config
├── frontend/                   # Next.js 工作台（app、components、lib、styles）
├── alembic/                    # 版本化数据库迁移
├── doc/  docs/plans/           # PRD、技术设计、实施计划
├── scripts/                    # ingest、verify、sandbox、live-feed 辅助
├── docker/                     # Dockerfile（api、sandbox）、postgres 初始化
├── tests/                      # pytest 套件（单元 + 集成/门禁）
├── compose.yaml                # api、postgres、minio、migrate、paper/live profiles
└── quant  Makefile             # 一条命令的开发入口 + 任务编排
```

---

## 为什么用 MetaQuant，而不是 notebook 或临时脚本？

| 你在意什么 | MetaQuant |
|---|---|
| 快速拉起本地环境 | `./quant`、Docker、宿主零 Python 依赖 |
| 回测别骗自己 | PIT 数据 + 时间类型检查 + 真实中国费率和规则 |
| 信任 LLM 生成的策略 | 审计代码、代码测试门禁、确定性哈希回测 |
| 几个月后还能复现 | 哈希运行 + 版本化简报 + 内容寻址工件 |
| 仿真对得上实盘 | 同一个策略包贯穿回测 / 仿真 / 实盘 |
| 向研究负责人/风控交代 | 证据优先快照、血缘、门禁、kill switch、对账 |

---

## 许可证

见 [`LICENSE`](./LICENSE)。

---

## 贡献

欢迎提交 Pull Request。提交前请跑 `make check`（在 3.12 镜像内 ruff + mypy + pytest）。较大的改动请先参考 `docs/plans/` 中的实施计划。

**如果 MetaQuant 帮你在量化研究里少骗自己一点，请给个 star ⭐**
