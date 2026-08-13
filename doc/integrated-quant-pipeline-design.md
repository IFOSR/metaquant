# 综合量化研究 Pipeline 方案

版本：v1.0  
日期：2026-08-09  
状态：架构设计

## 0. 来源与综合结论

本方案综合以下三份独立设计：

- [Codex 方案](./codex-quant-pipeline-report.md)
- [Pi 方案](./pi-quant-pipeline-report.md)
- [Kimi 方案](./kimi-quant-pipeline-report.md)

采用的总体策略是：

1. 以 Pi 的“双时间数据、五时钟账本、事件溯源、批处理优先”作为确定性研究内核。
2. 引入 Codex 的时间类型系统、论文复现 R0-R4 分级、负对照、多重检验、lockbox 和异常结果隔离机制。
3. 引入 Kimi 对 A 股涨跌停、停牌、ST、交易成本，以及商品期货合约链、夜盘、保证金、结算、换月和明确 HITL 节点的工程设计。
4. 不采用 LLM 直接生成并执行 Python 策略的模式。LLM 只能提交带证据的研究提案，数值计算和裁决全部由确定性系统完成。
5. 不从自动论文解析开始建设。第一阶段必须先完成 PIT 数据、Factor IR、验证政策和可信回测内核。

## 1. 目标、非目标与范围

### 1.1 目标

建设一个可复现、可审计、可扩展的端到端量化研究平台，支持：

- 人工或 LLM 输入研究假设、市场信息和约束，生成候选因子。
- 输入论文/PDF，抽取公式和实验设定，复现论文并形成候选因子。
- 使用统一 Factor IR 定义、计算和管理所有候选因子。
- 自动执行数据质量、防泄漏、统计显著性、稳定性、相关性、换手和容量验证。
- 将通过门禁的因子组合为策略，并进行考虑真实交易约束的 walk-forward/OOS 回测。
- 输出能够追溯至原始假设、论文页码、数据快照、代码版本和审批记录的研究报告。

平台的最终成功标准是产生可归因、可持续、成本后的真实交易利润，而不是生成多少因子或得到多高的样本内 Sharpe。

产品北极星：

> 平台产生的成本后、风险调整、可归因增量净利润，以及该利润相对于实际占用资本和容量的回报。

建议的业务口径：

```text
Net Economic Alpha ROI
= (策略净 P&L - 基准净 P&L - 资金/借券/平台成本)
  / 平均实际占用资本
```

真实 P&L 必须基于实际成交、手续费、滑点、冲击、融资、借券、数据和平台成本计算，并同时约束最大回撤、尾部损失、容量和风险暴露。绝对利润不能单独作为平台价值，因为高杠杆、市场 beta、不可扩展的小容量或偶然行情都可能制造虚假成功。

其余指标是北极星的领先指标和护栏，而不是最终目标：

- 领先指标：独立 OOS 保持率、成本后边际贡献、容量、可重现率、论文复现准确率和研究交付周期。
- 研究护栏：未来函数、幸存者偏差和伪发现拦截率。
- 生产护栏：回测/模拟/实盘成交语义偏差、风险限额、对账差异、订单异常、kill switch 触发率、净 P&L 漂移和最大回撤。

平台尚未有真实资金时，可以用 paper/shadow 的净经济 alpha 作为代理指标，但必须明确标注为代理，不得将其描述为已实现商业利润。

### 1.2 非目标

- MVP 不负责实盘订单执行。
- MVP 不覆盖中国境外市场、股指/国债期货、期权、数字资产、场外衍生品和跨市场事件策略。
- 不承诺全自动发现可交易 alpha。
- 不允许 LLM 修改门禁、数据快照、实验切分或回测结果。
- 不允许因子定义包含任意 Python、SQL、Shell、网络请求或文件 IO。

### 1.3 MVP 假设

- 市场域固定为 `CN_A` 和 `CN_COMMODITY_FUTURES`，其他市场不进入首阶段正式验收。
- `CN_A` 首先支持上海、深圳市场的人民币普通股，优先覆盖主板和主流指数历史成分；北京市场、科创板、创业板等扩展必须单独完成规则和执行 golden set。
- `CN_COMMODITY_FUTURES` 首先支持上期所、能源中心、大商所、郑商所和广期所中流动性、历史数据和交易规则达标的商品期货品种；不包括股指期货、国债期货、期权和海外合约。
- A 股默认信号时钟为 T 日收盘后，执行时钟为 T+1 下一可交易时点。
- 商品期货默认先做日频：信号使用实际合约或经过声明的连续合约，执行必须映射到实际可交易合约；回测额外处理夜盘归属、每日盯市结算、保证金和换月。
- 数据：行情、财务、证券主数据、历史成分、行业分类、停复牌、涨跌停、ST、退市、期货合约规格、交易时段、结算价、保证金、手续费、主力合约和交割状态具备 point-in-time 版本。
- 数据规模：约 3,000-6,000 只股票和 50-100 个商品期货品种、10 年以上日频数据。
- 研究平台与实盘系统隔离，只输出版本化 `StrategyPackage`。

数据来源采用“外部授权/官方来源 + 自研数据事实层”的模式，而不是直接把任一平台的数据接口当作正式来源：

- Vibe Trading、QuantDinger 的行情和因子接口只用于探索性研究或 POC。
- TradingAgents 的搜索、新闻和市场数据工具只用于证据、假设和风险意见。
- A 股 PIT 行情、财务、历史成分和证券状态，以及商品期货历史行情、结算价和合约链，必须由外部授权数据源经过自研 `Data Gateway` 冻结为 `DatasetSnapshot`。
- A 股和商品期货交易规则、费率、保证金、结算和交割规则必须从交易所/监管规则和 broker/CTP 参数建立版本化 `TradingRuleVersion`。
- NautilusTrader 消费规范化后的历史/实时事件和 `StrategyPackage`，不替代 PIT 数据层和规则注册表。

两类市场不能共享一套默认验证政策：

| 市场域 | 因子研究重点 | 关键验证口径 |
|---|---|---|
| `CN_A` | 价值、质量、盈利修正、动量、反转、流动性、行业/风格中性 | 横截面 Rank IC、分层收益、换手、容量、暴露和 T+1 可交易性 |
| `CN_COMMODITY_FUTURES` | 时序动量、期限结构/展期收益、基差、波动率、库存/宏观、跨品种相对价值 | 时序收益、换月稳定性、保证金占用、杠杆、滑点、极端行情、合约流动性和组合相关性 |

## 2. 核心设计原则

### 2.1 提案与裁决分离

LLM 可以：

- 理解研究意图。
- 解析论文和公式。
- 提出候选因子。
- 推荐字段映射。
- 解释失败原因。
- 生成报告文字。

LLM 不可以：

- 计算正式因子值。
- 决定候选是否通过。
- 修改统计门槛。
- 选择或反复查看 lockbox。
- 生成未经校验的报告数值。
- 直接执行生成的代码。

### 2.2 Factor IR 是唯一执行入口

人工公式、论文公式、自然语言和 Agent 输出必须转换为同一套声明式 Factor IR。所有下游组件只消费 IR，不区分因子来源。

### 2.3 时间正确性默认拒绝

如果无法证明某字段在决策时点已经可得，则该字段不可使用。时间语义必须由数据合同和类型系统传播，而不是依赖研究员手工调用 `shift(1)`。

### 2.4 先验证单因子，再构建组合

候选因子必须先独立通过数据、统计、稳健性、容量和相关性门禁。组合模型不能用于掩盖无效单因子或数据泄漏。

### 2.5 所有尝试都是研究数据

被拒绝、失败、重复和无效的候选同样必须登记。多重检验需要真实的候选总数，不能只保存胜出结果。

## 3. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│ 输入层                                                       │
│ ResearchBrief / Human Form / LLM Conversation / Paper PDF   │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 提案与证据层                                                 │
│ Intake Agent | Paper Agent | Formula Agent | Mapping Agent   │
│ Hypothesis Agent | Critic Agent | Evidence Builder           │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 规范与治理层                                                 │
│ Factor Registry | Factor IR Compiler | Temporal Type Checker │
│ Policy Engine | Experiment Preregistration | Approval Gates  │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 数据与计算层                                                 │
│ PIT Data Gateway | Snapshot Catalog | Data Quality           │
│ Factor Executor | Cache | Artifact Store                     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 验证与策略层                                                 │
│ Factor Validator | Multiple-testing Control | Alpha Pool     │
│ Factor Combiner | Risk Model | Cost Model | Optimizer        │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 回测与审计层                                                 │
│ Five-clock Backtester | Ledger | Attribution | Stress Tests  │
│ Experiment Tracker | Lineage | Signed Report                 │
└─────────────────────────────────────────────────────────────┘
```

控制面采用模块化单体，计算面允许任务级并行。MVP 不拆微服务，优先固定组件契约和结果口径。

### 3.1 第三方平台调用拓扑

系统不是把 Vibe Trading、TradingAgents、QuantDinger 和 NautilusTrader 依次串成固定流水线。自研控制面、Factor IR、PIT Data Gateway、验证门禁和 StrategyPackage 才是主链路；第三方平台通过 Adapter 插入特定阶段：

```text
ResearchBrief
  ├─> Vibe Trading Adapter ─────> CandidateProposal ─┐
  └─> TradingAgents Adapter ────> RiskMemo/Evidence ─┤
                                                     v
                                           自研 ProposalMerger
                                                     |
                                                     v
                                  自研 Factor IR/PIT/Validator
                                                     |
                                                     v
                                          自研 StrategyPackage
                                                     |
                         ┌───────────────────────────┴───────────────────────────┐
                         v                                                       v
             NautilusTrader Adapter                                  QuantDinger Adapter
             正式回测/paper/live                                      可选 POC，默认关闭
```

集成规则：

- Vibe Trading 和 TradingAgents 是并行、可选的研究建议源，不负责正式计算和晋级裁决。
- NautilusTrader 是正式回测、paper 和 live 的默认第三方运行时。
- QuantDinger 仅作为快速 MVP、MCP 或 broker 接入实验，不与自研控制面共同管理正式状态。
- 每个平台运行在独立 Adapter 容器中，只通过版本化 schema 和 artifact 通信，不直接写 PostgreSQL 主库。
- 任一研究 Adapter 下线时，人工输入 Factor IR 的确定性主链路仍须可运行。

## 4. 两条因子挖掘路径

### 4.1 路径 A：研究假设驱动

输入 `ResearchBrief`：

```yaml
market: CN_A
universe: CSI300_PIT
frequency: 1d
decision_time: T_CLOSE+30m
trade_time: T+1_OPEN+5m
horizon: 20TD
hypothesis: 高分歧和强动量共存可能代表短期过度反应
available_data_domains:
  - market_eod
  - analyst_forecast
constraints:
  industry_neutral: true
  size_neutral: true
  max_turnover_annual: 8.0
  max_single_name_weight: 0.01
falsification:
  - 效应只存在于微盘股
  - 成本后收益消失
candidate_budget: 20
```

商品期货研究任务必须显式声明合约链和展期策略，例如：

```yaml
market: CN_COMMODITY_FUTURES
exchange_scope: [SHFE, INE, DCE, CZCE, GFEX]
instrument_scope: commodity_futures
universe: liquid_contracts_pit
frequency: 1d
signal_time: settlement_available
trade_time: next_session_open
contract_selection: main_contract_by_volume
roll_policy:
  method: volume_switch
  min_days_before_expiry: 20
  price_adjustment: none
margin_policy: exchange_and_broker_schedule
cost_policy: fee_slippage_impact_v1
```

处理流程：

1. Intake Agent 将输入转成结构化研究任务。
2. Data Catalog 确认可用字段、历史覆盖、许可和 available-time。
3. Hypothesis Agent 输出经济机制、代理变量、预期方向、反证条件和负对照。
4. Candidate Generator 使用“机制模板 + 有预算 beam search”生成候选。
5. AST 哈希、语义相似度和历史因子相关性用于去重。
6. 候选编译为 Factor IR。
7. 静态门禁拒绝不可执行、不可证伪或时间不安全的候选。
8. smoke run 只检查工程和数据问题，不用于选择 alpha。
9. 预注册候选集合、主指标和 OOS 后执行正式验证。

禁止无限遗传搜索。每个研究任务必须设置候选数、LLM token、计算时长和正式实验次数预算。

### 4.2 路径 B：论文复现驱动

处理流程：

1. 保存原始 PDF、来源、许可和 SHA-256。
2. 生成页级版面对象，保留段落、公式、表格、脚注、图片和 bbox。
3. Paper Agent 提取论文主张和实验设定。
4. Formula Agent 将公式转为 LaTeX、符号表和 AST。
5. Mapping Agent 将论文变量映射到本地 Data Catalog。
6. 每个映射标记为 `exact`、`derived`、`proxy` 或 `unavailable`。
7. 低置信度公式、proxy 和 inferred 步骤必须人工审批。
8. 首先运行 faithful reproduction，复现核心中间表和结果。
9. faithful 分支冻结后才允许创建 local adaptation。
10. 两个分支生成独立 Factor IR、ExperimentSpec 和报告。

复现等级：

- `R0_PARSE_ONLY`：完成解析，尚未运行。
- `R1_LOGIC_REBUILT`：公式和实验逻辑已重建，但数据不完全等价。
- `R2_DIRECTIONAL`：方向和相对排序一致。
- `R3_NUMERICAL`：核心表格在预注册容差内数值复现。
- `R4_AUTHOR_ARTIFACT`：作者代码或数据在封存环境中成功重放。

只有 R2 及以上可以称为“复现成功”。

## 5. Factor IR

Factor IR 必须声明计算逻辑、市场上下文、时间语义和验证政策。

```yaml
schema_version: factor-ir/v1
factor_id: analyst.disagreement_momentum
version: 1.0.0
origin:
  type: research_brief
  source_id: brief_20260809_001
  evidence_refs:
    - brief://brief_20260809_001#hypothesis
economic_thesis:
  mechanism: 高预测分歧下的价格趋势可能存在过度反应
  expected_sign: -1
  horizon: 20TD
market_scope:
  market: CN
  asset_class: equity
  frequency: 1d
  universe_ref: universe://csi300_pit
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
missing_policy:
  min_analyst_count: 3
  max_missing_ratio: 0.20
validation_policy_ref: policy://cn_equity_daily_v1
```

商品期货 Factor IR 的 `market_scope` 必须声明交易所、品种和合约链上下文：

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

### 5.1 算子要求

每个算子必须声明：

- 输入和输出类型。
- 单位传播规则。
- 时序或横截面语义。
- 最大 lookback。
- available-time 传播规则。
- null、Inf 和除零行为。
- 是否允许出现在正式计算路径。

MVP 只允许注册算子，不允许任意 UDF。

### 5.2 时间类型

核心类型：

- `ScalarSeries<T, Unit>`
- `CrossSection<T, Unit>`
- `EventSeries<T>`
- `LabelSeries<T>`
- `UniverseMask`
- `ExposureMatrix`

`LabelSeries` 只能被 Validator 使用，Factor Executor 在类型层面无法引用标签。

### 5.3 身份与版本

```text
expression_hash = SHA256(canonical_AST)
data_contract_hash = SHA256(input fields + availability rules)
context_hash = SHA256(universe + clock + postprocess + policy)
factor_version_id = factor_id + semver + expression_hash + context_hash
run_fingerprint = factor_version_id + snapshot_id + code_sha + image_digest + config_hash
```

相同 `run_fingerprint` 必须产生相同结果。

## 6. 数据时间模型与防泄漏

### 6.1 数据时间字段

所有数据至少保留：

- `event_time`：经济事件实际发生时间。
- `available_time`：研究者最早可获知时间。
- `ingested_at`：平台收到数据的时间。
- `revision_id`：数据修订版本。

查询硬约束：

```sql
available_time <= decision_time
AND snapshot_id = :frozen_snapshot
```

研究任务禁止绕过 PIT Data Gateway 读取裸表。

### 6.2 三层防泄漏

第一层：编译期静态检查

- 负 lag。
- forward fill。
- label 依赖。
- 全样本标准化。
- 无界窗口。
- 数据字段可用时间晚于决策时间。

第二层：PIT 数据访问

- 财务数据按真实公告时间。
- 历史指数成分、行业和证券状态按点时版本。
- 修订数据不覆盖历史可见版本。
- 包含退市证券和 delisting return。

第三层：动态对拍

- 删除未来 N 日数据后，历史因子值必须不变。
- 延迟一个时点重新计算，验证 t 日值只依赖合法历史。
- 注入未来污染哨兵字段，因子结果必须不受影响。
- 随机选择决策时点执行 time-travel replay。

任一层失败，候选进入 `QUARANTINED`，不得继续回测。

## 7. 状态机与数据流

### 7.1 独立状态机

Gate G0 拒绝用一个线性 `ResearchState` 同时表达协调任务、实验、复现、发布和部署。实现必须拆分为：

- `ResearchJob`：`DRAFT -> READY -> RUNNING -> SUCCEEDED/FAILED/CANCELLED -> ARCHIVED`，并允许 `WAITING_INPUT/BLOCKED_POLICY`。
- `ResearchBriefVersion`：`DRAFT -> FROZEN -> SUPERSEDED`。
- `ExperimentSpec`：`DRAFT -> PREREGISTERED -> SUPERSEDED/CLOSED`。
- `ExperimentRun`：`QUEUED -> RUNNING -> SUCCEEDED`，或进入 retryable/terminal failure、policy block、quarantine、non-reproducible、cancelled。
- `Attempt`、`Replication`、`PackageRelease` 和 `DeploymentRun` 使用各自状态机。

完整状态和迁移约束见 `docs/architecture/g0-contract-baseline.md`；客户端只能展示服务端状态，不得自行推进状态。
- `QUARANTINED`
- `CANCELLED`

### 7.2 Artifact 数据流

```text
Input/PDF
 -> EvidenceBundle
 -> HypothesisSpec/PaperExperimentSpec
 -> FactorIR
 -> DatasetSnapshot
 -> FactorArtifact
 -> ValidationBundle
 -> GateDecision
 -> StrategySpec
 -> Orders/Fills/Ledger
 -> BacktestBundle
 -> SignedResearchReport
```

Artifact 使用内容哈希寻址，只追加、不覆盖。失败重跑产生新的 attempt。

## 8. 实验预注册和因子门禁

门禁参数由版本化 `ValidationPolicy` 管理，不在代码中写死。`CN_A` 和 `CN_COMMODITY_FUTURES` 必须使用不同的市场政策；同一市场内再按频率、因子类型和交易方向细分。

### Gate 0：静态与时间安全

必须全部通过：

- IR、类型和单位校验。
- 数据合同和 available-time 校验。
- 无标签依赖、负 lag、未来回填和全样本拟合。
- universe、benchmark、horizon 和执行时钟明确。

### Gate 1：数据质量

- 覆盖率、横截面有效样本和历史长度。
- 主键、日历、单位、币种、公司行动和证券状态。
- NaN、Inf、常数值、极值和 stale 数据。
- 相同 run fingerprint 重算一致。

覆盖率阈值不统一写死为 90%。事件型和基本面因子允许使用专属政策，但缺失模式必须可解释。

### Gate 2：预测能力

正式报告至少包括：

- Pearson IC、Rank IC、ICIR。
- Newey-West 调整 t 值。
- 1/5/10/20/60 日 IC decay。
- 分层收益、单调性和 Top-Bottom spread。
- Fama-MacBeth 或控制行业、市值、beta 的横截面回归。
- 年份、市场状态、行业、市值和流动性子样本。

### Gate 3：稳健性和伪发现

- 参数邻域测试。
- 数据源和 universe 扰动。
- winsorize、中性化和执行价格敏感性。
- 随机标签、时间错位和负对照。
- Benjamini-Hochberg FDR。
- Deflated Sharpe Ratio。
- Probability of Backtest Overfitting。
- 所有候选和调参次数进入试验账本。

### Gate 4：独立性、成本和容量

- 与 Alpha Pool 因子的截面相关和因子收益相关。
- 正交化后的增量 IC。
- 换手和信号半衰期。
- 成本后收益。
- ADV 参与率、冲击、涨跌停、停牌和融券约束。
- AUM 容量曲线。

### Gate 5：晋级

采用硬门槛加评分卡：

- 硬门槛：时间安全、数据质量、OOS 方向、伪发现控制和最低容量。
- 评分卡：效应强度 25%、稳定性 25%、独立性 20%、成本后价值 20%、可解释性 10%。
- 过度优秀的结果不直接通过，而进入 `QUARANTINED` 调查。
- 门禁例外必须记录审批人、理由、范围和到期时间。

## 9. 策略构建

### 9.1 Alpha Pool

只有通过门禁的 FactorVersion 才能进入 Alpha Pool。池内记录：

- 因子方向。
- 适用 universe 和 horizon。
- 验证政策。
- OOS 指标。
- 与现有因子相关性。
- 成本、容量和失效条件。
- 当前生命周期状态。

### 9.2 因子组合

MVP 使用稳健 IC 加权加 shrinkage：

```text
raw_weight_i = clip(EWMA(train_IC_i) / train_IC_vol_i)
weight = shrink(raw_weight, equal_weight, lambda)
weight = constrained_normalize(weight)
```

要求：

- 只使用训练窗估计权重。
- 权重在下一个 OOS fold 冻结。
- 单因子设置最大权重。
- 等权组合作为必须保留的基线。
- 组合必须进行因子消融和边际贡献分析。

非线性模型作为后续能力。ML 组合本身视为复合因子，重新经过预注册和门禁。

### 9.3 组合优化

```text
maximize alpha' w
       - lambda_risk * w'Cov*w
       - lambda_tc * Cost(w - w_prev)
       - lambda_conc * ConcentrationPenalty(w)
```

约束：

- 单票、行业、风格和 beta。
- 净/总敞口。
- tracking error。
- ADV 参与率和换手预算。
- 持仓数量和最小交易单位。
- 停牌、涨跌停、ST 和融券可用性。

优化失败必须返回冲突诊断，并按预注册规则降级到可行基线，禁止静默放宽约束。

## 10. 五时钟回测与商品期货结算

回测账本显式区分：

1. 数据可用时钟。
2. 信号时钟。
3. 订单时钟。
4. 成交时钟。
5. 收益和估值时钟。

商品期货额外增加结算时钟，用于每日结算价、盯市盈亏、可用资金、保证金占用和强平检查；它不能被收盘估值时钟替代。

事件顺序：

```text
数据到达
 -> 构建点时 universe
 -> 计算因子
 -> 生成目标仓位
 -> 检查可交易状态
 -> 下单
 -> 成交模型生成 fills
 -> 更新现金和持仓
 -> 处理公司行动
 -> 估值和归因
```

### 10.1 A 股执行约束

- 涨停不可买、跌停不可卖。
- 停牌不成交。
- ST 和上市天数过滤使用历史状态。
- 印花税只在卖出侧计算，并按日期版本化。
- 佣金、过户费、点差和最低滑点。
- 平方根市场冲击模型。
- 最小交易单位和无法成交的订单顺延规则。

### 10.2 商品期货执行约束

MVP 需要显式实现：

- 研究合约与实际可交易合约分离；连续合约只用于信号和研究序列，订单必须落到具体合约。
- 合约乘数、最小变动价位、报价单位、到期日、最后交易日、交割月和交易所归属。
- 日盘、夜盘、跨午夜交易日归属、集合竞价、休市和节假日规则。
- 涨跌停、手续费、平今/平昨、保证金比例、涨跌停板调整和每日结算。
- 盯市盈亏、结算价、可用资金、追加保证金、强平和最大持仓约束。
- 主力/次主力识别和换月：记录换月原因、换月时间、旧/新合约、价差、手续费和滑点。
- 到期前退出和交割禁止策略；除非经过单独审批，MVP 不模拟实物交割。
- 合约流动性、盘口深度、成交量参与率和冲击成本。

商品期货回测输出必须同时区分价格收益、展期收益、保证金占用和资金成本、手续费/滑点/冲击/换月成本，以及每日结算现金流、浮盈浮亏和强平风险。

### 10.3 市场规则注册表

所有市场规则进入版本化 `TradingRuleVersion`，由 `market + instrument + effective_time` 选择，不允许在回测代码中硬编码。至少包括：

- `calendar`、`sessions`、`auction` 和跨日归属。
- `price_limit`、`tick_size`、`lot_size`、`contract_multiplier`。
- `fee_schedule`、`stamp_duty`、`margin_schedule`、`settlement_rule`。
- `tradability_rule`、`position_limit`、`delivery_rule` 和 `roll_policy`。

任何规则缺失或版本不确定，研究任务进入 `BLOCKED_POLICY`，不能用默认值继续。

### 10.4 Walk-forward

- 训练、验证和测试按时间滚动。
- 标签重叠时使用 purged split 和 embargo。
- scaler、neutralizer、风险模型、成本参数和因子权重只在训练窗拟合。
- 最终 lockbox 在晋级前只打开一次。
- OOS 失败后重新调参必须创建新研究版本和更晚的 lockbox。

报告同时展示：

- gross/net 收益。
- Sharpe、Sortino、最大回撤和 Calmar。
- IC、分层和各 fold 分布。
- 换手、成本、风险暴露和容量。
- 不可成交、失败期和策略降级。
- 因子消融和收益归因。

## 11. Agent 与 HITL

### 11.1 Agent 角色

- Intake Agent：规范化研究输入。
- Hypothesis Agent：生成可证伪假设和候选。
- Paper Agent：解析论文主张和实验设定。
- Formula Agent：公式到 AST。
- Mapping Agent：论文变量到本地字段映射。
- Critic Agent：独立检查歧义、重复、泄漏和反例。
- Result Analyst Agent：解释结构化指标。
- Report Agent：生成叙事，不生成数值。

Agent 之间不通过自由对话传递事实。所有状态和结果必须写入 Registry 或 Artifact Store。

### 11.2 HITL 节点

默认必须人工确认：

1. 关键研究假设、候选预算和 OOS 预注册。
2. 低置信度论文公式。
3. proxy、derived 和 inferred 数据映射。
4. 门禁 waiver。
5. 打开最终 lockbox。
6. 因子进入 Alpha Pool。
7. 策略发布到 paper trading 或实盘系统。

审批必须记录人员、时间、理由、对象版本和前后 diff。

## 12. 技术栈

### 12.1 MVP

- Python 3.12。
- Pydantic v2：领域契约和 schema。
- Polars/Arrow：因子计算。
- DuckDB：本地探索和中小规模计算。
- Parquet + Apache Iceberg：PIT 数据和不可变快照。
- PostgreSQL（Docker Compose）：Registry、状态机、审批和 lineage。
- Dagster：资产 DAG、分区、重试和 backfill。
- FastAPI：控制面 API。
- MLflow：实验参数、指标和 artifact 索引。
- S3/MinIO：内容寻址 Artifact Store。
- CVXPY + OSQP：组合优化。
- PyMuPDF/Docling：PDF 版面解析。
- OpenTelemetry + Prometheus/Grafana：观测。
- Docker Compose + uv lock：可复现运行环境，PostgreSQL 与其他依赖统一容器化。

不在 MVP 同时引入 Spark、Ray、Temporal 和图数据库。规模或长事务需求明确后再扩展。

### 12.2 核心 API

```text
POST /v1/research-jobs
POST /v1/papers
GET  /v1/papers/{id}/evidence
POST /v1/factors:compile
POST /v1/experiments:preregister
POST /v1/experiments/{id}:run
GET  /v1/experiments/{id}/validation
POST /v1/approvals
POST /v1/strategies
POST /v1/backtests
GET  /v1/reports/{report_id}
GET  /v1/lineage/{artifact_id}
```

所有写接口要求：

- `Idempotency-Key`
- actor 由 OIDC/Bearer 认证主体注入，不接受 body 覆盖
- reason
- parent artifact
- budget
- 修改已有聚合时的 `If-Match`

## 13. 元数据、版本和审计

核心实体：

- `ResearchJob`
- `SourceArtifact`
- `PaperSource`
- `EvidenceRef`
- `Hypothesis`
- `FactorSpec`
- `CompiledIR`
- `DatasetSnapshot`
- `ExperimentSpec`
- `FactorRun`
- `ValidationBundle`
- `GateDecision`
- `StrategySpec`
- `BacktestRun`
- `Approval`
- `LLMTrace`
- `SignedResearchReport`

必须记录：

- 数据 snapshot。
- Git SHA 和容器 digest。
- 依赖锁文件 hash。
- 随机种子。
- 门禁政策版本。
- LLM provider、模型、prompt hash、检索语料版本、token 和成本。
- 所有失败和被拒候选。

报告 manifest 对全部 artifact hash 计算 Merkle root 并签名。

## 14. 失败、安全和成本

### 14.1 失败处理

- 输入不完整：`WAITING_INPUT`。
- 数据许可、时间泄漏或预算违规：`BLOCKED_POLICY`。
- 数据 schema 漂移：隔离数据和下游结果。
- 基础设施失败：幂等重试，最多三次。
- 统计门禁失败：记录研究结论，不自动调参到通过。
- 论文复现失败：保留差异分解和失败报告。
- 重算 hash 不一致：`NON_REPRODUCIBLE`，阻断发布。

### 14.2 安全

- PDF 和作者代码视为不可信输入。
- Agent 使用最小权限和短期凭证。
- 数据和网络 egress 使用 allowlist。
- LLM 不接收受限原始行情、客户持仓或交易凭证。
- 外部代码在无网络、非 root、只读输入和资源限额容器中运行。
- 禁止 `eval` 和任意 Python 直通。
- 数据许可标签沿 lineage 传播。

### 14.3 成本

- 静态检查和数据可行性检查优先。
- smoke run 只排查工程问题。
- cheap gate 通过后才运行完整评估。
- 相同 PDF、IR 子表达式和数据快照复用缓存。
- 小模型用于抽取和分类，歧义任务升级强模型。
- 超预算进入人工审批，不自动追加资源。
- 成本按研究任务、候选和通过因子归集。

## 15. 实施路线图

### Phase 0：数据和规则基线，2-4 周

- 在 Docker Compose 中固定 PostgreSQL 镜像主版本，创建应用用户和数据库，完成 schema migration、健康检查、备份和恢复演练。
- 定义三时间字段和 PIT 数据合同。
- 完成 A 股历史 universe、证券状态、公司行动和交易规则校验。
- 完成商品期货交易所、品种、合约规格、交易时段、结算、保证金、手续费、交割状态、主力链和换月规则校验。
- 为两个市场分别建立 `TradingRuleVersion`、`CostModel`、`ValidationPolicy` 和 golden set。
- 定义 Factor IR v1、算子语义和验证政策。
- 选择 3-5 个经典 A 股因子和 3-5 个经典商品期货因子作为 golden set。
- UI/UX 并行完成用户角色、信息架构、页面地图、P0 用户流程原型、设计 token、页面状态矩阵和前后端 mock contract。

退出标准：

- 时间旅行测试通过。
- 相同快照重算一致。
- 已知未来函数 mutation 100% 被拦截。
- P0 原型覆盖 ResearchJob、Factor IR、GateDecision、报告和 lineage 主流程，并通过产品评审。

### Phase 1：确定性研究内核，6-8 周

- Factor Registry。
- IR 编译器和 Temporal Linter。
- PIT Data Gateway。
- Factor Executor 和 Validator。
- 五时钟回测账本，以及商品期货结算时钟。
- A 股和商品期货各自的成本模型、容量模型和审计报告。
- 前端应用壳层、登录/RBAC、市场域切换、全局任务导航和 mock API。
- ResearchJob、ResearchBrief、候选列表、Factor IR 和编译错误页面；先基于 mock contract 开发，再切换真实 API。

输入先采用人工编写 Factor IR。

### Phase 2：假设驱动入口，3-5 周

- ResearchBrief。
- Hypothesis Agent 和 Critic Agent。
- 机制模板与候选预算。
- Agent Gateway 和结构化输出。
- HITL 审批 CLI。
- 研究运行监控、候选详情、预算消耗、审批节点、验证结果和基础报告页面。
- 将页面状态与 `ResearchJob`、事件流、GateDecision 和 `EvidenceBundle` schema 对齐。

### Phase 3：论文复现入口，4-6 周

- PDF 证据抽取。
- Formula AST。
- VariableMapping 和 ReplicationDelta。
- R0-R4 复现等级。
- faithful/local 双轨实验。

### Phase 4：策略和生产治理，6-8 周

- Alpha Pool。
- 因子组合和组合优化。
- 容量与风险模型。
- lockbox 和多重检验账本。
- 签名报告、RBAC 和 paper trading。
- Alpha Pool、StrategySpec、正式回测、风险归因和报告 lineage 页面。

暂缓：

- 自动实盘发布。
- 高频研究。
- 端到端 AutoML。
- 强化学习策略搜索。
- 自我修改 Agent。

## 16. 验收指标

### 正确性

- Golden factors 与基准实现误差在 `1e-10` 或业务容差内。
- 已知未来函数、幸存者偏差、同收盘成交和修订泄漏拦截率 100%。
- 相同 run fingerprint 的关键 artifact hash 一致。

### 论文复现

- 关键公式和变量抽取准确率不低于 95%。
- 每个关键结论具备页码/bbox EvidenceRef。
- faithful reproduction 与 local adaptation 不混淆。

### 研究治理

- 正式实验预注册率 100%。
- 候选和调参登记率 100%。
- 所有 waiver 有审批、范围和到期时间。
- lockbox 非法重复打开次数为 0。

### 工程

- 3,000 股票、10 年日频，以及 50-100 个商品期货品种、10 年日频，单个中等因子计算和基础评估 P95 小于 10 分钟。
- 20 个标准因子的完整流程在目标集群小于 60 分钟。
- 基础设施任务成功率不低于 99%。
- 月度 replay 成功率不低于 99.5%。

### 商业价值与研究护栏

- 平台产生的真实成本后增量净利润和 Net Economic Alpha ROI 是最终业务 KPI。
- 真实利润必须能归因到 StrategyPackage、FactorVersion、数据快照、交易成本和风险暴露。
- paper/shadow 净经济 alpha 只能作为 live 之前的代理 KPI。
- 最大回撤、尾部损失、容量和风险限额是利润 KPI 的硬约束。
- 不以正 alpha 数量或样本内 Sharpe 作为最终平台 KPI。

### 市场覆盖与交易正确性

- `CN_A` 和 `CN_COMMODITY_FUTURES` 各自拥有独立的规则、数据、成本、容量和验证政策。
- A 股 golden set 覆盖 T+1、涨跌停、停牌、ST、公司行动、历史 universe 和交易成本。
- 商品期货 golden set 覆盖实际合约映射、夜盘归属、合约到期、换月、保证金、每日结算、平今/平昨和交易成本。
- 任何未通过市场规则 golden set 的品种或合约不能进入 paper/live。

### 研究价值

- 论文首次复现耗时中位数降低至少 50%。
- OOS 方向保持率达到团队预设基线。
- 研究指标用于预测利润和保护资本，不替代利润 KPI。

## 17. 端到端示例

输入一篇关于标准化意外盈利 SUE 的论文，并指定在 A 股中证 800 上进行本地验证。

1. Paper Agent 保存 PDF hash，并抽取 SUE 公式、样本区间和月度调仓设定。
2. Formula Agent 生成 AST，证据指向论文页码和公式编号。
3. Mapping Agent 将 EPS 映射到 PIT 财务数据，按真实公告时间确定 available-time。
4. 论文使用美股数据，本地使用 A 股数据，因此创建：
   - `faithful_reproduction`
   - `local_adaptation`
5. 研究员审批市场、行业分类和成本差异。
6. 编译器生成 Factor IR，静态检查确认无负 lag 和 label 依赖。
7. 动态 time-travel test 验证未来数据删除后历史因子值不变。
8. 预注册主 horizon、候选总数、walk-forward 和最终 lockbox。
9. Validator 输出 IC、ICIR、分层、稳定性、相关性、换手、容量和 FDR/DSR/PBO。
10. 通过门禁后进入 Alpha Pool，并与价值、质量和动量因子做稳健 IC 加权。
11. Optimizer 施加行业、市值、单票、换手和 ADV 约束。
12. Backtester 按五时钟模拟涨跌停、停牌、佣金、印花税、点差和市场冲击。
13. 报告展示 faithful/local 两条结果、所有 fold、gross/net、成本、容量、失效期和因子消融。
14. 报告中的每个数字可以反向定位到 run、IR、数据快照和 PDF 证据。

商品期货研究分支必须额外执行：

1. 根据交易所、品种和历史流动性构建 PIT 合约 universe。
2. 保存连续合约构造、主力切换和价差处理规则。
3. 因子计算使用结算价或明确声明的收盘价，并校验夜盘归属和 available-time。
4. 回测把信号映射到具体可交易合约，模拟成交量参与率、手续费、滑点和换月。
5. 逐日计算盯市盈亏、保证金占用、可用资金和追加保证金风险。
6. 报告拆分价格收益、展期收益、资金成本、交易成本、换月损益和极端行情损失。

## 18. 最终决策

建议项目按以下顺序推进：

1. 先建立可信的 PIT 数据和回测地基。
2. 再建立 Factor IR、验证门禁和研究账本。
3. 然后接入人工假设路径。
4. 再接入论文复现路径。
5. 最后开放 LLM 批量候选生成和策略组合自动化。

如果顺序倒置，LLM 只会更快地产生不可审计、不可复现和可能含未来函数的结果。平台的核心资产不是 Agent 数量，而是统一的时间语义、研究契约和可重放证据链。
