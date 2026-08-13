# 端到端量化研究 Pipeline 架构设计

## 0. 执行摘要

本方案建设一个“LLM 负责提出可解释候选，确定性系统负责证明候选是否成立”的量化研究平台。平台支持两类入口：

1. 研究人员或 LLM 输入研究假设、市场信息与约束，系统基于可用数据目录和算子空间自动挖掘候选因子。
2. 输入论文/PDF，系统解析正文、公式、图表与实验设定，将论文主张映射为可执行、可验证、可追溯的候选因子。

两条路径在 `FactorSpec` 处汇合，后续统一经过静态检查、时间语义检查、数据校验、点时数据装配、因子计算、统计验证、容量与交易约束评估、组合构建、walk-forward/out-of-sample 回测和可审计报告生成。

核心设计取舍如下：

- **研究提案与研究裁决分离**：LLM 可以提案、解释、映射公式和修复草案，但不能自行改变数据、门槛、样本切分或回测结果。
- **Factor IR 是唯一执行入口**：自然语言、Python 片段和论文公式都必须先编译为受限、类型化、带时间语义的 IR，禁止任意代码直接进入生产计算。
- **时间正确性优先于算力效率**：数据使用 point-in-time/available-time 语义；若无法证明某字段在决策时点可得，则默认不可用。
- **先单因子证据，后策略收益**：候选先通过独立门禁，再参与组合，避免用复杂组合掩盖单因子无效和数据泄漏。
- **MVP 收敛范围**：先做日频股票横截面研究，不在 MVP 同时覆盖高频、期权、数字资产和跨市场事件驱动；架构预留扩展点。

---

## 1. 目标、非目标与明确假设

### 1.1 目标

平台需要实现：

- 从自然语言研究假设或论文/PDF 自动形成候选因子，并明确候选的经济直觉、公式、数据依赖、适用市场、调仓频率和预期失效条件。
- 对所有候选执行统一、可复现、可审计的验证流水线。
- 系统性防止未来函数、幸存者偏差、标签泄漏、数据修订泄漏、参数选择偏差和回测过拟合。
- 输出从原始输入到最终回测结论的完整 lineage：谁、何时、基于什么材料、使用什么数据快照、运行什么代码、得到什么结果、经过哪些人工审批。
- 支持失败恢复、缓存复用、并行实验、预算控制和研究资产沉淀。

### 1.2 非目标

- 不承诺全自动发现可交易 alpha；系统目标是提高研究吞吐和降低伪发现率。
- 不允许 LLM 直接运行任意 Python、SQL、Shell 或访问未授权数据。
- 不把回测最高收益作为候选选择的唯一标准。
- MVP 不做实盘 OMS/EMS；生产阶段通过受控策略发布接口对接交易系统。
- 不用一个“大 Agent”包办所有工作；Agent 只协调边界清晰的工具和工作流。

### 1.3 明确假设

为使方案可落地，首期采用以下假设：

- 资产范围：A 股或美股日频股票横截面，单市场单币种；示例按 A 股描述。
- 决策时间：交易日收盘后生成信号，下一交易日开盘后或 VWAP 执行。
- 基础数据：复权行情、交易日历、证券主数据、停复牌/涨跌停/ST 状态、行业分类、财务报表及其实际公告时间、分析师或新闻等可选另类数据。
- 数据平台能够保留原始版本、修订版本及 `event_time`、`available_time`、`ingested_at` 三类时间。
- 研究集群可使用容器化 Python 任务和列式存储；结果规模允许先以 Parquet/Iceberg + PostgreSQL 实现。
- 每个实验都绑定固定 universe、benchmark、持有期、切分方案和成本模型；修改任何一项都产生新实验版本。
- 统计门槛是按资产类别和策略频率配置的政策，不由候选生成 Agent 临时决定。

---

## 2. 总体架构与组件边界

### 2.1 分层架构

```text
┌────────────────────────────────────────────────────────────────────┐
│ 入口层                                                             │
│ Research Brief / Market Context / Constraints / Paper PDF          │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ 提案层（允许 LLM）                                                  │
│ Brief Normalizer | Paper Parser | Hypothesis Agent | Formula Mapper│
│ Candidate Generator | Evidence/Citation Builder                    │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ 规范层（确定性为主）                                                │
│ Factor Registry | Factor IR Compiler | Type/Unit Checker           │
│ Temporal Linter | Data Contract Resolver | Policy Engine           │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ 数据与计算层（确定性）                                              │
│ PIT Data Service | Snapshot Catalog | Feature Executor             │
│ Quality Service | Cache | Distributed Compute                      │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ 验证与策略层（确定性）                                              │
│ Factor Validator | Multiple-testing Control | Capacity Model       │
│ Factor Combiner | Portfolio Optimizer | Risk/Cost Model            │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ 回测与审计层（确定性）                                              │
│ Walk-forward Backtester | Attribution | Report Generator           │
│ Experiment Tracker | Lineage/Audit Store | Approval Gates          │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件及边界

| 组件 | 责任 | 明确不负责 |
|---|---|---|
| Research Intake API | 接收 brief、约束、附件，创建研究任务 | 不解释策略优劣 |
| Paper Ingestion Service | PDF/OCR/版面解析、章节/公式/表格/引用定位 | 不直接执行论文代码 |
| Proposal Agents | 形成假设、候选公式、经济机制、反证条件 | 不读取未来数据，不决定是否通过 |
| Factor Registry | 保存 FactorSpec、版本、依赖、状态、owner | 不计算因子 |
| Factor IR Compiler | AST 构建、类型/单位检查、规范化、生成执行计划 | 不接受任意 Python `eval` |
| Temporal Safety Service | 校验 available-time、滞后、窗口和标签隔离 | 不根据收益表现放宽规则 |
| PIT Data Service | 按决策时点返回当时可见的数据视图 | 不返回“最新修订值”代替历史值 |
| Feature Executor | 执行 IR、缓存中间结果、输出因子矩阵 | 不做候选选择 |
| Factor Validator | 计算 IC、分层、换手、稳定性、相关性、容量等 | 不构建最终持仓 |
| Strategy Builder | 因子组合、风险中性、约束优化、仓位生成 | 不改写原始因子值 |
| Backtest Engine | 事件时序、成交、成本、公司行动、账本 | 不用全样本拟合参数 |
| Experiment/Lineage Store | 记录输入、数据、代码、环境、指标、审批 | 不保存不可追踪的手工结果 |
| Report Service | 从结构化结果生成 HTML/PDF/Markdown 报告 | 不由 LLM杜撰数值或结论 |
| Orchestrator | DAG 调度、重试、超时、HITL 门控和预算管理 | 不包含研究计算逻辑 |

### 2.3 确定性实现与 LLM 边界

**必须确定性实现：**

- Factor IR 解析、类型系统、单位检查、算子白名单和执行计划。
- 数据快照、PIT join、交易日历、公告可用时间、复权和 universe 构造。
- 去未来函数、标签隔离、purging/embargo、样本切分。
- 全部指标计算、统计检验、多重检验校正、门禁裁决。
- 成本、风控、组合优化、订单仿真、回测账本和归因。
- 实验 ID、哈希、版本、审计日志、权限和预算限额。
- 报告中的数值表格与图形；LLM 只能基于结构化结果生成文字摘要。

**适合交给 LLM：**

- 从 brief 中消歧研究意图并生成多种可证伪假设。
- 从论文段落、公式和表格中抽取设定，提出语义映射候选。
- 在受控数据字典中选择可能字段，给出映射置信度和证据位置。
- 生成候选因子变体、经济解释、失效条件、推荐消融实验。
- 对失败日志进行归类并提出修复草案。
- 把确定性结果转换为人类可读的研究摘要，但不得更改结论标签。

---

## 3. 两条因子挖掘路径

### 3.1 路径 A：研究假设/市场信息/约束驱动

#### 输入对象 `ResearchBrief`

至少包括：

- 市场、资产类别、universe、频率、持有期和执行时点。
- 自然语言假设，例如“机构调研热度上升但价格反应不足可能预测未来 20 日收益”。
- 可用数据域和禁用数据域。
- 风险、换手、容量、行业暴露、可解释性和时延约束。
- 目标不是“最大化样本内收益”，而是指定验证任务，例如“检验信息扩散速度与拥挤度的交互效应”。

#### 流程

1. **Brief 规范化**：LLM 把自然语言转为结构化问题；缺失的关键字段由默认政策补齐并标记 `assumed`。
2. **数据可行性检查**：确定性服务查询 Data Catalog，返回字段覆盖期、频率、延迟、许可和质量等级。
3. **机制拆解**：Hypothesis Agent 输出“原因 → 可观测代理变量 → 预期方向 → 时间尺度 → 反证条件”。
4. **候选生成**：在受限算子空间中生成少量有差异的候选，不进行无限遗传搜索。建议每轮 10–30 个，分为基线、机制变体、稳健变体和负对照。
5. **候选去重**：基于规范化 AST 哈希、历史因子相关性草测和语义 embedding 去重。
6. **编译为 FactorSpec**：每个候选必须具备公式、输入字段、时间语义、缺失值政策、中性化方法和证据。
7. **静态门禁**：无法映射数据、含禁用算子、缺少 lag、单位不一致或表达不可证伪者直接拒绝。
8. **低成本筛选**：在缩短区间/抽样 universe 上做 smoke test，仅用于发现工程错误，不据此判断 alpha。
9. **正式验证**：在预注册切分和门槛下运行完整验证。

#### 搜索策略取舍

不采用纯遗传编程遍历海量表达式，因为其多重检验成本和伪发现率难以审计。采用“机制模板 + 有预算的 beam search”：

- 模板由趋势、反转、质量、估值、流动性、事件扩散、预期差等经济机制定义。
- LLM 负责提出模板参数化和组合理由。
- 编译器只接受白名单算子。
- 每个研究任务有候选预算和“试验次数账本”，所有淘汰候选也被记录。
- 进入正式 OOS 的候选数量在预注册时冻结。

### 3.2 路径 B：论文/PDF 解析与复现驱动

#### 解析产物

Paper Ingestion Service 输出：

- 文档元数据：标题、作者、年份、DOI/arXiv、版本、文件 SHA-256。
- 页级版面对象：章节、段落、脚注、公式、表格、图、附录、参考文献。
- 公式的 LaTeX/MathML、页面坐标和周边解释文本。
- 样本范围、市场、筛选条件、数据源、变量定义、滞后、再平衡频率、成本假设、回归规格、评价指标。
- 作者提供的代码/数据链接及其内容哈希；外部资源必须被下载到隔离区并经过许可和安全检查。

#### 复现流程

1. **文档指纹与版本冻结**：原始 PDF、OCR 结果、解析器版本和页面图片均保存哈希。
2. **声明抽取**：LLM 输出 `Claim` 列表，例如“过去 12 个月收益跳过最近 1 个月预测未来 1 个月收益”。
3. **公式抽取与校对**：OCR/公式模型抽取 LaTeX；规则检查括号、上下标、求和边界；低置信度公式进入人工确认。
4. **实验设定抽取**：形成 `PaperExperimentSpec`，所有字段带页码/表号/公式号证据。
5. **本地数据映射**：将论文变量映射到 Data Catalog；每个映射记录 exact/derived/proxy/unavailable 和置信度。
6. **差异登记**：无法完全一致的市场、样本期、字段、行业分类或执行价格进入 `ReplicationDelta`，禁止静默替换。
7. **基线复现**：优先复现论文核心表/图，不先做“改进版”。比较方向、数量级、排序关系和误差带。
8. **接受度裁决**：若基线无法在合理容差内复现，候选可继续作为“启发式改编”，但不能标记为“已复现”。
9. **本地化与扩展**：在冻结基线之后，才允许改变市场、样本、成本模型或公式形成候选因子。
10. **统一 FactorSpec**：论文基线与扩展版本均进入统一 IR 和后续门禁。

#### 复现等级

- `R0_PARSE_ONLY`：已解析，未运行。
- `R1_LOGIC_REBUILT`：公式和实验逻辑已重建，数据不完全等价。
- `R2_DIRECTIONAL`：关键结果方向与相对排序一致。
- `R3_NUMERICAL`：核心表格在预设容差内数值复现。
- `R4_AUTHOR_ARTIFACT`：使用作者代码/数据成功复现并封存环境。

只有 `R2` 以上可在报告中称“复现成功”；`R1` 只能称“逻辑重建”。

---

## 4. 统一 Factor IR / DSL / Schema

### 4.1 设计原则

- 声明式、可序列化、可哈希、可静态分析。
- 时间语义是一等公民，不依赖开发者记忆手工 `shift(1)`。
- 表达式和实验上下文分离：相同表达式在不同 universe/频率/中性化下是不同 `FactorVersion`。
- IR 只表达因子，不嵌入任意网络请求、文件 IO 或动态代码。
- 所有算子有输入类型、输出类型、单位、跨截面/时序语义、lookback 上界和空值行为。

### 4.2 示例 Schema

```yaml
factor_spec_version: "1.0"
factor_id: "fac_price_volume_divergence"
version: "1.2.0"
name: "价格成交量背离"
status: "DRAFT"
owner: "research_team_alpha"
origin:
  type: "research_brief"       # research_brief | paper | manual
  source_id: "brief_20260809_001"
  evidence_refs:
    - "brief://brief_20260809_001#hypothesis"
economic_thesis:
  mechanism: "价格上涨但成交参与度下降，趋势确认不足"
  expected_sign: -1
  horizon: "20TD"
  falsification:
    - "高流动性股票中效应消失"
market_scope:
  asset_class: "equity"
  market: "CN"
  frequency: "1d"
  universe_ref: "universe://cn_a_liquid_v3"
decision_clock:
  signal_time: "T_CLOSE+30m"
  earliest_trade_time: "T+1_OPEN+5m"
inputs:
  - alias: "close"
    field_ref: "market.eod.close_adjusted"
    dtype: "price"
    unit: "CNY"
    availability: "T_CLOSE+20m"
  - alias: "turnover"
    field_ref: "market.eod.turnover"
    dtype: "ratio"
    unit: "1"
    availability: "T_CLOSE+20m"
expression:
  op: "neg"
  args:
    - op: "ts_corr"
      window: "20TD"
      min_periods: 15
      args:
        - {op: "returns", periods: 1, input: "close"}
        - {op: "delta", periods: 1, input: "turnover"}
postprocess:
  winsorize: {method: "mad", limit: 5}
  normalize: {method: "cross_sectional_zscore"}
  neutralize:
    exposures: ["industry_sw1", "log_float_mkt_cap"]
    method: "weighted_ridge"
missing_policy:
  max_missing_ratio: 0.15
  imputation: "industry_median"
  stale_limit: "2TD"
validation_policy_ref: "policy://equity_daily_factor_v4"
tags: ["price_volume", "reversal"]
```

### 4.3 核心类型

- `ScalarSeries<T, Unit>`：单资产时序。
- `CrossSection<T, Unit>`：某决策时点的横截面。
- `EventSeries<T>`：带事件发生与可用时间的数据。
- `LabelSeries<T>`：只允许在验证节点访问，因子执行节点无法引用。
- `UniverseMask`：点时 universe 成员掩码。
- `ExposureMatrix`：行业、风格、国家等风险暴露。

### 4.4 算子类别

- 时序：`lag`、`delta`、`returns`、`rolling_mean/std/min/max`、`ewm`、`ts_rank`、`ts_corr`。
- 横截面：`cs_rank`、`zscore`、`winsorize`、`group_demean`、`neutralize`。
- 基本面：`asof_latest_report`、`ttm`、`yoy`、`report_age`。
- 事件：`event_count`、`event_decay`、`since_event`。
- 组合：四则运算、条件表达式、裁剪；除法必须声明零值策略。

禁止：

- 无界窗口、负 lag、从未来向过去回填。
- 因子表达式引用 label、未来收益或 OOS 统计。
- 任意 UDF。生产阶段如需 UDF，必须注册为版本化、纯函数、可审计算子。

### 4.5 身份与版本

```text
expression_hash = SHA256(canonical_AST)
data_contract_hash = SHA256(sorted input field versions + availability rules)
context_hash = SHA256(universe + clock + postprocess + policy)
factor_version_id = factor_id@semver + expression_hash + context_hash
run_id = factor_version_id + dataset_snapshot_id + code_commit + environment_digest
```

语义版本规则：

- 修正文档、不改变结果：patch。
- 改变后处理、输入映射或参数：minor。
- 改变经济含义、公式主结构或时间语义：major，新因子族。

---

## 5. 完整数据流与状态机

### 5.1 端到端数据流

```text
Input
  → Intake validation
  → Source snapshot
  → Hypothesis/claim extraction
  → Candidate proposal
  → FactorSpec compile
  → Static + temporal lint
  → Data contract resolution
  → Experiment preregistration
  → PIT dataset materialization
  → Factor computation
  → Data/feature QA
  → Single-factor validation
  → Correlation/capacity review
  → HITL gate
  → Factor combination
  → Portfolio construction
  → Walk-forward/OOS backtest
  → Stress and attribution
  → Reproducibility replay
  → Audit report
  → Research registry / rejected archive
```

每个箭头产生结构化 `Artifact` 和 `Event`，不能只通过日志文本传递状态。

### 5.2 研究任务状态机

```text
CREATED
  → INTAKE_VALIDATED
  → SOURCE_FROZEN
  → CANDIDATES_PROPOSED
  → SPEC_COMPILED
  → PREREGISTERED
  → DATA_READY
  → COMPUTED
  → VALIDATED
  → HUMAN_REVIEW
  → STRATEGY_BUILT
  → BACKTESTED
  → REPRODUCED
  → REPORTED
  → APPROVED | REJECTED | ARCHIVED
```

旁路状态：

- `WAITING_INPUT`：缺数据授权、低置信度公式、关键约束缺失。
- `BLOCKED_POLICY`：安全、许可、预算或时间泄漏规则阻断。
- `FAILED_RETRYABLE`：瞬时数据/计算失败。
- `FAILED_TERMINAL`：Schema 不兼容、不可复现、确定性错误超限。
- `CANCELLED`：人工取消。

### 5.3 候选因子状态机

```text
DRAFT
 → LINTED
 → COMPILED
 → SMOKE_PASSED
 → REGISTERED_FOR_TEST
 → TESTED
 → GATE_PASSED
 → COMBINATION_ELIGIBLE
 → PROMOTED
```

任一步可进入：

- `REJECTED_STATIC`：语法、类型、时间或数据合同错误。
- `REJECTED_EMPIRICAL`：统计/稳健性/容量门禁失败。
- `SUPERSEDED`：被新版本替代。
- `QUARANTINED`：疑似泄漏、异常高表现或数据污染，等待调查。

### 5.4 幂等与恢复

- 每个任务输入采用 content-addressed artifact；相同 `run_id` 重跑必须得到相同结果。
- 节点以 `(run_id, node_name, attempt)` 记录，输出提交采用临时路径 + 原子 rename/manifest commit。
- 可重试节点使用指数退避；统计失败和政策失败不可自动重试。
- 下游只读取状态为 `COMMITTED` 的 artifact。
- 状态转换通过数据库事务和 outbox event 保证，避免编排器与元数据状态不一致。

---

## 6. 数据治理、校验与防泄漏

### 6.1 数据时间模型

所有记录至少包含：

- `event_time`：经济事件实际发生时间。
- `available_time`：研究者/交易系统最早可合法获知时间。
- `ingested_at`：平台接收到数据的时间。
- `revision_id`：数据修订版本。

查询约束为：

```sql
available_time <= decision_time
AND snapshot_id = :frozen_snapshot
```

财务数据按真实公告时间进入，不按报告期末进入；指数成分、行业分类、ST 和退市状态均按历史时点重建。

### 6.2 原始数据门禁

- 主键唯一性、交易日连续性、字段类型、单位、币种和时区。
- OHLC 逻辑、负价格/负成交量、异常复权跳变。
- 缺失率、横截面覆盖率、延迟分布、供应商修订率。
- 多源对账：价格、公司行动和证券状态在容差内一致。
- 数据许可：字段是否允许用于研究、衍生、报告和生产。
- 漂移检查：分布、零值、极值、类别占比与历史基线差异。

### 6.3 因子结果 QA

- 每日覆盖率、有限值比例、重复值比例和横截面方差。
- 极值、分位数、行业/市值集中度。
- 时间自相关、跳变、stale 比例。
- 对输入字段做扰动测试和 lag 测试；去掉最后 N 天数据时，历史因子值不得变化。
- “时间旅行单元测试”：对随机决策时点只暴露当时快照，比较与全量计算结果。
- “未来污染哨兵”：注入只存在于未来的随机字段，因子结果必须不受影响。

---

## 7. 论文复现的可追溯机制

### 7.1 证据图谱

为每次复现构建有向证据图：

```text
PDF hash
 → page/region
 → extracted claim/formula/table cell
 → normalized variable
 → local field mapping
 → transformation AST
 → experiment setting
 → execution run
 → reproduced metric/table
 → replication verdict
```

任一报告结论可反向追踪到页面坐标和 PDF 哈希；任一实现差异可追踪到审批记录。

### 7.2 关键对象

`PaperSource`：

- 文档版本、哈希、获取地址、许可、解析器版本。

`EvidenceRef`：

- 页码、区域坐标、公式/表格/段落 ID、抽取文本、置信度。

`PaperExperimentSpec`：

- universe、样本期、频率、筛选、变量、label、回归/排序方法、标准误、成本。

`VariableMapping`：

- 论文变量、本文定义、本地字段/派生式、映射类型、差异、审批人。

`ReplicationDelta`：

- 原设定、本地设定、原因、预期影响、是否阻断 R2/R3。

`ReplicationResult`：

- 目标表格、复现结果、方向一致率、标准化误差、容差、等级。

### 7.3 复现防伪规则

- 论文结果表不可手工录入后冒充程序输出。
- OCR 置信度低于阈值的公式必须 HITL 确认。
- 论文未说明的处理步骤不得由 LLM“合理猜测”后静默采用；必须标记 `inferred`。
- 本地化实验不得覆盖基线复现 run。
- 论文代码在无网络、只读输入、资源限额容器中运行，并记录镜像 digest、依赖锁文件和随机种子。

---

## 8. 因子验证门禁

门禁政策由资产类别配置。以下为日频股票建议基线，不作为所有市场的固定真理。

### 8.1 Gate 0：静态与时间安全

必须全部通过：

- IR 可编译、类型和单位一致、lookback 有界。
- 所有字段存在数据合同，且 available-time 早于决策时间。
- 无 label 引用、负 lag、向后回填、全样本标准化或全样本拟合。
- universe、benchmark、执行时点和持有期已冻结。

失败即拒绝，不进入统计测试。

### 8.2 Gate 1：数据与可计算性

- 有效样本覆盖率建议 ≥ 80%，关键行业/年份不得系统性缺失。
- 横截面有效股票数达到政策下限。
- 无大面积常数、无异常无限值、因子分布可解释。
- 重算一致性：同一快照、代码和环境下输出哈希一致。

### 8.3 Gate 2：预测有效性

至少报告，不只选择最优项：

- Pearson IC、Rank IC、ICIR、Newey-West 调整 t 值。
- 多持有期 IC decay：1/5/10/20/60 日。
- 分层收益、单调性、Top-Bottom spread 和置信区间。
- Fama-MacBeth 或横截面回归，控制行业、市值、beta 等已知暴露。
- 子样本：年份、牛熊、波动率、流动性、行业、市值。

建议晋级门槛示例：

- 预注册主 horizon 的 OOS Rank IC 绝对值 ≥ 0.02。
- OOS IC t 值 ≥ 2.0，且方向与经济假设一致。
- 至少 60% 的年度子样本方向一致。
- 五分组收益大体单调，不能只由一个极端组驱动。

### 8.4 Gate 3：稳健性与伪发现控制

- 参数邻域稳定，不允许只在单一窗口尖峰有效。
- 改变 winsorize、行业分类、执行价格后结论不反转。
- 与负对照、随机打乱 label 和时间错位测试有显著区分。
- 采用 Benjamini-Hochberg FDR、Deflated Sharpe Ratio 或 Probability of Backtest Overfitting，候选试验总数进入校正。
- 若 LLM/搜索算法探索了 N 个候选，N 必须计入研究账本，不能只登记幸存者。

### 8.5 Gate 4：独立性、换手与容量

- 与现有生产/候选因子的日截面相关和因子收益相关。
- 增量 IC、条件 IC、正交化后 IC。
- 原始换手、缓冲后换手、信号衰减和持有期匹配。
- 容量模型考虑 ADV 占比、参与率、冲击、涨跌停、停牌和可融券性。
- 因子不是已知风险因子的无意复制，或明确标记为风险溢价。

### 8.6 Gate 5：晋级规则

采用“硬门槛 + 评分卡”，不采用单一综合分掩盖致命问题：

- 硬门槛：时间安全、数据质量、OOS 方向、多重检验、容量最低值。
- 评分卡：效应强度 25%、稳定性 25%、独立性 20%、成本后价值 20%、可解释性 10%。
- 只有硬门槛全过且评分达到政策线，才进入组合池。
- 异常优秀结果触发 `QUARANTINED` 而不是快速晋级，例如日频无成本 Sharpe > 5、IC > 0.2。

---

## 9. 因子组合与策略构建

### 9.1 组合流程

1. 对通过门禁的因子做方向对齐、稳健标准化和可选行业/风格中性。
2. 删除高度相似因子，保留经济机制、稳定性和成本更优者。
3. 只使用训练窗口估计因子权重，在下一个 OOS 窗口冻结。
4. 将综合 alpha 输入组合优化器，叠加风险、成本和交易约束。
5. 订单层应用缓冲区、最小交易单位、涨跌停/停牌约束。

### 9.2 因子权重方法取舍

MVP 推荐 **稳健 IC 加权 + shrinkage**，而不是深度模型：

```text
raw_weight_i = clipped(EWMA(train_IC_i) / train_IC_vol_i)
weight = shrink(raw_weight, equal_weight, lambda)
weight = constrained_normalize(weight, max_abs_weight, group_caps)
```

原因：

- 样本有限时稳定、可解释、容易 walk-forward。
- 可以明确展示每个因子的边际贡献。
- 深度模型容易把组合层变成新的数据挖掘层。

生产阶段可加入：

- 正则化线性模型/Elastic Net。
- Bayesian model averaging。
- 带时变 regime 的 gated ensemble，但 regime 特征必须在当时可得。
- 非线性模型只在跨期稳定、消融充分且可解释工具成熟后启用。

### 9.3 组合优化

目标函数：

```text
maximize  alpha' w
        - λ_risk * w'Σw
        - λ_tc * Cost(w - w_prev)
        - λ_conc * ConcentrationPenalty(w)
```

典型约束：

- 净/总敞口、单票、行业、风格、beta、国家/币种。
- ADV 参与率、换手预算、持仓数量、最小成交额。
- 禁买、停牌、涨跌停、ST、融券可用性。
- benchmark-relative tracking error。

风险模型使用点时暴露和训练窗协方差；禁止用全样本协方差。

### 9.4 交易成本

拆分为：

- 显式成本：佣金、印花税、交易所费用、借券费。
- 点差成本：与价格/流动性/交易时段相关。
- 市场冲击：建议初期用平方根模型，参数按市场和市值层拟合。
- 延迟与机会成本：信号生成到执行期间的价格变化。
- 约束成本：涨跌停、停牌和无法成交造成的持仓偏离。

成本参数必须按日期版本化，并提供保守/基准/乐观三档压力测试。

---

## 10. Walk-forward / OOS 回测设计

### 10.1 推荐切分

- 最终保留一段从未参与设计的 lockbox。
- 开发期使用 expanding 或 rolling walk-forward，例如训练 3 年、验证 6 个月、测试 6 个月，每 6 个月滚动。
- 有标签重叠时使用 purged split，并在边界加入 embargo。
- 因子参数、组合权重、风险模型和成本校准都只能使用当前训练窗。
- 每个 OOS fold 的持仓和成交按真实事件顺序模拟，最后拼接成完整 OOS 权益曲线。

### 10.2 事件顺序

```text
数据在 available_time 到达
→ 决策时点构建 universe
→ 计算因子
→ 生成目标仓位
→ 检查可交易状态
→ 下一可交易时点下单
→ 成交模型产生 fills
→ 更新现金/持仓/费用
→ 公司行动与估值
```

### 10.3 回测防偏差清单

- [ ] 使用历史点时 universe，包含退市股票。
- [ ] 财务数据按公告/可用时间，不按报告期末。
- [ ] 供应商修订值不会覆盖历史可见值。
- [ ] 价格复权和公司行动处理不泄漏未来因子。
- [ ] 信号、下单和成交时点严格分离。
- [ ] 停牌、涨跌停、无成交量、融券限制真实建模。
- [ ] 不用收盘价同时生成信号并按同一收盘价无摩擦成交。
- [ ] 标签构造与特征窗口无重叠泄漏。
- [ ] 标准化、中性化、缺失填充参数按训练期/当日横截面计算。
- [ ] 样本切分使用 purging/embargo 处理重叠持有期。
- [ ] 参数、阈值、因子方向未在 OOS 或 lockbox 上选择。
- [ ] 所有尝试过的候选计入多重检验和试验账本。
- [ ] 交易成本、冲击和 ADV 使用当时可见/历史估计。
- [ ] 风险模型暴露与协方差是点时且训练窗估计。
- [ ] 汇率、时区、节假日和不同市场日历对齐。
- [ ] benchmark 成分和行业分类按历史版本。
- [ ] 随机种子固定；并行计算归约顺序可重复。
- [ ] lockbox 只在晋级前打开一次；失败后不得反复调参。
- [ ] 报告区分 gross、net、paper portfolio 和可执行 portfolio。
- [ ] 由独立 replay job 从原始快照重建关键结果。

---

## 11. Agent 与 HITL 编排

### 11.1 Agent 角色

| Agent | 输入 | 输出 | 权限 |
|---|---|---|---|
| Intake Agent | brief/PDF/约束 | 结构化研究任务 | 只读数据目录 |
| Hypothesis Agent | brief、市场知识、数据字典 | 可证伪假设与候选草案 | 不可执行回测 |
| Paper Agent | 解析文档 | Claim、公式、实验设定、证据引用 | 只读文档 |
| Mapping Agent | 变量定义、Data Catalog | 字段映射和差异清单 | 不可查询真实 label |
| Factor Author Agent | 候选草案 | FactorSpec | 只能调用 IR 工具 |
| Critic Agent | FactorSpec、证据 | 泄漏/歧义/反例清单 | 无修改权 |
| Experiment Agent | 已批准 spec | 预注册实验 DAG | 只能选择政策允许模板 |
| Result Analyst Agent | 结构化指标 | 解释、失败归因、下一步建议 | 数值只读 |
| Report Agent | artifacts、审计日志 | 报告文字 | 不可改结论状态 |

Agent 不持有长期“事实记忆”作为真源；状态必须写入 Registry/Artifact Store。

### 11.2 HITL 门

必须人工确认：

- 低置信度论文公式和关键变量映射。
- 使用 proxy 替代论文原变量。
- 修改预注册主指标、OOS 切分或门槛。
- 因子晋级组合池和打开最终 lockbox。
- 发布到模拟/实盘。
- 许可不明确、另类数据含隐私或供应商限制。

可自动通过：

- 高置信度文档结构提取。
- 已注册算子的类型检查和静态 lint。
- 确定性数据 QA、计算、统计和报告生成。
- 可重试基础设施失败。

### 11.3 编排模式

- 使用 DAG 编排器承载任务，不让 Agent 用聊天消息隐式驱动状态。
- Agent 调用工具必须携带 `research_id`、`run_id`、预算和权限 token。
- 每个节点有 schema 化输入/输出、超时、重试策略和幂等键。
- Critic Agent 与 Author Agent 分离，且最终裁决由 Policy Engine 而非二者投票。
- 人工审批记录审批人、时间、理由、前后 diff，不接受口头“同意”。

---

## 12. 建议技术栈与接口

### 12.1 技术栈取舍

**MVP：**

- Python 3.12、Polars/Arrow：因子与批量研究计算。
- DuckDB：本地和中小规模探索；不作为唯一生产元数据数据库。
- Parquet + Apache Iceberg：不可变快照、schema evolution、time travel。
- PostgreSQL：Registry、状态机、审批、实验元数据。
- Dagster：资产化编排、分区、重试和 lineage；若团队已有 Airflow/Argo，应复用现有平台。
- FastAPI + Pydantic：Research/Factor/Experiment API。
- MLflow：实验指标与 artifact 索引；关键 lineage 仍由自有 schema 管理。
- Great Expectations 或自研轻量规则引擎：数据合同与质量检查。
- QuantStats/自研报告层：仅用于展示；核心指标自行实现并测试。
- Docker + uv 锁依赖；生产用 Kubernetes Jobs。
- OpenTelemetry + Prometheus/Grafana：链路、指标和告警。

**论文解析：**

- PyMuPDF/Docling/版面模型解析 PDF。
- OCR 作为回退；公式抽取结果统一转 LaTeX/MathML。
- LLM 采用结构化输出、固定模型版本、低温度；原始提示词和响应封存。

**不建议首期引入：**

- 多套计算引擎同时存在。
- 自定义流处理平台。
- 端到端 AutoML/强化学习策略搜索。
- 图数据库作为强依赖；证据图可先用 PostgreSQL 边表实现。

### 12.2 关键 API

```http
POST /v1/research-jobs
GET  /v1/research-jobs/{id}
POST /v1/papers
GET  /v1/papers/{id}/extractions
POST /v1/factors:compile
POST /v1/factors/{id}/versions
POST /v1/experiments:preregister
POST /v1/experiments/{id}:run
GET  /v1/experiments/{id}/metrics
POST /v1/approvals
POST /v1/strategies
POST /v1/backtests
GET  /v1/reports/{run_id}
GET  /v1/lineage/{artifact_id}
```

### 12.3 服务接口约束

`PIT Data Service`：

```python
get_dataset(
    fields: list[FieldRef],
    universe_ref: str,
    start: date,
    end: date,
    decision_clock: DecisionClock,
    snapshot_id: str,
) -> DatasetManifest
```

返回 manifest，不直接返回不可追踪 DataFrame。Manifest 包含分区、schema、哈希、记录数、可用时间规则和许可标签。

`Factor Executor`：

```python
execute(
    compiled_ir_id: str,
    dataset_manifest_id: str,
    compute_profile: str,
) -> FactorArtifact
```

`Validator`：

```python
validate(
    factor_artifact_id: str,
    experiment_spec_id: str,
    validation_policy_id: str,
) -> ValidationBundle
```

所有接口使用 JSON Schema/OpenAPI 契约；大 artifact 只传 URI + hash。

---

## 13. 元数据、版本与实验追踪

### 13.1 必存元数据

- `ResearchJob`：输入、发起人、目标、约束、预算、状态。
- `SourceArtifact`：brief/PDF/代码/附件、哈希、许可。
- `Hypothesis`：机制、方向、horizon、反证条件、来源。
- `FactorSpec`/`CompiledIR`：版本、AST、依赖、编译器版本。
- `DatasetSnapshot`：字段版本、分区、质量结果、许可标签。
- `ExperimentSpec`：预注册切分、指标、门槛、随机种子。
- `Run`：代码 commit、容器 digest、硬件、参数、时间、父 run。
- `Metric`：值、定义版本、样本范围、置信区间。
- `Artifact`：URI、hash、schema、生产节点。
- `Approval`：对象、diff、审批人、理由、时间。
- `LLMTrace`：模型、版本、prompt template、输入 artifact refs、结构化输出、token、成本。

### 13.2 不可变性

- 已执行的 `ExperimentSpec` 不可原地修改；只能 fork 新版本。
- 数据快照和关键报告采用对象锁/WORM 策略。
- 报告页显示 `run_id`、数据快照、代码 commit、IR hash 和重现命令。
- 删除遵循数据许可和隐私政策，但保留合规 tombstone 与删除审计。

### 13.3 实验关系

使用 `parent_run_id` 和 `change_set` 标注：

- baseline → parameter sensitivity。
- paper baseline → local adaptation。
- single factor → combined strategy。
- failed run → repaired run。

报告必须区分预注册主实验、探索性实验和事后分析。

---

## 14. 失败处理

### 14.1 失败分类

- **输入失败**：PDF 损坏、brief 缺关键约束。进入 `WAITING_INPUT`。
- **映射失败**：字段不存在或只能用不可接受 proxy。终止该候选，不自动捏造字段。
- **政策失败**：时间泄漏、许可违规、预算超限。`BLOCKED_POLICY`，需人工处理。
- **数据失败**：分区缺失、质量下降、供应商延迟。冻结下游并告警。
- **计算失败**：OOM、worker 中断、临时存储错误。按幂等键重试并可降级资源规格。
- **统计失败**：门禁不通过。记录为研究结论，不应自动“修复到通过”。
- **复现失败**：论文结果差异超容差。输出差异分解，保留失败证据。
- **一致性失败**：同一 run 重算 hash 不一致。隔离结果并触发确定性调查。

### 14.2 重试与补偿

- 基础设施类默认最多 3 次，指数退避。
- OCR/LLM 解析可切换备用模型一次，但必须生成新 extraction version。
- Artifact 写入失败执行清理补偿；元数据只指向已提交对象。
- 下游已消费的错误数据通过 lineage 批量标记 `tainted` 并失效，不静默覆盖。
- 任何人工 override 必须有到期时间和审批理由。

---

## 15. 安全与成本控制

### 15.1 安全

- RBAC/ABAC：按项目、数据域、市场和操作类型授权。
- 数据许可标签随 lineage 传播；报告导出前做政策检查。
- PDF、作者代码和附件视为不可信输入，做病毒扫描、内容类型校验和 sandbox。
- LLM 防提示注入：文档内容仅作为数据，系统指令与工具权限固定；文档中的“执行命令/上传数据”不生效。
- Agent 使用短期凭证、最小权限和出站网络白名单。
- 任意外部代码在无网络、非 root、只读根文件系统、CPU/内存/时间限额容器中运行。
- 秘钥存 Vault/KMS，不进入 prompt、日志或 artifact。
- 对敏感另类数据做脱敏、用途限制和访问审计。

### 15.2 成本

- 每个 ResearchJob 设 LLM token、候选数、CPU/GPU 小时、扫描数据量和 wall-clock 预算。
- 文档按页缓存解析；相同 PDF hash 不重复 OCR/LLM。
- IR 子表达式按 AST + snapshot 缓存。
- 分级执行：静态检查 → 小样本 smoke → 完整单因子 → 组合回测。
- 候选使用 successive halving，但正式门禁仍在完整预注册样本运行。
- 默认使用小模型做分类/抽取，高价值歧义才升级强模型。
- 超预算不自动追加；进入 HITL。
- 成本报告按任务展示“每个通过门禁因子的边际成本”。

---

## 16. MVP 到生产路线图

### Phase 0：规则与数据基线（2–4 周）

- 冻结日频股票场景、决策时钟和验证政策。
- 建立证券主数据、交易日历、行情、财务公告时间和历史 universe 的 PIT 合同。
- 定义 FactorSpec v1、核心算子和 20–30 个时间安全测试。
- 选 3 个已知因子作为 golden set。

**退出条件**：golden set 在固定快照可重复，时间旅行测试通过。

### Phase 1：确定性研究内核 MVP（6–8 周）

- Factor Registry、IR 编译器、PIT Data Service、Executor。
- 单因子验证、walk-forward 回测、成本模型和基础报告。
- Dagster 编排、PostgreSQL 元数据、MLflow artifact。
- 人工录入 FactorSpec，暂不追求自动挖掘。

**退出条件**：从 spec 到报告一键运行；相同 run 输出 hash 一致。

### Phase 2：两类智能入口（4–6 周）

- ResearchBrief Agent 和 Paper Parser/Claim/Formula extraction。
- 数据字段映射、evidence refs、ReplicationDelta。
- 受限候选生成与 Critic Agent。
- 论文基线复现模板。

**退出条件**：至少 5 篇论文完成 R1，2 篇达到 R2；自然语言路径候选全部先编译后执行。

### Phase 3：策略与治理强化（6–8 周）

- 因子组合、风险模型、容量、组合优化。
- 多重检验账本、lockbox、审批工作流。
- 权限、许可传播、WORM 报告、可观测性。

**退出条件**：一组多因子策略完成独立 replay 和完整审计。

### Phase 4：生产化（持续）

- Kubernetes 扩展、任务优先级、配额、SLA。
- 数据漂移、live paper trading、模型/因子衰减监控。
- 与策略发布、模拟盘和实盘风控系统对接。
- 支持分钟级、期货或多市场时，每类资产新建专属 clock、成本和验证政策，不复用股票日频默认值。

---

## 17. 验收指标

### 17.1 功能

- 两类入口均可生成符合 Schema 的 FactorSpec。
- 100% 执行因子来自已编译 IR，无任意代码旁路。
- 报告可一跳查看输入、公式、数据、代码、指标和审批。
- 论文报告中每个关键变量和结论都有 EvidenceRef 或明确标记 inferred。

### 17.2 正确性

- Golden factors 与基准实现数值差异在 `1e-10` 或业务定义容差内。
- 未来污染哨兵、公告时间、幸存者偏差和同收盘成交测试 100% 阻断。
- 同一 run 在相同架构环境重跑关键 artifact hash 一致。
- 随机 label 的门禁通过率符合预设假阳性上限。

### 17.3 研究质量

- 所有正式实验 100% 预注册主指标、切分和试验预算。
- 候选试验登记覆盖率 100%，不存在只记录幸存者。
- 通过 Gate 的因子在下一独立 OOS 窗口方向保持率达到团队基线，例如 ≥ 65%。
- 报告同时展示 gross/net、稳定性、容量和失败项，不能只展示 Sharpe。

### 17.4 性能与运维

- 3000 股票 × 10 年日频 × 20 个标准因子的全流程在目标集群内小于 60 分钟。
- 缓存命中时单因子增量验证小于 10 分钟。
- 编排任务成功率 ≥ 99%，基础设施失败可自动恢复率 ≥ 95%。
- 元数据 API P95 小于 500 ms；关键服务有 SLO 和告警。

### 17.5 成本

- 单个 ResearchJob 的预算超支率 < 5%。
- 相同文档和数据快照重复处理成本降低 ≥ 70%。
- 可按候选、通过因子、论文复现 run 归集成本。

---

## 18. 关键风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 生成“看似合理”的伪公式 | 大量伪候选 | IR 白名单、证据引用、负对照、候选预算 |
| 数据 available-time 不可靠 | 系统性未来函数 | 字段级时间合同、供应商审计、默认拒绝 |
| 论文描述不完整 | 复现结论误标 | `inferred` 标记、ReplicationDelta、复现等级 |
| 自动搜索导致多重检验爆炸 | 样本内过拟合 | 试验账本、FDR/DSR/PBO、lockbox |
| 因子组合掩盖单因子缺陷 | 策略不可解释 | 单因子硬门禁、增量贡献与消融 |
| 成本/容量模型过于乐观 | OOS 与实盘落差 | 三档压力、成交约束、paper trading 校准 |
| Agent 权限过大 | 数据泄露或执行风险 | 最小权限、sandbox、工具白名单、审计 |
| 数据/代码版本漂移 | 无法重现 | 快照、容器 digest、锁文件、artifact hash |
| 指标门槛僵化 | 错杀新型 alpha 或被规则 gaming | 政策版本化、人工例外但强审计、按资产类别配置 |
| 研究吞吐追求压过研究质量 | 垃圾候选堆积 | 以 OOS 保持率和每个有效因子的成本衡量，而非候选数量 |

---

## 19. 具体示例：从研究假设到回测报告

### 19.1 输入

研究人员提交：

> 假设：分析师盈利预测分歧扩大后，如果股价仍强势上涨，可能代表信息不确定性被价格趋势暂时掩盖，未来 20 个交易日存在反转。限定 A 股、沪深 300 可交易成分、日频、行业和市值中性、月度调仓、单票不超过 1%、年化换手不超过 8 倍。

### 19.2 提案与数据可行性

Hypothesis Agent 拆解：

- 机制：高分歧意味着估值不确定性；强势价格与分歧共存可能过度反应。
- 代理变量：未来 12 个月 EPS 预测的横截面标准差/均值、过去 20 日收益。
- 预期：`dispersion × positive_momentum` 越高，未来收益越低。
- 反证：效应若只在微盘股、公告日或低覆盖股票出现，则机制不成立。

Data Catalog 返回：

- `analyst.eps_fy1_mean/std`：日快照，供应商在 T 日 07:00 更新，可供 T 日开盘后使用。
- `market.eod.close_adjusted`：T 日收盘后 20 分钟可用。
- 因为策略在 T 日收盘后决策，分析师数据允许使用当日 07:00 快照，价格允许使用 T 收盘。

### 19.3 候选 FactorSpec

```yaml
factor_id: fac_earnings_disagreement_momentum
version: 1.0.0
decision_clock:
  signal_time: T_CLOSE+30m
  earliest_trade_time: T+1_OPEN+5m
expression:
  op: neg
  args:
    - op: mul
      args:
        - op: clip
          min: 0
          max: 3
          args:
            - op: safe_div
              zero_policy: null
              args:
                - {input: eps_fy1_std}
                - {op: abs, args: [{input: eps_fy1_mean}]}
        - op: clip
          min: 0
          max: 1
          args:
            - {op: returns, periods: 20, input: close}
postprocess:
  winsorize: {method: mad, limit: 5}
  neutralize:
    exposures: [industry_sw1, log_float_mkt_cap]
  normalize: {method: cross_sectional_zscore}
```

编译器检测到分析师字段可能在均值接近零时爆炸，因此要求 `safe_div` 和覆盖分析师数量下限；加入 `analyst_count >= 3` 的 universe mask。

### 19.4 预注册

- 样本：2014-01-01 至 2025-12-31。
- 开发 walk-forward：训练 36 个月、验证 6 个月、测试 6 个月，滚动。
- 最终 lockbox：2024-01-01 至 2025-12-31，在晋级决定前不可见。
- 主指标：20 日 OOS Rank IC。
- 次指标：五分组 spread、ICIR、换手、成本后 Sharpe、容量。
- 尝试预算：机制候选最多 12 个；主窗口只允许 20 日，5/10/60 日仅作 decay 报告。
- 门槛：Rank IC ≤ -0.02，t ≤ -2，年度方向一致率 ≥ 60%，FDR q < 0.10。

### 19.5 数据与计算

PIT Data Service 固化 `snapshot_cn_equity_20260809_01`。Executor 按每日决策时点：

1. 取当时沪深 300 历史成分。
2. 排除停牌、ST、上市不足 120 日和分析师覆盖不足 3 的股票。
3. 使用当日 07:00 已发布的 FY1 预测快照。
4. 使用 T 日收盘价格计算 20 日动量。
5. 生成原始值，横截面 winsorize、中性化和 z-score。
6. T+1 开盘后 5 分钟才允许交易。

时间旅行测试删除未来 60 日数据后，历史因子 artifact hash 不变。

### 19.6 示例验证结果

以下数值为流程示意，不代表真实市场结论：

| 指标 | 开发 OOS | Lockbox OOS |
|---|---:|---:|
| 20 日 Rank IC | -0.031 | -0.024 |
| Newey-West t | -3.2 | -2.1 |
| 年度方向一致率 | 75% | 100% |
| 五分组 Q1-Q5 年化 spread | 8.4% | 5.9% |
| 月度双边换手 | 42% | 39% |
| 与现有反转因子相关 | 0.34 | 0.31 |
| FDR q-value | 0.06 | 冻结验证 |

容量模型显示在 ADV 参与率 5%、单票 1% 限制下，策略估算容量为 8 亿元；基准成本后仍有正 spread。因子通过硬门槛，评分卡 78/100，进入组合池。

### 19.7 策略构建

将该因子与质量、估值和低波因子组合：

- 因子权重使用训练窗稳健 ICIR，加 50% 等权 shrinkage。
- 单因子权重上限 35%。
- 组合相对沪深 300 行业偏离不超过 2%，beta 在 `[0.95, 1.05]`。
- 单票权重 0–1%，总换手预算年化 8 倍。
- 使用成交额、点差和平方根冲击模型估算成本。

### 19.8 Walk-forward 回测与报告

Backtest Engine 逐 fold 冻结因子权重、风险参数和成本参数，生成：

- gross/net 权益曲线与回撤。
- OOS Sharpe、信息比率、tracking error、换手和成本分解。
- 行业/风格/因子收益归因。
- 容量曲线与参与率压力测试。
- 各 fold、年份和 regime 的稳定性。
- 因子消融：移除该分歧因子后的边际变化。
- 完整 lineage：brief → Hypothesis → FactorSpec → data snapshot → run → report。

报告首页明确写出：

- 该因子“通过当前政策门禁”，不是“保证未来有效”。
- 主要失效风险为分析师覆盖结构变化、预测供应商口径变化和市场对分歧信息定价速度提高。
- paper trading 监控项：滚动 IC、覆盖率、与反转因子相关性、实际冲击和容量。

---

## 20. 五条优于常见做法的关键判断

1. **把时间可用性写进类型系统，而不是依赖回测人员自觉 `shift`。** 常见平台把未来函数当代码 review 问题，本方案把它变成编译和数据服务层的硬约束。
2. **记录所有候选和试验预算，而不是只保存“成功因子”。** 这使 FDR、DSR、PBO 等伪发现控制有真实分母，避免研究过程的幸存者偏差。
3. **论文复现与本地改编严格分叉。** 常见做法在数据不一致时直接替换字段并宣称复现；本方案用证据图、ReplicationDelta 和 R0–R4 等级约束结论措辞。
4. **LLM 不触碰裁决、数据快照和数值结果。** 这保留 LLM 在理解文本和生成假设上的优势，同时把最危险的自由度锁在确定性引擎外。
5. **先证明单因子增量价值，再允许组合优化。** 常见 AutoML 容易用复杂模型掩盖弱因子和泄漏，本方案通过硬门禁、正交后 IC、消融和冻结 OOS 权重保证组合收益可解释、可审计。

---

## 21. 最终落地建议

第一阶段不要从“自动读论文”开始，而应先完成 PIT 数据合同、Factor IR、时间安全测试、验证政策和可重复回测。这些是系统可信度的地基。地基稳定后，再接入两类 LLM 上游；否则自动化只会更快地产生不可审计的错误。

生产决策应以三项指标为核心：**独立 OOS 保持率、可重现率、成本后边际贡献**。候选数量、生成速度和样本内收益只能作为运营指标，不能作为平台成功标准。
