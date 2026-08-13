# 量化研究与交易平台详细技术方案

**文档版本：** v1.0  
**日期：** 2026-08-10  
**状态：** 待评审、待拆解实施  
**上游文档：**

- [量化研究与交易平台 PRD](./quant-platform-prd.md)
- [量化交易平台调研与选型报告](./quant-platform-research.md)
- [综合量化研究 Pipeline 方案](./integrated-quant-pipeline-design.md)

## 1. 技术决策摘要

### 1.1 总体架构

采用：

- **模块化单体控制面**：研究任务、Registry、审批、策略包、报告和 API。
- **任务级并行计算面**：因子计算、验证、回测和论文复现以可重放任务执行。
- **独立执行面**：NautilusTrader 负责正式事件驱动回测、模拟和实盘执行。
- **对象存储作为 artifact 真相源**：所有 PDF、IR、快照、因子结果、回测结果和报告只追加、不覆盖。
- **PostgreSQL 作为元数据与状态真相源**：不保存大规模行情和矩阵结果。

MVP 不引入微服务、Spark、Ray、Temporal、图数据库和复杂在线特征平台。只有在任务规模、可靠性或团队边界明确需要时才拆分。

### 1.2 平台复用策略

| 组件 | 使用方式 |
|---|---|
| Vibe Trading | 复用研究 Agent、数据探索、因子分析和探索性回测；外层包裹 Factor IR |
| TradingAgents | 复用 Agent 角色、研究辩论和风险分析；只输出结构化提案 |
| QuantDinger | 可选 MCP/控制面和 broker 操作适配；不作为研究事实源 |
| NautilusTrader | 正式回测、paper/live、订单、账本、执行和 broker adapter |
| 自研模块 | Factor IR、PIT Data Gateway、Validation Policy、Registry、lineage、审批和 Strategy Compiler |

### 1.3 第三方平台集成模式

本方案不是把四个平台按 `A -> B -> C -> D` 串成一条所有任务都必须经过的流水线，也不是把四个平台的完整产品界面、数据库和领域模型全部嵌入当前系统。

最终产品是一个自研控制面和确定性研究内核，第三方平台通过版本化 Adapter 作为可替换能力接入：

```text
                              ┌─> VibeResearchAdapter ───────┐
ResearchBrief -> AgentGateway ┤                              ├─> ProposalMerger
                              └─> TradingAgentsAdapter ──────┘         |
                                                                      v
                                                           ResearchProposal
                                                                      |
                                                                      v
PIT Data Gateway -> Factor IR Compiler -> Factor Validator -> Strategy Compiler
                                                                      |
                                                                      v
                                                            StrategyPackage
                                                                      |
                                              ┌───────────────────────┴───────────────────────┐
                                              v                                               v
                                  NautilusStrategyAdapter                         QuantDingerAdapter
                                  formal backtest/paper/live                      optional POC only
```

Vibe Trading 和 TradingAgents 是并行、可选的上游研究能力，不存在固定的先后依赖。QuantDinger 与自研控制面存在能力重叠，因此默认不进入正式主链路。NautilusTrader 是当前唯一默认进入正式回测、paper 和 live 路径的第三方运行时。

#### 复用决策矩阵

| 平台 | 默认状态 | 复用粒度 | 部署方式 | 输入 | 允许输出 | 明确禁止 |
|---|---|---|---|---|---|---|
| Vibe Trading | 启用研究试点 | 选择性复用 Agent、因子探索和分析模块，不复用其数据库作为真相源 | 独立 `vibe-adapter` 容器，固定上游 commit/image digest | `ResearchBrief`、只读字段目录、脱敏数据切片 | `CandidateProposal`、`ExploratoryArtifact`、warnings | 直接写 Factor Registry、裁决门禁、发布策略或下单 |
| TradingAgents | 启用研究委员会试点 | 复用或借鉴角色图、辩论、反方研究和风险评审 | 独立 `tradingagents-adapter` 容器 | `ResearchBrief`、`EvidenceBundle`、候选摘要 | `ResearchProposal`、`RiskMemo`、反证条件 | 把观点当正式因子结果、生成正式 P&L、修改 StrategyPackage |
| QuantDinger | 默认关闭 | 只通过 MCP/Strategy/Broker Adapter 做快速 POC，不接管内部领域模型 | Compose optional profile：`quantdinger-adapter` | `StrategyPackage` 或受限 broker 操作请求 | POC 回测、paper 状态、broker 回执 | 成为 PIT、Factor IR、实验账本或正式回测的唯一事实源 |
| NautilusTrader | 正式执行阶段启用 | 直接复用事件驱动运行时、订单、持仓、账本、撮合和执行模型 | 独立 `nautilus-runtime` 容器 | 不可变 `StrategyPackage`、市场数据、规则和账户配置 | `BacktestBundle`、orders、fills、positions、ledger、P&L | 生成研究假设、修改因子、绕过发布审批 |

#### 哪些是直接复用，哪些只是借鉴

- **直接运行上游代码**：NautilusTrader；Vibe Trading 和 TradingAgents 在完成技术/许可证验收后可运行其代码，但必须位于 Adapter 容器后。
- **选择性复用模块**：Vibe Trading 的研究 Agent、因子探索和分析工具；TradingAgents 的角色图、checkpoint 和研究辩论流程。
- **只借鉴设计、不直接依赖**：Agent 角色拆分、critic、risk debate、候选预算和工具调用追踪等思路可以在自研 Agent Gateway 内实现，避免被上游接口锁定。
- **默认不复用完整产品**：不复用第三方 UI、用户体系、数据库、任务状态机、策略格式和研究账本作为本产品核心。
- **可选替代路径**：QuantDinger 用于验证 MCP、broker 和快速闭环，不与自研控制面同时承担同一份状态管理责任。

#### Adapter 的工程边界

每个 Adapter 都必须：

- 实现内部版本化契约，不让上游对象直接进入核心领域模型。
- 通过 HTTP/gRPC/MCP 或 artifact manifest 通信，不直接连接 PostgreSQL 主库。
- 固定上游 commit、依赖锁和镜像 digest。
- 只使用只读数据切片；除 NautilusTrader/受限 broker adapter 外不持有交易凭证。
- 记录请求 hash、响应 hash、模型/provider、工具调用、版本、耗时和成本。
- 支持 feature flag、超时、熔断和降级；Adapter 不可用时，确定性研究内核仍可运行。
- 通过 schema contract、golden case、故障注入和回测对拍后才能进入下一环境。

#### 两条运行路径

正式产品主路径：

```text
自研 Control Plane
  -> Vibe/TradingAgents 可选研究建议
  -> 自研 Factor IR/PIT/Validation/Strategy Compiler
  -> NautilusTrader formal backtest
  -> shadow
  -> paper
  -> approved live
```

快速验证路径：

```text
自研 ResearchBrief/Factor IR
  -> Vibe Trading 或 QuantDinger exploratory backtest
  -> 只生成 EXPLORATORY 结果
  -> 回到自研 Validator 重新计算
  -> 通过后再进入 NautilusTrader
```

快速验证结果不能直接晋级或发布。

### 1.4 强制边界

```text
Agent/LLM
  只能提交 ResearchProposal / EvidenceBundle / RiskMemo

Factor IR Compiler
  负责结构校验、类型检查、时间检查和 canonical AST

Deterministic Core
  负责数据读取、计算、统计、门禁和裁决

Strategy Compiler
  负责把通过门禁的 FactorVersion 编译为 StrategyPackage

Execution Engine
  只消费不可变 StrategyPackage，不反向修改研究结果
```

## 2. 架构分层

### 2.1 逻辑架构

```text
┌──────────────────────────────────────────────────────────────┐
│ Client / UI / CLI / Notebook / MCP                          │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Control Plane                                                │
│ FastAPI | Auth/RBAC | Research Jobs | Registry | Approvals   │
│ Strategy Packages | Reports | Audit API                      │
└───────────────┬───────────────────────────┬──────────────────┘
                ▼                           ▼
┌──────────────────────────────┐  ┌─────────────────────────────┐
│ Agent Gateway                │  │ Orchestrator                │
│ Adapter router               │  │ Dagster assets/jobs         │
│ Vibe/TradingAgents adapters  │  │ budgets/retries/state       │
│ Proposal/evidence trace      │  │ task queue/worker dispatch   │
└───────────────┬──────────────┘  └──────────────┬──────────────┘
                ▼                                ▼
┌──────────────────────────────┐  ┌─────────────────────────────┐
│ Evidence & Governance        │  │ Deterministic Compute        │
│ Paper parser                 │  │ PIT Gateway                  │
│ Evidence bundle              │  │ Factor Compiler/Executor     │
│ Policy engine                │  │ Validator/Optimizer          │
│ Approval/lockbox             │  │ Backtest/Attribution         │
└───────────────┬──────────────┘  └──────────────┬──────────────┘
                ▼                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Storage                                                      │
│ PostgreSQL | Iceberg/Parquet | S3/MinIO | MLflow | Audit Log │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│ Execution Plane                                              │
│ StrategyPackage Validator | NautilusTrader Adapter            │
│ Paper Runtime | Live Runtime | Broker/Exchange Adapters      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 运行边界

#### 研究控制面

负责：

- 创建和查询研究任务。
- 保存结构化输入和状态。
- 管理 Factor Registry、Validation Policy、Alpha Pool。
- 处理审批、lockbox 和策略包发布。
- 展示报告、指标和 lineage。

不负责：

- 在 API 进程中执行长时间因子计算。
- 直接访问 broker live credential。
- 直接执行任意用户代码。

#### 计算面

负责：

- PIT 数据切片。
- Factor IR 编译和执行。
- 因子验证、组合优化和回测。
- 论文 faithful/local 实验。

每个任务必须有：

- 输入 artifact hash。
- `run_fingerprint`。
- 资源预算。
- 代码和容器版本。
- 可重试策略。
- 输出 artifact manifest。

#### 执行面

负责：

- 验证 StrategyPackage。
- 加载策略和风险约束。
- 生成订单、接收行情和处理 fills。
- 维护组合账本、对账、告警和 kill switch。

执行面禁止：

- 修改 Factor IR。
- 修改验证指标。
- 读取未通过门禁的候选。
- 让 LLM 直接生成订单指令。

### 2.3 首阶段市场域

平台首阶段只启用两个 `MarketDefinition`：

| `market_id` | 标的范围 | 研究与执行特点 |
|---|---|---|
| `CN_A` | 上海、深圳市场人民币普通股，优先主板和主流指数历史成分 | 横截面因子、历史 universe、公司行动、T+1、涨跌停、停牌和股票交易成本 |
| `CN_COMMODITY_FUTURES` | 上期所、能源中心、大商所、郑商所、广期所的商品期货 | 具体合约、连续合约、主力切换、夜盘、保证金、每日结算、展期和交割约束 |

市场域是硬隔离，不允许用 A 股的 `universe`、`CostModel`、`ValidationPolicy` 或 `ExecutionModel` 运行商品期货任务，反之亦然。中国境外市场、股指/国债期货、期权和场外衍生品只保留扩展接口，不进入首阶段验收。

每个市场域必须先通过自己的规则 golden set，才允许进入 paper；任何规则缺失时任务进入 `BLOCKED_POLICY`，禁止用通用默认值补齐。

### 2.4 UI/UX 与前端边界

UI 不是后端完成后的装饰层。Phase 0 先冻结信息架构、关键用户流程和页面状态，随后与数据内核、Agent Gateway 和策略服务并行实现。

前端只通过 Control Plane API、查询接口和事件流访问系统，不直接访问 PostgreSQL、对象存储或 broker。前端不复制门禁、风险和交易裁决逻辑。

P0 页面：

- 应用壳层、登录、RBAC、市场域切换和全局任务导航。
- ResearchJob、ResearchBrief、候选列表和运行监控。
- Factor IR、编译错误、数据字段和时间依赖。
- 因子验证、GateDecision、OOS、成本、容量和风险指标。
- 研究报告、EvidenceRef、DatasetSnapshot、RuleSnapshot、代码版本和 lineage。

P1 页面：

- Alpha Pool、StrategySpec、组合优化和正式回测。
- shadow/paper 运行、订单、成交、持仓、P&L、风险和对账。
- live 发布审批、kill switch 和审计操作。

每个页面必须定义 loading、empty、error、permission denied、stale data 和 long-running 状态，并绑定 API schema、事件类型、权限、危险操作确认和审计字段。

## 3. 技术栈与部署

### 3.1 MVP 技术栈

| 领域 | 选择 | 用途 |
|---|---|---|
| API | FastAPI + Pydantic v2 | 控制面、契约和校验 |
| 语言 | Python 3.12 | 控制面、Agent、研究编排和数值管线 |
| 因子计算 | Polars + Apache Arrow | 列式计算、类型和批量处理 |
| 探索查询 | DuckDB | 本地数据探索和小规模回测 |
| 数据格式 | Parquet | 中间结果和批量 artifact |
| 表格式 | Apache Iceberg | PIT 表、快照和 schema evolution |
| 元数据 | PostgreSQL（Docker Compose） | Registry、状态机、审批、lineage |
| 对象存储 | S3/MinIO | PDF、快照、矩阵、报告和 manifest |
| 编排 | Dagster | 资产、分区、依赖、重试和 backfill |
| 实验 | MLflow | 参数、指标、artifact 索引 |
| 优化 | CVXPY + OSQP | 组合优化 |
| 论文解析 | PyMuPDF + Docling | 页级版面、公式和表格 |
| Web UI | Next.js + TypeScript | 研究工作台、报告、策略和交易运维页面 |
| 执行 | NautilusTrader | 正式回测、paper/live、账本和适配器 |
| API 观测 | OpenTelemetry | traces、metrics 和 logs |
| 运行 | Docker Compose | PostgreSQL、API、worker、MinIO、Dagster 等本地和单机组件 |
| 生产 | Kubernetes 或 Nomad | 后续 worker 扩缩容 |

### 3.2 市场规则注册表

新增 `MarketRuleRegistry`，按 `market_id + instrument_id + effective_time` 解析生效规则。规则必须版本化并进入 `DatasetSnapshot` 和 `run_fingerprint`：

```yaml
market_id: CN_COMMODITY_FUTURES
instrument_id: rb
exchange: SHFE
effective_from: 2026-01-01
calendar_ref: calendar://shfe/2026
sessions_ref: sessions://shfe/rb/v1
price_limit_ref: limits://shfe/rb/v1
fee_schedule_ref: fees://shfe/rb/2026-01
margin_schedule_ref: margin://shfe/rb/2026-01
settlement_rule_ref: settlement://shfe/daily_mark_to_market_v1
contract_spec:
  contract_multiplier: 10
  tick_size: 1
  quote_unit: CNY/ton
delivery_rule_ref: delivery://shfe/rb/v1
roll_policy_ref: roll://rb/volume_switch_no_adjustment_v1
```

注册表至少覆盖交易日历、时段和跨午夜归属、涨跌停、最小交易单位/变动价位、合约乘数、费率、保证金、结算、持仓限制、交割和展期。规则来源、版本、适用范围和生效时间必须可审计。

### 3.3 部署形态

#### Local

适合单研究员和开发。所有本地依赖，包括 PostgreSQL，统一由 Docker Compose 管理：

```text
docker compose
  postgres
  api
  minio
  dagster
  mlflow
  worker
  vibe-adapter                  # optional profile
  tradingagents-adapter         # optional profile
  quantdinger-adapter           # optional POC profile, disabled by default
  nautilus-runtime              # enabled for formal backtest/paper/live
```

### 3.4 Docker PostgreSQL 初始化

本地安装和初始化由 Docker Compose 负责，PostgreSQL 数据必须使用命名 volume 持久化：

```text
docker compose up -d postgres
  -> 创建 quant_app 用户和 quant_platform 数据库
  -> 配置最小权限
  -> 运行 Alembic migrations
  -> 执行 schema/health check
```

初始化要求：

- 应用连接使用独立的 `quant_app` 用户，不使用超级用户。
- 开发、测试和本地 paper 使用不同数据库或 schema，不混用 live 数据。
- PostgreSQL 数据目录挂载到 Docker named volume，不使用容器临时文件系统。
- `DATABASE_URL`、密码和 SSL 配置通过 Compose `.env` 或 secret 管理，不写入仓库。
- 每次 schema 变更必须有 Alembic migration，并在空库和现有库各执行一次。
- 每日使用 `pg_dump` 备份元数据和审计表；artifact、行情和矩阵结果仍备份到对象存储。
- 使用 `pg_isready`、迁移版本和关键表检查作为启动健康检查。

本地 Compose 环境迁移到 Shared Research 或 Production 时，只替换 PostgreSQL 服务部署方式和连接配置，不改变领域模型和 SQL 契约。

#### Shared Research

适合团队：

- 团队环境可使用独立 PostgreSQL 服务或托管 PostgreSQL；本地 MVP 继续使用 Docker Compose 中的 PostgreSQL。
- S3/MinIO 版本化 bucket。
- 独立 compute worker pool。
- Dagster daemon 和 scheduler。
- MLflow tracking server。
- Grafana/Prometheus。
- live execution 使用独立主机或 namespace。

#### Production Execution

研究和交易分离。PostgreSQL 可以运行在独立宿主机或托管数据库服务中，不能与交易进程共享容器和凭证：

```text
Research VPC / Namespace
  no broker credentials
  no live network egress

Execution VPC / Namespace
  only signed StrategyPackage
  broker allowlist
  MFA and kill switch
```

## 4. 领域模型和状态

### 4.1 核心实体

| 实体 | 作用 | 真相源 |
|---|---|---|
| `ResearchJob` | 一次研究任务和预算 | PostgreSQL |
| `MarketDefinition` | 市场域、交易所范围、资产类型和启用状态 | PostgreSQL |
| `InstrumentMaster` | 股票、期货品种和具体合约的历史主数据 | PostgreSQL + Object Store |
| `TradingRuleVersion` | 日历、时段、费率、保证金、结算和可交易规则 | PostgreSQL |
| `ContractChain` | 主力/次主力识别、连续合约和换月事件 | PostgreSQL + Object Store |
| `ResearchBriefVersion` | 可冻结、不可覆盖的研究假设、约束和反证版本 | PostgreSQL + artifact |
| `SourceArtifact` | PDF、网页快照、作者代码和数据许可 | Object Store |
| `EvidenceRef` | 页码、bbox、段落、表格或代码位置 | PostgreSQL |
| `Hypothesis` | 经济机制、预期方向和 falsification | PostgreSQL |
| `FactorSpec` | 人类可读因子定义 | PostgreSQL |
| `FactorVersion` | 因子数据库身份、semver 和内容身份 | PostgreSQL |
| `CompiledIR` | canonical Factor IR 和 AST | Object Store + PostgreSQL |
| `DatasetContract` | 字段语义、时间和许可 | PostgreSQL |
| `DatasetSnapshot` | 冻结的数据版本 | Iceberg + PostgreSQL |
| `RuleSetSnapshot` | 一次运行绑定的封闭规则版本集合 | PostgreSQL + Object Store |
| `ExperimentSpec` | 预注册的实验规则 | PostgreSQL |
| `ExperimentRun` / `Attempt` | 一次计算验证运行及不可覆盖的尝试 | PostgreSQL + Object Store |
| `ValidationBundle` | 指标、分层、稳健性和门禁结果 | Object Store |
| `GateDecision` | 通过、拒绝、隔离或 waiver | PostgreSQL |
| `AlphaPoolVersion` / `AlphaPoolEntry` | 可用于策略的冻结池版本和成员 | PostgreSQL |
| `StrategySpecVersion` | 因子组合、风险、成本和调仓版本 | PostgreSQL |
| `StrategyBuildArtifact` | 正式回测消费的不可变候选构建物 | Object Store + PostgreSQL |
| `BacktestRun` | 五时钟/结算时钟回测结果和账本 | Object Store + PostgreSQL |
| `StrategyPackagePayload` | 引用正式回测的不可变发布 payload | Object Store |
| `PackageAttestation` | paper/live 环境相关批准、拒绝和撤销 | PostgreSQL + Audit |
| `DeploymentRun` | shadow/paper/live 的独立运行状态 | PostgreSQL + execution store |
| `Approval` | 人工审批记录 | PostgreSQL + Audit |
| `AuditEvent` | 追加式审计日志 | Append-only store |

### 4.2 独立状态机

Gate G0 决定不使用覆盖全流程的单一研究状态机。`ResearchJob` 只表达协调状态；`ResearchBriefVersion`、`ExperimentSpec`、`ExperimentRun`、`Attempt`、`Replication`、`PackageRelease` 和 `DeploymentRun` 分别拥有自己的状态与终态。完整枚举和迁移约束见 `docs/architecture/g0-contract-baseline.md`。

状态迁移只能由各聚合的状态机服务执行，客户端不能直接改数据库状态，也不能从自由文本 stage 推导权威状态。

### 4.3 运行指纹

```text
expression_hash  = SHA256(canonical_AST)
data_contract_hash = SHA256(fields + availability_rules)
context_hash = SHA256(universe + clocks + postprocess + policy)
factor_version_id = factor_id + semver + expression_hash + context_hash
run_fingerprint = SHA256(
  factor_version_id
  + snapshot_id
  + code_sha
  + image_digest
  + dependency_lock_hash
  + config_hash
  + random_seed
)
```

相同 `run_fingerprint` 必须生成相同的关键结果；不一致时运行标记为 `NON_REPRODUCIBLE`。

## 5. Factor IR v1

### 5.1 设计要求

Factor IR 是人工公式、论文公式、自然语言和 Agent 输出进入确定性系统的唯一入口。它必须：

- 声明输入字段、单位和 available-time 规则。
- 声明市场、资产、频率、universe 和决策/交易时钟。
- 使用白名单算子和受限 AST。
- 支持空值、Inf、除零、窗口和边界策略。
- 能静态计算 lookback 和 available-time。
- 可生成 canonical serialization 和表达式 hash。
- 禁止任意 Python、SQL、Shell、网络请求和文件 IO。

### 5.2 类型系统

MVP 类型：

- `ScalarSeries<T, Unit>`
- `CrossSection<T, Unit>`
- `EventSeries<T>`
- `LabelSeries<T>`
- `UniverseMask`
- `ExposureMatrix`
- `TimestampedValue<T>`

约束：

- `LabelSeries` 只能被 Validator 使用。
- `FactorExecutor` 不允许引用 forward return、future label 或测试窗统计量。
- 横截面算子必须声明 universe 和缺失处理。
- 时间序列算子必须声明最大 lookback。
- 单位不兼容在编译期失败。

### 5.3 IR 示例

```yaml
schema_version: factor-ir/v1
factor_id: analyst.disagreement_momentum
version: 1.0.0

origin:
  type: research_brief
  source_id: brief_20260809_001
  evidence_refs:
    - brief://brief_20260809_001#hypothesis

market_scope:
  market: CN
  asset_class: equity
  frequency: 1d
  universe_ref: universe://csi800_pit

decision_clock:
  signal_time: T_CLOSE+30m
  earliest_trade_time: T+1_OPEN+5m

inputs:
  - alias: eps_mean
    field_ref: analyst.eps_fy1_mean
    unit: CNY
    available_time_rule: vendor_timestamp
  - alias: eps_std
    field_ref: analyst.eps_fy1_std
    unit: CNY
    available_time_rule: vendor_timestamp
  - alias: close
    field_ref: market.eod.close_adjusted
    unit: CNY
    available_time_rule: T_CLOSE+20m

expression:
  op: neg
  args:
    - op: mul
      args:
        - op: safe_div
          zero_policy: null
          args:
            - {ref: eps_std}
            - {op: abs, args: [{ref: eps_mean}]}
        - {op: returns, periods: 20, input: close}

postprocess:
  winsorize: {method: mad, limit: 5}
  neutralize:
    exposures: [industry_sw1, log_float_mkt_cap]
  normalize: cross_sectional_zscore

validation_policy_ref: policy://cn_equity_daily_v1
```

商品期货 Factor IR 的 `market_scope` 必须额外声明交易所、品种和合约链：

```yaml
market_scope:
  market: CN
  asset_class: commodity_futures
  exchange_scope: [SHFE, INE, DCE, CZCE, GFEX]
  frequency: 1d
  universe_ref: universe://liquid_commodity_contracts_pit
  contract_chain_ref: chain://rb/main/volume_switch_v1
  roll_policy_ref: policy://roll/volume_switch_no_adjustment_v1
  validation_policy_ref: policy://cn_commodity_futures_daily_v1
```

### 5.4 编译阶段

```text
Parse
  -> Schema Validation
  -> Canonicalization
  -> Type Check
  -> Unit Check
  -> Lookback Analysis
  -> Available-time Analysis
  -> Policy Check
  -> AST Hash
  -> CompiledIR
```

编译器输出：

- canonical AST。
- input contract。
- inferred lookback。
- propagated available-time。
- operator list。
- warnings。
- hard errors。
- expression hash。

## 6. 数据事实源与 PIT 架构

### 6.1 数据事实源边界

平台自带的数据加载器、MCP 数据接口和 broker connector 不是本产品的正式数据事实源。它们可以被 Adapter 调用，但所有正式研究、正式回测和交易规则判断必须经过自研 `Data Gateway`、`MarketRuleRegistry` 和 `Snapshot Catalog`。

正式数据链路：

```text
交易所/监管规则 + 授权数据供应商 + broker/CTP 行情
                         |
                         v
              ExternalSourceAdapter
                         |
                         v
 Raw Landing -> Bronze -> PIT Silver -> Research Gold
                                      |
                                      v
                           DatasetSnapshot / RuleSnapshot
                                      |
             ┌────────────────────────┼────────────────────────┐
             v                        v                        v
       Factor Executor        Vibe/TradingAgents          NautilusTrader
       formal research        read-only slices            backtest/paper/live
```

#### 数据来源分层

| 数据类型 | 正式来源 | 平台数据能力的使用 |
|---|---|---|
| A 股行情、复权/未复权价格、成交量 | 授权历史行情供应商，必要时与交易所发布数据交叉校验 | Vibe/QuantDinger 数据接口可用于探索性检查，不写入正式 snapshot |
| A 股财务、公告、业绩快报和修订版本 | 能提供公告时间、可用时间和历史 revision 的授权 PIT 数据供应商 | TradingAgents 的基本面/新闻工具只提供线索和证据候选，不能替代 PIT 字段 |
| A 股历史成分、行业、上市/退市、ST、停牌和公司行动 | 授权数据供应商的历史版本，交易所/指数规则作交叉校验 | 平台 universe 接口只能作为候选 universe，必须由自研历史 universe 构建器重算 |
| 商品期货 OHLCV、结算价、成交量、持仓量、盘口 | 授权期货历史数据供应商、交易所数据或两者交叉校验 | Vibe/QuantDinger 数据接口可用于探索性连续合约，不作为正式合约链事实源 |
| 商品期货合约规格、交易时段、涨跌停、保证金、手续费、结算、交割 | 交易所规则和 broker/CTP 参数，按生效日期归档 | 任何平台返回的规则只能作为对照，不能覆盖 `TradingRuleVersion` |
| 实时行情、订单、成交和账户状态 | 实际 broker/交易通道及其行情接口 | NautilusTrader 负责消费统一事件和执行；不把平台 demo 行情当实盘行情 |

当前技术方案只定义来源契约和适配接口，**尚未最终选定具体数据供应商**。Phase 0 必须完成供应商选型、授权确认、历史覆盖、修订/PIT 能力和 golden set 验收后，才能冻结 `source_id` 和生产配置。

#### 第三方平台数据的使用规则

- **Vibe Trading**：其数据加载器和因子工具接入 `ExploratoryDataAdapter`，只用于字段探索、候选因子和 cheap gate；正式计算必须重新从 `Data Gateway` 读取冻结快照。
- **TradingAgents**：其搜索、新闻和市场数据工具只用于形成 `EvidenceBundle`、研究假设和风险意见；除非字段已进入 PIT snapshot，否则不能作为因子输入。
- **QuantDinger**：其 MCP 数据、Strategy API 和 broker 数据只进入可选 POC adapter；不作为研究数据目录、规则注册表或正式账本。
- **NautilusTrader**：消费自研规范化的历史/实时事件和 `StrategyPackage`，负责正式回测、paper/live、订单和账本；不负责构建 A 股 PIT 数据或商品期货历史合约链。

平台连接器的结果必须标记为 `EXPLORATORY`，并记录平台、版本、请求参数、数据 provider、时间和 hash。任何 `EXPLORATORY` artifact 不得直接进入 `GateDecision`、`AlphaPoolEntry` 或 live 发布。

### 6.2 数据时间字段

所有正式研究字段至少保留：

- `instrument_id`
- `event_time`
- `available_time`
- `ingested_at`
- `revision_id`
- `source_id`
- `license_tag`
- `value`
- `unit`

查询硬约束：

```sql
available_time <= :decision_time
AND snapshot_id = :frozen_snapshot
AND license_tag IN (:allowed_licenses)
```

### 6.3 数据分层

```text
Raw Landing
  -> Normalized Bronze
  -> PIT Silver
  -> Research Gold
  -> DatasetSnapshot
```

- `Raw Landing`：保留供应商原始 payload、接收时间和 checksum。
- `Normalized Bronze`：统一字段名、类型、单位和主键。
- `PIT Silver`：按 event/available/revision 时间建模。
- `Research Gold`：生成可查询的因子输入表、历史 universe 和证券状态。
- `DatasetSnapshot`：针对一次实验冻结的快照。

### 6.4 A 股数据域

MVP 必须覆盖：

- 日线 OHLCV、复权和未复权价格。
- 交易日历和交易时段。
- 证券主数据、上市/退市、ST 和停牌。
- 涨跌停价格和可交易状态。
- 历史指数/行业成分。
- 财务报表、公告时间、业绩快报和修订版本。
- 行业分类、流通市值和风险暴露。
- 费用、印花税、佣金和过户费参数。
- 公司行动和收益调整。

### 6.5 商品期货数据域

MVP 必须覆盖：

- 交易所、品种、合约、上市/挂牌、最后交易日、交割月和实际可交易状态。
- 日盘/夜盘交易时段、跨午夜交易日归属、交易日历和节假日。
- OHLCV、结算价、持仓量、成交量、盘口/深度数据的时间戳和来源版本。
- 合约乘数、最小变动价位、报价单位、涨跌停、保证金和手续费。
- 平今/平昨、持仓限额、交割规则、到期前退出和强平规则。
- 主力/次主力识别、连续合约、换月事件、旧/新合约映射和展期价格调整。

连续合约是研究派生数据，不是可交易标的。每个连续合约值必须能追溯到具体合约、换月规则、价差处理和可交易性判断。

### 6.6 Snapshot Catalog

每个快照记录：

```yaml
snapshot_id: cn-a-daily-20260810-001
market: CN_A
as_of: 2026-08-10
source_versions:
  market_eod: vendor-20260810
  fundamentals: vendor-20260809
  universe: csi800-pit-v3
tables:
  - name: market_eod
    uri: s3://quant/snapshots/.../market_eod
    schema_hash: ...
    row_count: 123456789
    content_hash: ...
license_tags: [internal-research]
created_at: 2026-08-10T09:00:00Z
```

商品期货快照必须同时绑定合约规格、规则版本和合约链：

```yaml
snapshot_id: cn-futures-daily-20260810-001
market: CN_COMMODITY_FUTURES
as_of: 2026-08-10
source_versions:
  futures_bars: vendor-20260810
  contract_specs: exchange-rules-20260810
  contract_chain: liquid-main-pit-v1
  fees_margin: exchange-broker-schedule-v1
rule_versions:
  - trading_rule://shfe/rb/2026-01
  - trading_rule://dce/m/2026-01
tables:
  - name: futures_daily_bars
    uri: s3://quant/snapshots/.../futures_daily_bars
    schema_hash: ...
    row_count: 1234567
    content_hash: ...
  - name: contract_chain_events
    uri: s3://quant/snapshots/.../contract_chain_events
    schema_hash: ...
    row_count: 23456
    content_hash: ...
```

## 7. 防泄漏实现

### 7.1 编译期静态检查

阻断：

- 负 lag。
- forward fill。
- `LabelSeries` 进入因子。
- 测试窗或全样本拟合 scaler。
- 无界窗口。
- available-time 晚于 decision time。
- 同收盘信号直接使用同收盘成交价。
- 使用未来 universe、行业和证券状态。

### 7.2 PIT 访问层

- 财务数据按公告/供应商可用时间查询。
- 历史指数、行业和证券状态按点时版本查询。
- 修订数据以新 revision 追加，不覆盖历史可见版本。
- 保留退市证券和退市收益。
- 研究任务禁止通过裸 SQL 绕过 Data Gateway。

### 7.3 动态对拍

每个正式因子至少执行：

1. 删除未来 N 日数据后重算，历史因子值不得变化。
2. 将数据可用时间延迟一个时点，检查信号变化是否符合规则。
3. 注入未来污染哨兵字段，结果必须不变。
4. 随机抽样决策时点执行 time-travel replay。

任一失败，FactorRun 进入 `QUARANTINED`。

## 8. 研究任务编排

### 8.1 Dagster 资产

建议资产：

```text
source_artifact
  -> evidence_bundle
  -> hypothesis_spec
  -> factor_spec
  -> compiled_ir
  -> dataset_snapshot
  -> factor_values
  -> validation_bundle
  -> gate_decision
  -> alpha_pool
  -> strategy_spec
  -> backtest_bundle
  -> signed_report
```

每个资产：

- 只写新版本。
- 由输入 hash 自动生成 key。
- 失败可以从最近成功资产恢复。
- 输出 manifest 和 metrics。
- 记录资源、耗时、代码和容器版本。

### 8.2 任务状态

API 只创建任务，长任务由 Dagster worker 执行。状态迁移由状态机服务统一管理：

```text
CREATED
  -> INTAKE_VALIDATED
  -> SOURCE_FROZEN
  -> EVIDENCE_READY
  -> CANDIDATES_PROPOSED
  -> SPEC_COMPILED
  -> PREREGISTERED
  -> DATA_READY
  -> COMPUTED
  -> VALIDATED
  -> HUMAN_REVIEW
  -> STRATEGY_BUILT
  -> BACKTESTED
  -> REPORTED
  -> APPROVED | REJECTED | ARCHIVED
```

### 8.3 重试与预算

- 基础设施错误最多自动重试 3 次。
- 数据、策略或政策错误不自动重试。
- 每个任务有候选数、token、CPU、内存、存储和 wall-clock 预算。
- 超预算进入 `BLOCKED_POLICY`，等待人工审批。
- 重试不改变原始 run；每次重试有独立 attempt。

## 9. Agent Gateway

### 9.1 统一输出

所有 Agent 必须输出 Pydantic 结构，不接受自由文本作为正式输入：

```python
class ResearchProposal(BaseModel):
    job_id: str
    hypothesis: str
    mechanism: str
    expected_sign: Literal["positive", "negative", "unknown"]
    candidate_factors: list[CandidateFactor]
    falsification_tests: list[FalsificationTest]
    data_requests: list[DataRequest]
    evidence_refs: list[str]
    uncertainty: list[Uncertainty]
```

### 9.2 Agent 角色

- `IntakeAgent`：将自然语言转成 ResearchBrief。
- `HypothesisAgent`：生成机制、代理变量、预期方向和反证条件。
- `PaperAgent`：抽取论文主张和实验设定。
- `FormulaAgent`：生成 LaTeX、符号表和受限 AST。
- `MappingAgent`：映射到 Data Catalog。
- `CriticAgent`：检查泄漏、重复、不可证伪和证据不足。
- `ResultAnalystAgent`：只解释结构化指标，不生成数值。
- `ReportAgent`：生成叙事报告，不写回指标。

### 9.3 Provider 策略

- 小模型：分类、字段抽取、格式修复和报告初稿。
- 强模型：歧义公式、复杂映射、反方批评和人工待审任务。
- Provider、模型、prompt hash、温度、token、工具和检索语料必须记录。
- Agent 失败不改变确定性任务状态，必须返回结构化错误。

## 10. 因子验证内核

### 10.1 Gate 0：静态和时间安全

- IR、类型、单位、lookback 和可用时间检查。
- 无标签依赖、未来函数和全样本统计。
- universe、benchmark、horizon、信号时间和执行时间明确。

### 10.2 Gate 1：数据质量

- 覆盖率、有效样本和历史长度。
- 主键、日历、单位、币种和公司行动。
- NaN、Inf、常数因子、极值和 stale 数据。
- 相同 run fingerprint 重算一致性。

### 10.3 Gate 2：预测能力

正式输出：

- Pearson IC、Rank IC、ICIR。
- Newey-West 调整 t 值。
- 1/5/10/20/60 日 IC decay。
- 分层收益、单调性和 Top-Bottom spread。
- 行业、市值、beta 控制后的横截面回归。
- 年份、市场状态、行业、市值和流动性子样本。

### 10.4 Gate 3：稳健性和伪发现

- 参数邻域。
- 数据源扰动。
- universe 扰动。
- winsorize、中性化和执行价格敏感性。
- 随机标签、时间错位和负对照。
- Benjamini-Hochberg FDR。
- Deflated Sharpe Ratio。
- PBO。
- 所有候选和调参次数登记。

### 10.5 Gate 4：独立性、成本和容量

- 截面和因子收益相关。
- 正交化后的增量 IC。
- 换手、信号半衰期和调仓频率。
- 成本后收益。
- ADV 参与率、冲击、涨跌停和停牌约束。
- AUM 容量曲线。

### 10.6 Gate 5：晋级

硬门槛：

- 时间安全。
- 数据质量。
- OOS 方向。
- 伪发现控制。
- 最低容量。

评分卡：

```text
效应强度 25%
稳定性 25%
独立性 20%
成本后价值 20%
可解释性 10%
```

异常优秀的结果进入 `QUARANTINED` 调查，不直接通过。例外必须记录审批人、理由、范围和到期时间。

## 11. Alpha Pool、策略和组合优化

### 11.1 Alpha Pool

只有通过 Gate 5 的 `FactorVersion` 才能进入 Alpha Pool。记录：

- 因子方向、universe 和 horizon。
- OOS 指标和 fold 分布。
- 相关性、成本、容量和失效条件。
- 当前生命周期和最近验证时间。

### 11.2 MVP 组合

使用稳健 IC 加权和 shrinkage：

```text
raw_weight_i = clip(EWMA(train_IC_i) / train_IC_vol_i)
weight = shrink(raw_weight, equal_weight, lambda)
weight = constrained_normalize(weight)
```

规则：

- 权重只在训练窗估计。
- 下一 OOS fold 使用冻结权重。
- 必须保留等权基线。
- 必须输出因子消融和边际贡献。
- 机器学习组合视为复合因子，重新预注册和门禁。

### 11.3 组合优化

```text
maximize alpha' w
       - lambda_risk * w'Cov*w
       - lambda_tc * Cost(w - w_prev)
       - lambda_conc * ConcentrationPenalty(w)
```

约束：

- 单票、行业、风格、beta 和持仓数。
- 净敞口、总敞口和 tracking error。
- ADV 参与率、换手预算和最小交易单位。
- 停牌、涨跌停、ST 和融券可用性。

优化失败必须返回冲突诊断，并按预注册规则降级到可行基线，不允许静默放宽约束。

## 12. 五时钟回测、商品期货结算和 NautilusTrader 适配

### 12.1 五时钟

回测账本区分：

1. 数据可用时钟。
2. 信号时钟。
3. 订单时钟。
4. 成交时钟。
5. 收益/估值时钟。

商品期货额外增加结算时钟，用于每日结算价、盯市盈亏、可用资金、保证金占用和强平检查；它不能被收盘估值时钟替代。

事件顺序：

```text
数据到达
  -> 构建 PIT universe
  -> 计算因子
  -> 生成目标仓位
  -> 检查可交易状态
  -> 生成订单
  -> 成交模型生成 fill
  -> 更新现金和持仓
  -> 处理公司行动
  -> 估值、归因和审计
```

### 12.2 A 股执行规则

MVP 需要显式实现：

- T 日收盘后生成信号，T+1 可交易时点执行。
- 涨停不可买、跌停不可卖。
- 停牌不可成交。
- ST 和上市天数过滤使用历史状态。
- 印花税只在卖出侧计算。
- 佣金、过户费、点差和最小滑点按日期/市场版本化。
- 最小交易单位和无法成交订单的顺延规则。
- 公司行动对价格、持仓和收益的影响。

### 12.3 商品期货执行规则

MVP 需要显式实现：

- 连续合约只用于研究序列，订单必须映射到具体、当时可交易的期货合约。
- 合约乘数、最小变动价位、报价单位、到期日、最后交易日、交割月和交易所归属。
- 日盘、夜盘、跨午夜交易日归属、集合竞价、休市和节假日规则。
- 涨跌停、手续费、平今/平昨、保证金比例、涨跌停板调整和每日结算。
- 盯市盈亏、结算价、可用资金、追加保证金、强平和最大持仓约束。
- 主力/次主力识别和换月：记录换月原因、时间、旧/新合约、价差、手续费和滑点。
- 到期前退出和交割禁止策略；除非经过单独审批，MVP 不模拟实物交割。
- 合约流动性、成交量参与率、盘口深度和市场冲击成本。

商品期货回测必须分别输出价格收益、展期收益、保证金占用和资金成本、手续费/滑点/冲击/换月成本，以及每日结算现金流、浮盈浮亏和强平风险。

### 12.4 StrategyPackage

`StrategyPackage` 是研究和执行之间唯一的发布接口：

```yaml
schema_version: strategy-package/v1
package_id: strategy.cn_a.0001
version: 1.0.0
market: CN_A
universe_ref: universe://csi800_pit
factor_refs:
  - factor://value/1.2.0
  - factor://quality/2.0.1
execution:
  signal_time: T_CLOSE+30m
  trade_time: T+1_OPEN+5m
  rebalance: weekly
risk:
  max_single_name_weight: 0.01
  max_turnover_annual: 8.0
  max_adv_participation: 0.10
artifacts:
  ir_manifest: s3://...
  validation_bundle: s3://...
  backtest_bundle: s3://...
provenance:
  code_sha: ...
  image_digest: ...
  snapshot_id: ...
  policy_version: ...
  report_manifest_hash: ...
signature:
  algorithm: ed25519
  key_id: strategy-release-key-01
  value: ...
```

上述 YAML 表达不可变 payload。`approved/rejected/revoked` 不属于 payload；paper/live 批准由独立 `PackageAttestation` 绑定 `content_hash`、environment、审批人和有效期。正式回测在 package 生成前消费不可变 `StrategyBuildArtifact`，package 再引用已接受的 `BacktestRun`，避免循环依赖。

商品期货策略包还必须包含：

```yaml
market: CN_COMMODITY_FUTURES
exchange_scope: [SHFE, INE, DCE, CZCE, GFEX]
instrument_scope: commodity_futures
contract_chain_ref: chain://rb/main/volume_switch_v1
roll_policy_ref: policy://roll/volume_switch_no_adjustment_v1
margin_policy_ref: policy://margin/exchange_and_broker_schedule_v1
delivery_policy: exit_before_delivery
```

策略包验证必须确认研究连续合约到实际合约的映射、换月和成本模型完整，不能仅验证连续合约净值曲线。

发布前必须验证：

- FactorVersion 全部通过门禁。
- 数据快照和策略包匹配。
- 风险参数完整。
- 报告签名有效。
- 依赖和容器可拉取。
- 运行时只读加载，不允许修改包内容。

## 13. 数据库和存储设计

### 13.1 PostgreSQL 表

最小表集：

```text
research_jobs
research_brief_versions
source_artifacts
evidence_refs
hypotheses
factor_specs
factor_versions
compiled_irs
dataset_contracts
dataset_snapshots
trading_rule_versions
rule_set_snapshots
experiment_specs
experiment_runs
run_attempts
validation_bundles
gate_decisions
alpha_pool_versions
alpha_pool_entries
strategy_spec_versions
strategy_build_artifacts
backtest_runs
strategy_package_payloads
package_attestations
deployment_runs
approvals
llm_traces
audit_events
```

### 13.2 `factor_runs` 示例字段

```text
id
factor_version_id
experiment_id
snapshot_id
run_fingerprint
status
attempt
code_sha
image_digest
policy_version
random_seed
started_at
finished_at
metrics_uri
artifact_manifest_uri
error_code
created_by
```

### 13.3 对象存储布局

```text
s3://quant/
  raw/{source_id}/{ingest_date}/{hash}/
  snapshots/{snapshot_id}/
  factors/{factor_version_id}/
  experiments/{experiment_id}/{run_id}/
  backtests/{backtest_id}/
  strategies/{package_id}/{version}/
  reports/{report_id}/
  quarantine/{artifact_id}/
```

对象写入完成后生成 manifest，manifest 包含 schema hash、content hash、大小、行数、来源、许可和父级 artifact。

## 14. API 设计

### 14.1 控制面 API

```text
POST /v1/research-jobs
GET  /v1/research-jobs/{job_id}
POST /v1/research-jobs/{job_id}:propose
POST /v1/papers
GET  /v1/papers/{paper_id}/evidence
POST /v1/factors:compile
GET  /v1/factors/{factor_id}/versions
POST /v1/experiments:preregister
POST /v1/experiments/{experiment_id}:run
GET  /v1/experiments/{experiment_id}/validation
POST /v1/gate-decisions
GET  /v1/alpha-pool
POST /v1/strategies:build
POST /v1/backtests
GET  /v1/backtests/{backtest_id}
POST /v1/strategy-packages/{package_id}:approve
POST /v1/strategy-packages/{package_id}:publish-paper
POST /v1/strategy-packages/{package_id}:publish-live
GET  /v1/lineage/{artifact_id}
GET  /v1/audit-events
```

### 14.2 写接口通用要求

每个写接口要求：

- `Idempotency-Key`。
- actor 由 OIDC/Bearer 认证主体注入，body 不接受 `actor`。
- `reason`。
- `parent_artifact_id`。
- `budget`。
- `schema_version`。
- 修改已有聚合时使用 `If-Match`。

API 只创建任务和状态变更请求，不执行长时间计算。

### 14.3 Agent Gateway API

```text
POST /v1/agent/intake
POST /v1/agent/hypothesis
POST /v1/agent/paper-extract
POST /v1/agent/formula-map
POST /v1/agent/critic
POST /v1/agent/report
```

Agent API 必须返回：

- 结构化 payload。
- evidence refs。
- uncertainty。
- provider/model。
- prompt hash。
- tool trace。
- token/cost。

所有 Agent 结果进入待编译或待审批状态，不能直接触发正式计算。

## 15. 论文复现技术流程

### 15.1 证据对象

```yaml
evidence_ref:
  source_artifact_id: paper-001
  page: 7
  bbox: [80, 210, 520, 450]
  kind: formula
  text_hash: ...
  extraction_method: pdf-layout-v1
  confidence: 0.94
```

### 15.2 映射状态

```text
UNMAPPED
  -> EXACT
  -> DERIVED
  -> PROXY
  -> UNAVAILABLE
```

- `EXACT`：语义、单位和时间定义一致。
- `DERIVED`：可由本地字段确定性推导。
- `PROXY`：本地字段是替代变量，必须人工批准。
- `UNAVAILABLE`：不能进入 faithful reproduction。

### 15.3 双轨实验

- `faithful_reproduction`：尽可能保持论文市场、样本、公式、调仓和成本。
- `local_adaptation`：使用本地数据和市场规则。

两条轨道使用不同 ExperimentSpec 和 FactorVersion，报告不得合并为一个“复现成功”结论。

## 16. 回测和执行实现

### 16.1 研究回测

研究回测用于：

- 快速排查因子工程错误。
- 生成基础统计和调参反馈。
- 运行大量候选的 cheap gate。

研究回测结果标记为 `EXPLORATORY`，不具备正式发布资格。

### 16.2 正式回测

正式回测由 NautilusTrader adapter 或等价确定性运行时执行，必须：

- 使用冻结 DatasetSnapshot。
- 消费不可变 `StrategyBuildArtifact`；回测通过后才生成引用该 `BacktestRun` 的 `StrategyPackage` payload。
- 显式处理订单、成交、现金、持仓、费用和公司行动。
- 生成订单、fills、ledger、positions、exposures 和 attribution。
- 输出不可成交、延迟、降级和异常事件。

### 16.3 对拍测试

至少包含：

- 研究回测与正式回测信号对拍。
- T+1 订单时点对拍。
- 涨跌停/停牌订单状态对拍。
- 费用和滑点对拍。
- 公司行动和收益调整对拍。
- 同一 StrategyPackage 在 replay、paper 和 live dry-run 的状态机对拍。

## 17. 安全设计

### 17.1 Agent 安全

- Agent 使用短期 token 和最小权限。
- Agent 不可读取 broker live secret。
- 工具调用使用 allowlist。
- 外部网页、PDF、作者代码和数据均按不可信内容处理。
- 报告 Agent 不能写指标、门禁或账本。

### 17.2 计算沙箱

因子和论文代码执行在独立容器：

- 非 root。
- 只读输入挂载。
- 结果目录单独挂载。
- 默认无网络。
- CPU、内存、磁盘和执行时间限制。
- 禁止访问 broker、PostgreSQL 主库和 live namespace。

### 17.3 交易安全

- live 发布需要 `ResearchLead + ExecutionOperator` 审批。
- 订单有 notional cap、价格偏离限制、数量限制和频率限制。
- 每笔订单带策略包版本和幂等键。
- kill switch 独立于策略进程。
- 发生行情异常、连接异常、对账差异或风险超限时自动停止新订单。

## 18. 观测、告警和运维

### 18.1 指标

业务北极星：

- 实盘成本后净 P&L。
- 相对基准的增量净 P&L。
- `Net Economic Alpha ROI`：扣除交易、融资、借券、数据和平台成本后，相对于平均实际占用资本的回报。
- 单位风险资本利润、利润容量和边际资金回报。
- 利润对 StrategyPackage、FactorVersion、市场 beta、行业、风格、成本和执行质量的归因。
- A 股单独归因 T+1 不可卖、涨跌停、停牌、公司行动和交易税费造成的 P&L。
- 商品期货单独归因价格收益、展期收益、保证金占用、每日结算、换月成本、滑点和强平风险。

资本与风险护栏：

- 最大回撤、尾部损失、波动率和 Calmar。
- gross/net exposure、杠杆、集中度和流动性。
- 容量、ADV 参与率和市场冲击。
- 风险限额突破、kill switch、订单异常和对账差异。
- 回测、paper 与 live 的 P&L 和成交语义漂移。

没有 live 资金时，paper/shadow 的净经济 alpha 只能作为代理业务指标，并必须在指标名称、报告和 Dashboard 上标记为 `PROXY`。

平台指标：

- 任务成功率、重试率、失败原因。
- queue latency、计算耗时、CPU、内存和存储。
- snapshot 构建成功率和数据延迟。
- 因子计算吞吐和缓存命中率。
- Agent token、cost、失败率和 schema 修复率。

研究指标：

- 候选数、拒绝数、重复数、通过率。
- 每个 gate 的失败分布。
- OOS 保持率、成本后边际贡献和容量。
- 研究到报告的中位耗时。

研究指标是利润的领先指标和资本保护指标，不作为最终业务北极星。

交易指标：

- 订单延迟、拒单率、成交率和滑点。
- 实盘与账本对账差异。
- 风险暴露、敞口、换手和损益。
- 策略包版本和运行实例。

### 18.2 告警

- 数据 schema 变化。
- PIT 快照缺失或时间倒流。
- run fingerprint 不一致。
- 队列积压和连续任务失败。
- 策略包签名无效。
- broker 断连、对账差异和 kill switch 触发。

## 19. 测试策略

### 19.1 单元测试

- IR parser、canonicalizer、type checker 和 unit checker。
- available-time 传播。
- 算子 null/Inf/除零语义。
- A 股日历、涨跌停、停牌、ST、费用和公司行动。
- 商品期货交易所日历、夜盘归属、合约规格、涨跌停、保证金、结算、平今/平昨、交割和换月。
- 组合优化约束和降级逻辑。

### 19.2 合同测试

- Data Gateway 与每个数据供应商。
- Vibe Trading wrapper 输入/输出。
- TradingAgents Agent schema。
- QuantDinger MCP/Strategy API adapter。
- NautilusTrader StrategyPackage adapter。

### 19.3 防泄漏测试

- future row deletion。
- available-time 延迟。
- 未来污染哨兵。
- label 依赖注入。
- 全样本 scaler 检测。
- universe survivorship mutation。

### 19.4 Golden Set

建立固定 golden set：

- 3-5 个经典因子。
- 1 个已知未来函数因子。
- 1 个幸存者偏差因子。
- 1 个修订数据泄漏因子。
- 1 个论文公式复现样例。
- 1 个包含停牌、涨跌停和公司行动的 A 股回测片段。
- 1 个包含夜盘、合约到期、换月、保证金和每日结算的商品期货回测片段。

### 19.5 Replay

每月使用固定 snapshot、代码 SHA、镜像 digest、依赖锁和随机种子进行 replay。关键 artifact hash 不一致则阻断发布并生成差异报告。

## 20. 实施任务拆解

### UI/UX 工作流（跨阶段）

UI/UX 不等待整个后端完成，而是按以下依赖推进：

```text
PRD/角色/用户流程冻结
  -> 信息架构和页面地图
  -> P0 关键流程线框与交互原型
  -> 设计 token、组件规范和页面状态
  -> API schema/mock contract
  -> 前端应用壳层
  -> 研究页面与报告页面
  -> 策略/回测页面
  -> paper/live 运维页面
  -> E2E、可访问性和视觉回归
```

任务拆解：

- `UX-001`：用户角色、核心任务、页面地图和导航结构。
- `UX-002`：研究提案到报告的 P0 交互原型。
- `UX-003`：因子 IR、Gate、OOS、成本和 lineage 的信息呈现规范。
- `UX-004`：设计 token、表格、图表、状态、审批和危险操作组件。
- `UX-005`：Next.js/TypeScript 应用壳层、RBAC 和 mock API。
- `UX-006`：ResearchJob、ResearchBrief、Factor IR、实验监控页面。
- `UX-007`：验证报告、GateDecision、lineage、Alpha Pool 和 StrategySpec 页面。
- `UX-008`：正式回测、paper/live、订单、风险、对账和 kill switch 页面。
- `UX-009`：E2E、响应式、可访问性、视觉回归和错误状态验收。

依赖关系：

- `UX-001`、`UX-002` 在 Phase 0 与数据和架构调研并行，但必须在 PRD 范围冻结后开始。
- `UX-003`、`UX-004` 可与 Factor IR、ValidationPolicy 和 API schema 设计并行。
- `UX-005` 在 API 契约初版冻结后开始，不必等待后端实现完成。
- `UX-006`、`UX-007` 与 Phase 1/2 研究内核并行，通过 mock contract 先开发。
- `UX-008` 等 StrategyPackage、交易状态和风险 API 稳定后开发。
- `UX-009` 在每个页面交付时持续执行，最终在 G6 统一验收。

### Phase 0：规则和数据基线，2-4 周

- [ ] 在 Docker Compose 中固定 PostgreSQL 镜像主版本。
- [ ] 创建 `quant_app` 用户、`quant_platform` 数据库，完成 Alembic migration 和 `pg_isready` 健康检查。
- [ ] 配置 PostgreSQL named volume、最小权限、备份和恢复演练。
- [ ] 固化 `CN_A` 和 `CN_COMMODITY_FUTURES` 的市场边界、首批品种、universe、频率、决策/交易/结算时钟。
- [ ] 定义数据字段合同和 available-time。
- [ ] 接入 A 股日历、证券状态、历史成分和公司行动。
- [ ] 接入商品期货交易所、品种、合约规格、夜盘、结算、保证金、手续费、交割状态和历史合约链。
- [ ] 建立 `MarketRuleRegistry`、市场专属 `CostModel` 和 `ValidationPolicy`。
- [ ] 建立 Raw/Bronze/PIT/Gold 分层。
- [ ] 建立 Snapshot Catalog。
- [ ] 完成两个市场各自的 golden set。
- [ ] 完成 UI 信息架构、P0 页面地图、关键流程原型和设计 token。

### Phase 1：确定性研究内核，6-8 周

- [ ] Factor IR v1 schema。
- [ ] canonical AST 和 hash。
- [ ] operator registry。
- [ ] temporal/type/unit checker。
- [ ] PIT Data Gateway。
- [ ] Factor Executor。
- [ ] Gate 0-2。
- [ ] 五时钟回测账本和商品期货结算时钟。
- [ ] A 股和商品期货的成本、容量、保证金和展期模型。
- [ ] 前端应用壳层、RBAC 和 mock API。

### Phase 2：治理和因子池，4-6 周

- [ ] ExperimentSpec 和预注册。
- [ ] Gate 3-5。
- [ ] FDR、DSR、PBO。
- [ ] Alpha Pool。
- [ ] 因子相关性和消融。
- [ ] 审批、waiver 和 lockbox。
- [ ] signed report。

### Phase 3：研究 Agent，3-5 周

- [ ] Agent Gateway。
- [ ] Intake/Hypothesis/Critic Agent。
- [ ] Vibe Trading adapter。
- [ ] TradingAgents role adapter。
- [ ] ProposalMerger 和统一 `ResearchProposal/EvidenceBundle/RiskMemo` 契约。
- [ ] Adapter 容器隔离、版本固定、feature flag、超时、熔断和降级。
- [ ] ResearchJob、ResearchBrief、Factor IR、验证和报告页面。
- [ ] 候选预算和成本计量。
- [ ] Agent trace 和 evidence refs。

### Phase 4：论文复现和组合策略，4-6 周

- [ ] PDF 页级解析。
- [ ] Paper/Formula/Mapping Agent。
- [ ] faithful/local 双轨。
- [ ] R0-R4 状态。
- [ ] Alpha Pool 组合。
- [ ] 风险模型、优化器和策略报告。

### Phase 5：执行闭环，6-8 周

- [ ] StrategySpec。
- [ ] Strategy Compiler。
- [ ] StrategyPackage v1。
- [ ] NautilusTrader adapter。
- [ ] QuantDinger optional POC adapter；不得进入默认正式回测链路。
- [ ] A 股交易规则和 broker adapter。
- [ ] 商品期货交易规则、合约链和 broker adapter。
- [ ] shadow/paper runtime。
- [ ] StrategySpec、回测、paper/live、风险和对账页面。
- [ ] live 安全和审批。

## 21. 交付验收清单

### 研究内核

- [ ] 相同 run fingerprint 可重算一致。
- [ ] PIT 查询无法绕过 snapshot。
- [ ] 未来函数和修订泄漏测试全部通过。
- [ ] 所有候选都进入试验账本。
- [ ] OOS、成本、容量和多重检验可生成报告。

### Agent

- [ ] Agent 输出只能落入结构化 schema。
- [ ] Agent 不能直接调用 Factor Executor 的写接口。
- [ ] 第三方 Adapter 不能直接写 PostgreSQL、GateDecision、Alpha Pool 或 StrategyPackage。
- [ ] 禁用任一 Vibe/TradingAgents/QuantDinger Adapter 后，确定性研究主链路仍可运行。
- [ ] Agent trace、prompt hash 和 evidence refs 完整。
- [ ] 低置信度映射自动进入人工审批。

### UI

- [ ] P0 页面基于真实 API schema 或 mock contract 可运行。
- [ ] 页面具备 loading、empty、error、permission denied、stale data 和 long-running 状态。
- [ ] 页面不直接访问数据库、对象存储或 broker。
- [ ] 关键审批、发布、kill switch 和交易操作具备权限、二次确认和审计记录。
- [ ] E2E、响应式、可访问性和视觉回归测试通过。

### 策略

- [ ] 只有 Alpha Pool 因子可构建策略。
- [ ] 策略包包含数据、代码、政策、风险和报告 manifest。
- [ ] 策略包签名和内容 hash 可校验。
- [ ] 研究回测和正式回测差异可解释。

### 执行

- [ ] shadow 和 paper 运行不发送真实订单。
- [ ] live 发布具备双人审批。
- [ ] notional cap、kill switch、幂等、对账和恢复测试通过。
- [ ] NautilusTrader 适配器具备回测/paper/live 一致性测试。

## 22. 未决技术决策

以下决策应在 Phase 0 评审时确认：

1. 第一数据供应商及其历史修订/PIT 能力。
2. Iceberg 是否在 MVP 直接采用，或先使用版本化 Parquet。
3. NautilusTrader 的 A 股和商品期货 broker 适配目标及优先顺序。
4. 是否将 QuantDinger 作为内部控制面试点。
5. 研究报告签名密钥的托管方式。
6. 组合风险模型的第一版来源和更新频率。
7. 共享研究环境的最大并发和成本预算。

## 23. 最终技术结论

平台的核心资产应由自研确定性研究内核掌握：

```text
PIT Data Contract
  + Factor IR
  + Validation Policy
  + Experiment Ledger
  + StrategyPackage
```

Vibe Trading 和 TradingAgents 作为可替换的研究 Agent 前端，NautilusTrader 作为可替换但优先采用的交易执行后端，QuantDinger 作为可选的快速控制面。任何第三方平台都不应成为唯一的因子定义、数据事实源、研究账本或实盘发布依据。
