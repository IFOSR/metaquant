# Pi 端到端量化研究 Pipeline 架构方案

## 1. 目标、范围与明确假设

### 目标

构建一个“证据驱动、时间正确、可复现、可审计”的量化研究流水线：从自然语言研究命题或论文/PDF 出发，形成候选因子，经过统一定义、数据与泄漏检查、统计验证、组合构建、成本/风险建模和 walk-forward/OOS 回测，最终输出可追溯报告与可部署策略候选。

核心不是让 LLM 自动宣布“发现 alpha”，而是让 LLM 提高假设生成和论文理解效率；所有数值计算、时间对齐、门禁、回测和审计由确定性代码完成。

### 明确假设

1. MVP 以日频、股票横截面、多空或多头增强策略为主；基础设施保留分钟频、期货和数字资产扩展点，但不在 MVP 同时支持。
2. 研究时点为 `as_of`，任何输入数据必须同时记录“经济发生时间 event_time”和“系统可获知时间 available_time”；修订型数据另记录 `revision_id`。
3. 初始样本至少覆盖一个完整市场周期，建议 A 股/美股日频 8 年以上；不足时降低结论等级，不伪造统计显著性。
4. 因子收益预测仅在明确 universe、频率、持有期、交易日历和执行假设下成立；脱离这些上下文的“因子”不是可比较对象。
5. 研究平台不直接下单。只有通过独立审批和 paper/live shadow 阶段的版本化策略包才能交给执行系统。
6. 用户拥有论文和数据的合法使用权；系统必须遵守供应商许可，不把受限原始数据发送给外部 LLM。

### 有意取舍

- 选“批处理优先 + 事件溯源状态机”，不先做实时流式研究平台：日频研究更需要时间正确性和重放能力。
- 选统一、受限的 Factor IR/DSL，不允许 LLM 直接生成任意 Python：降低任意代码执行、泄漏和不可复现风险。
- 选固定主门禁 + 多重检验修正 + 冻结 OOS，不靠单一 Sharpe/IC 排名：控制因子动物园与反复窥视测试集。
- 论文复现分“忠实复现”和“本地适配”两个实验分支，禁止把适配后的好结果冒充原文复现。
- MVP 使用单体控制面、可分布式计算面的模块化架构；先保证契约，再拆微服务。

## 2. 总体架构与组件边界

```text
[研究假设/UI/API] ----> [Hypothesis Agent] ---\
                                            +--> [Factor IR Registry]
[PDF/Object Store] -> [Paper Repro Pipeline] --/          |
                                                         v
[Data Catalog] -> [PIT Data Gateway] -> [Validation & Compute Engine]
                                      -> [Factor Evaluation/Gates]
                                      -> [Portfolio/Strategy Builder]
                                      -> [Cost/Risk Models]
                                      -> [WF/OOS Backtest Engine]
                                      -> [Audit Report + Strategy Package]

横切能力: Orchestrator/State Store, Metadata/Lineage, Experiment Tracking,
Secrets/Policy, Observability, Artifact Store, Human Approval
```

组件边界：

- **Research Intake**：接收命题、市场、资产池、频率、约束和成功标准；只负责结构化，不做结论。
- **Paper Repro Pipeline**：PDF 取证、版面/OCR、公式与表格提取、实验设定归一、差异登记；不直接执行任意论文代码。
- **Factor Registry**：Factor IR 的唯一事实源，做 schema 校验、内容寻址、版本和依赖 DAG 管理。
- **Data Catalog/PIT Gateway**：数据授权、字段语义、双时间索引、企业行动、退市样本、交易日历和快照；禁止研究任务绕过网关读裸表。
- **Compute Engine**：解析 DSL 为受控执行图，进行窗口计算、横截面变换、中性化和缓存；相同输入哈希必须得到相同结果。
- **Evaluation/Gate Engine**：生成 IC、分层、换手、稳定性、相关性、容量和统计检验，执行版本化门禁策略。
- **Strategy Builder**：因子去冗余、组合、权重/约束优化和再平衡规则；不修改上游因子定义。
- **Backtest Engine**：事件驱动订单/成交模拟，严格按信号、订单、成交时钟运行，输出账本而非只输出收益曲线。
- **Report/Audit**：从不可变 artifact 和 lineage 生成报告；报告模板不重新计算结果。
- **Orchestrator**：只编排有类型的任务和审批，不承载量化逻辑。

## 3. 两条因子挖掘路径

### 路径 A：人工/LLM 研究命题

输入必须包含：研究命题、经济机制、适用市场与资产池、观测时间、预测目标、持有期、禁用字段、成本/容量约束、可证伪条件。流程为：

1. Intake 将自然语言转成 `HypothesisSpec`，实体链接到数据目录；缺少时间语义或目标变量时停止并请求 HITL。
2. Retrieval Agent 仅检索已批准的数据字典、历史实验和文献摘要，找出重复因子、可用字段和已知反例。
3. Candidate Agent 基于白名单算子生成少量候选 IR，并为每个候选写经济机制、预期符号、失效场景和复杂度预算；MVP 每个命题最多 20 个候选。
4. Static Analyzer 做类型、单位、窗口、可用时点、非法目标引用、同义重复和复杂度检查。
5. 先跑廉价 smoke sample，再跑完整验证；失败原因回写，但不允许 Agent 自主反复调参窥视 OOS。
6. 人工批准进入正式实验，并冻结候选集合、搜索空间和 OOS 时间段。

LLM 可做：命题结构化、字段候选映射、机制解释、DSL 草案、结果摘要。确定性实现：字段解析、DSL 编译、数据查询、泄漏检测、统计检验、回测和门禁。

### 路径 B：论文/PDF 复现

1. 对原始 PDF 计算 SHA-256，保存来源 URI、获取时间、版本、许可和逐页渲染；文本型 PDF 用版面解析，扫描件按页 OCR。
2. 抽取标题、作者、样本市场/区间、universe、过滤规则、频率、公式、变量定义、滞后、再平衡、成本、基准和评价表；每个字段必须指向页码、bbox/文本片段和置信度。
3. Formula Agent 将公式转为带符号表的 AST/LaTeX，再映射为 Factor IR；确定性检查自由变量、单位、窗口、分母零值和公式编号。
4. Data Mapper 把论文变量映射到本地数据字段，记录 `exact/proxy/unavailable`、转换规则和偏差影响。任何 proxy 必须 HITL 批准。
5. 建立两个不可混淆的实验：`faithful_reproduction` 尽量匹配论文；`local_adaptation` 才允许更换市场、样本、成本或参数。
6. 先复现论文中间表/描述统计/单变量结果，再做本地扩展；中间结果对不上时不得直接跳到策略收益比较。

## 4. 统一 Factor IR / DSL

Factor IR 使用版本化 JSON/YAML schema，表达“是什么、何时可知、如何计算、预测什么、如何验证”，不承载任意代码。示意：

```yaml
schema_version: factor-ir/v1
factor_id: quality.sue_3m
version: 1.2.0
hypothesis_ref: hyp_01J...
provenance:
  kind: paper
  source_sha256: "..."
  citations:
    - {page: 7, bbox: [88, 214, 510, 292], formula: "(EPS_t-EPS_t-4)/sigma"}
universe:
  market: US
  asset_type: equity
  selector: "common_stock & primary_listing & price>=5"
  survivorship_policy: point_in_time
clock:
  calendar: XNYS
  observation_time: close
  available_lag: "next_session_open"
  signal_time: "session[t].close"
  order_time: "session[t+1].open"
inputs:
  - {name: eps_q, dataset: fundamentals_pit, field: diluted_eps,
     dtype: float64, unit: USD/share, availability: vendor_timestamp}
expression:
  op: winsorize_cs
  args:
    - {op: div, args: [
        {op: sub, args: [{ref: eps_q}, {op: lag, args: [{ref: eps_q}, 4]}]},
        {op: rolling_std, args: [
          {op: sub, args: [{ref: eps_q}, {op: lag, args: [{ref: eps_q}, 4]}]}, 8]}
      ]}
    - {lower_q: 0.01, upper_q: 0.99}
postprocess:
  - {op: zscore_cs}
  - {op: neutralize, exposures: [sector, log_mcap]}
target: {kind: forward_return, horizon: 20d, price: open_to_open}
missing_policy: {min_history: 8q, cross_section_fill: none}
validation_policy: equity_daily_v3
```

受限算子分四类：时间序列 `lag/diff/rolling_* /ewm/rank_ts`，横截面 `rank_cs/zscore_cs/winsorize_cs/neutralize`，代数 `add/sub/mul/div/log/signed_power`，条件 `where/clip/isfinite`。所有算子声明输入/输出类型、单位规则、warm-up、null 传播和可用时间传播；编译器自动推导 `effective_available_time=max(inputs)+operator_lag`。

IR 的规范化 JSON 计算 `factor_def_hash`；数据快照、代码镜像、日历、配置、随机种子和环境锁文件共同计算 `run_fingerprint`。任何一个变化都生成新 run，禁止原地覆盖。

## 5. 完整数据流与状态机

数据流：

```text
Raw Source -> immutable bronze -> PIT-normalized silver -> feature-ready gold
Input/PDF -> Evidence Bundle -> HypothesisSpec -> Candidate IR -> Validated IR
-> Factor Values -> Evaluation Bundle -> Accepted Factor Set -> StrategySpec
-> Orders/Fills/Ledger -> Backtest Bundle -> Signed Audit Report
```

每个 artifact 以 URI + content hash 引用，状态记录只保存引用与摘要。主状态机：

```text
RECEIVED
 -> PARSED
 -> EVIDENCE_READY
 -> IR_DRAFTED
 -> STATIC_VALIDATED
 -> DATA_VALIDATED
 -> COMPUTED
 -> EVALUATED
 -> GATE_REVIEW
 -> ACCEPTED | REJECTED | NEEDS_HUMAN
 -> STRATEGY_BUILT
 -> BACKTESTED
 -> REPORT_APPROVAL
 -> PUBLISHED
```

异常子状态为 `RETRYABLE_FAILED`、`TERMINAL_FAILED`、`QUARANTINED`、`CANCELLED`。状态迁移由显式前置条件和幂等键驱动；失败重跑产生新 attempt，不篡改历史。`ACCEPTED` 仅代表通过研究门禁，不代表获准交易。

## 6. 论文复现的可追溯机制

每次复现生成 `ReproductionManifest`：PDF 哈希与来源、解析器/OCR/LLM 模型版本、prompt hash、页级证据、公式 AST、变量映射、数据快照、原文参数、偏差清单、代码镜像 digest、环境锁、随机种子、运行指纹和输出 artifact 哈希。

建立可双向查询的证据图：`报告结论 -> 指标 -> run -> Factor IR -> AST/变量映射 -> PDF 页码/bbox`。LLM 提取内容必须附 evidence span 和置信度；低置信度公式、表头错位、脚注依赖、变量 proxy 自动进入 HITL。报告明确分级：完全复现、方向复现、部分复现、不可复现，并列出差异，不用“结果相近”掩盖口径变化。

## 7. 数据校验与因子验证门禁

### 数据与防泄漏门禁（硬失败）

- schema、主键、频率、币种/单位、交易日历、企业行动和重复值检查。
- 覆盖率、缺失簇、极值、停牌、涨跌停、退市、IPO seasoning 和 universe 漂移检查。
- `available_time <= signal_time`；财报用真实披露/供应商到达时间，不用财报期末日期。
- universe membership、行业分类和指数成分使用历史快照；必须包含退市证券。
- target 字段不能出现在表达式依赖图；任何 forward window 节点只允许存在于 evaluator。
- 特征归一化、缺失填充、中性化、模型拟合只能在训练折拟合，再应用到验证/OOS。
- 执行价格必须晚于信号，且考虑开盘不可交易、停牌、冲击和成交量约束。

### 统计与经济性门禁（默认基线，可按市场/频率版本化）

1. 有效覆盖率中位数 >= 70%，单证券所需历史满足率 >= 80%；否则拒绝或限定 universe。
2. 横截面 Rank IC 均值方向符合假设，Newey-West 调整后 `|t| >= 2`；月度 IC 胜率 >= 55%。
3. 五分层收益整体近似单调，顶部与底部组合差经成本后为正；用 Spearman 单调性和 top-bottom t 值，不只看一张图。
4. 至少三个子区间、主要行业/规模桶中方向一致；滚动 12 个月 IC 不应由单一短区间贡献超过 50%。
5. 换手与成本后 alpha 合格；默认 participation <= 10% ADV，压力成本为基准成本 2 倍仍不过度失效。
6. 与已入库因子的绝对相关性 < 0.8；超阈值时只有显著改善组合边际 IC/净 Sharpe 才保留。
7. 多候选搜索使用 Benjamini-Hochberg FDR 或 Deflated Sharpe Ratio；登记总尝试次数与搜索空间。
8. 参数扰动、数据源替代和 universe 扰动后结论稳定；只在尖锐单点参数有效则拒绝。
9. 冻结 OOS 只允许一次主评估；未达标不能根据 OOS 反馈调参后继续称其为 OOS。
10. 门禁同时输出 `pass/fail/waiver`；waiver 必须有审批人、理由、范围和到期时间。

## 8. 因子组合与策略构建

先对通过门禁的因子按统一日期/universe 对齐并正交化或聚类去冗余，再形成预期收益。MVP 不用复杂深度模型，采用两层稳健方法：

- 因子层权重：滚动训练窗内按收缩后的 ICIR 加权，设置单因子上限，并对权重做指数平滑；也可用等权作为必须超越的基线。
- 证券层组合：`alpha_i = Σ w_k z(factor_ik)`，用带 L2 正则的凸优化最大化 `alpha'w - λ_r w'Σw - λ_t turnover - estimated_cost(w)`。

约束包括净/总敞口、单票、行业、风格 beta、国家/币种、流动性、ADV participation、借券可用性、换手和持仓数。风险模型使用 point-in-time 暴露与协方差；先支持 shrinkage covariance + 行业/风格因子风险。优化失败必须降级为受约束分位数组合或上一期可行仓位，并记录降级，不能静默输出空组合。

策略门禁比较等权、单因子和组合基线，要求组合提升来自分散而非更高杠杆。输出 `StrategySpec`：因子版本、权重训练法、风险/成本模型版本、约束、再平衡、信号/订单时钟和退出规则。

## 9. 回测与防偏差清单

- **样本选择偏差**：历史 universe、退市证券、IPO/停牌规则均 point-in-time。
- **前视偏差**：双时间数据、真实公告延迟、滞后执行、历史行业/指数成分。
- **幸存者偏差**：证券主数据保留退市、更名、并购和 delisting return。
- **复权偏差**：区分研究价格、成交价格和总回报；企业行动在正确时点入账。
- **数据挖掘偏差**：实验预注册、尝试计数、FDR/DSR、冻结 OOS。
- **重叠标签偏差**：purged walk-forward + embargo，持有期重叠时使用 HAC 标准误。
- **模型拟合泄漏**：所有 scaler/imputer/neutralizer/risk model 只用当时训练数据。
- **执行偏差**：next-bar 成交、bid-ask、佣金、税费、滑点、冲击、排队/不可成交、借券费。
- **容量幻觉**：ADV 参与率、交易天数、冲击曲线、组合拥挤度和 AUM 扫描。
- **再平衡时钟错误**：信号、订单、成交、持仓和收益五个时钟单独记录。
- **随机性/缓存污染**：固定 seed，缓存键包含 IR、数据快照、代码和配置哈希。
- **基准误配**：基准与 universe、币种和再投资假设一致。

建议 walk-forward：例如训练 3 年、验证 1 年、测试 6 个月，向前滚动；模型/权重只在每个训练窗重估。最后保留完全封存的 12 个月 final holdout。报告同时展示毛/净收益、Sharpe/Sortino、最大回撤、Calmar、换手、暴露、容量曲线、各折分布和失败期，不只展示聚合曲线。

## 10. Agent 与 HITL 编排

Agent 采用“受限工具 + typed output + 审批节点”，不采用自由聊天式多 Agent 相互调用：

- Intake Agent：生成 HypothesisSpec。
- Literature/Paper Agent：抽取证据和实验设定。
- Formula Agent：LaTeX/AST 到 IR 草案。
- Data Mapping Agent：字段候选与差异说明。
- Research Critic Agent：寻找反例、重复因子和不可证伪表述。
- Report Agent：只读取签名后的指标和 provenance，生成叙述。

HITL 必经点：研究命题与 OOS 冻结、低置信度公式、proxy 数据映射、正式全量计算预算、门禁 waiver、策略发布。Agent 无权访问生产交易凭证、修改数据快照、修改门禁结果或执行任意代码。每个 Agent 输出须过 JSON schema、引用校验和策略引擎；最多两次自动修复，之后进入人工队列。

## 11. 建议技术栈与接口

选择一套主栈，避免早期多引擎口径漂移：

- Python 3.12，Pydantic v2 定义契约；Polars + DuckDB 作为 MVP 计算层，数据量扩大后同一 IR 编译到 Ray/Spark。
- Parquet + Apache Iceberg 存双时间 lakehouse；S3/MinIO 存不可变 artifact；PostgreSQL 存控制面与状态。
- Dagster 编排资产 DAG、分区、重试和 backfill；Temporal 只在跨天人工审批/长事务变复杂后引入。
- FastAPI + OpenAPI/JSON Schema 提供控制接口；gRPC/Arrow Flight 仅用于大规模内部数据传输。
- MLflow 记录参数/指标/artifact，OpenLineage 记录 lineage；OpenTelemetry + Prometheus/Grafana 做观测。
- PDF：PyMuPDF/Docling 版面解析，OCR 采用受控服务；公式识别模型输出必须保留页级证据。
- 回测采用自研薄内核（明确五时钟与账本）或先接 Qlib 做研究计算，但最终成交模拟需统一到本系统契约；不同时并存多个“收益口径”。
- OSQP/CVXPy 做凸优化；Great Expectations 或 Pandera 实现数据契约；OPA 实现授权和发布策略。

核心接口：

```text
POST /v1/hypotheses                 -> hypothesis_id
POST /v1/papers                     -> paper_id + source_hash
POST /v1/candidates:generate        -> candidate_set_id
POST /v1/factors:validate           -> validation_run_id
POST /v1/evaluations                -> evaluation_run_id
POST /v1/strategies                 -> strategy_id
POST /v1/backtests                  -> backtest_run_id
GET  /v1/runs/{id}/lineage          -> provenance DAG
GET  /v1/reports/{id}               -> signed report manifest
POST /v1/approvals/{gate}:decide    -> signed decision
```

所有写接口要求 `Idempotency-Key`、actor、reason、parent artifact 和 budget；异步任务返回 run_id，通过事件 `RunStateChanged` 订阅状态。

## 12. 元数据、版本与实验追踪

最小实体：`Hypothesis`、`Paper`、`EvidenceSpan`、`DatasetSnapshot`、`FieldSemantics`、`FactorDefinition`、`FactorRun`、`EvaluationRun`、`GateDecision`、`StrategySpec`、`BacktestRun`、`Report`、`Approval`。

版本规则：IR/schema/门禁/数据字段采用 SemVer；数据快照用 Iceberg snapshot ID；代码用 Git SHA + OCI digest；环境用 lock hash；LLM 记录 provider/model、temperature、seed（若支持）、prompt/template hash、retrieval corpus snapshot、token usage 和输出 hash。实验追踪必须记录失败实验和被拒候选，防止只保留成功结果造成选择偏差。

报告 manifest 对所有引用 artifact 计算 Merkle root 并签名；任何结果都能用 `run_fingerprint` 一键重放。因许可证不能固化的数据至少保存供应商版本、查询条件、行数/统计摘要和可验证 hash。

## 13. 失败处理

- 数据供应商超时、临时算力失败：指数退避重试，沿用幂等键；超过阈值进入 dead-letter queue。
- schema 漂移、时间语义缺失、哈希不一致：立即 quarantine，不自动猜测字段。
- PDF/OCR/公式低置信度：保留页图与候选解释，转 HITL；不能用无引用的 LLM 猜测补齐。
- 计算中 NaN/Inf、横截面为空、窗口不足：按 IR missing policy 处理并生成质量指标；超阈值硬失败。
- 资源超预算：保存 checkpoint 和部分 artifact，状态 `BUDGET_EXCEEDED`，需审批后恢复。
- 优化不可行：输出冲突约束诊断，按预注册降级策略执行；不得自动放宽风险约束。
- 重放结果不一致：标记 `NON_REPRODUCIBLE` 并阻断发布，比较数据、代码、环境与随机性指纹。
- LLM 不可用：已有 IR 的确定性流水线继续运行；新命题可人工填写结构化表单。

## 14. 安全与成本控制

- 数据按 license/classification 分级；受限行情、客户持仓、凭证禁止出域，LLM 前做字段白名单和脱敏。
- Agent 运行在无生产凭证的沙箱，网络 egress allowlist、只读数据挂载、CPU/内存/时长限额；禁止 `eval` 和任意 Python。
- RBAC/ABAC 分离研究者、数据管理员、审批人和发布人；高风险操作双人审批，全量审计日志防篡改。
- Prompt injection 防护：PDF 文本一律视为不可信数据，不能改变系统策略或调用权限；工具参数经 schema 和 policy 校验。
- secrets 置于 Vault/KMS，短期凭证、定期轮换；artifact 加密传输/静态加密并设保留期和删除策略。
- 成本分层：先静态检查与 5% universe/短区间 smoke，再全样本；表达式子图缓存和内容寻址去重；每命题候选数、LLM token、CPU-hour 和存储设预算。
- 只有通过 cheap gates 的候选进入昂贵容量/压力测试；预算使用量和估算剩余成本展示给审批者。

## 15. MVP 到生产路线图

### 阶段 0：契约与金标准（2-3 周）

定义 Factor IR v1、五时钟、双时间数据契约、状态机、门禁 v1；选 3 个已知因子和 1 篇公开论文作为 golden cases。完成目标：相同快照可重复得到逐位一致结果。

### 阶段 1：MVP（6-8 周）

支持日频股票、路径 A、文本型 PDF 路径 B、20 个白名单算子、PIT Gateway、IC/分层/换手/相关性、基础成本模型、purged walk-forward、HTML/PDF 报告和 4 个 HITL 门。单机/中型节点运行，控制面为模块化单体。

### 阶段 2：研究 Beta（6-10 周）

加入 OCR/公式置信度、容量/风险模型、凸优化、多重检验、MLflow/OpenLineage、RBAC、预算/队列、重放工具；shadow 用户验证 20-50 个真实命题。

### 阶段 3：生产化（8-12 周）

Iceberg 数据版本、分布式计算、HA 编排、签名报告、灾备、SLO、paper trading 和 live shadow；通过模型风险、数据许可和安全评审后才输出可部署包。

暂缓：端到端自动下单、在线自我修改 Agent、分钟级全市场、复杂深度组合模型。它们会显著扩大审计和执行风险，不是验证研究闭环的必要条件。

## 16. 验收指标

- **正确性**：golden factors 与人工基准逐日值误差 < 1e-10（浮点容差）；所有测试样例无 `available_time > signal_time`。
- **复现性**：同 run fingerprint 重跑关键指标一致率 100%；报告任一图表可在 3 次跳转内定位到数据/IR/代码证据。
- **论文复现**：golden paper 关键公式/变量/样本设定人工核验准确率 >= 95%，每项均有页码/bbox；中间表方向和数量级可解释。
- **门禁覆盖**：100% 正式候选通过数据、泄漏、统计、成本和稳定性门禁；所有 waiver 有审批与到期时间。
- **偏差测试**：植入未来字段、幸存者 universe、错误披露日期、全样本标准化等 mutation cases，拦截率 100%。
- **性能**：MVP 3000 股票、10 年日频、单个中等因子计算 + 基础评估 P95 < 10 分钟；缓存命中重跑 < 2 分钟。
- **可用性**：异步任务成功/明确失败率 >= 99%，无静默失败；研究 Beta 月度重放成功率 >= 99.5%。
- **成本**：smoke 阶段淘汰失败候选使全量计算 CPU-hour 降低 >= 60%；单命题 LLM/计算预算可见且不可越权超支。
- **研究价值**：相较人工流程，标准论文首次复现耗时中位数下降 >= 50%，但不以“发现正 alpha 数量”作为验收 KPI。

## 17. 关键风险与缓解

1. **数据时间语义错误是最大风险**：通过双时间字段、PIT Gateway、mutation test 和禁止裸表访问控制。
2. **LLM 生成看似合理但错误的公式**：受限 IR、证据 bbox、符号表校验、低置信度 HITL，不让 LLM 直接执行。
3. **因子挖掘导致多重试验和 OOS 污染**：预注册、候选预算、尝试全记录、FDR/DSR、一次性封存 OOS。
4. **研究结果与真实成交脱节**：五时钟账本、不可成交状态、冲击/借券/税费和容量压力测试。
5. **多数据源/多引擎口径漂移**：MVP 单主栈、IR 语义测试、golden cases；扩展编译后必须做 cross-engine conformance。
6. **过度自治导致责任不清**：Agent 无发布权，关键映射/冻结/waiver/发布由签名 HITL 决策。
7. **论文版权和供应商许可**：来源许可元数据、域隔离、只保留允许的证据和派生摘要。
8. **稳定历史不代表未来有效**：机制先验、子区间/压力测试、衰减监控、shadow 和明确 kill criteria。

## 18. 具体示例：从论文到回测报告

**输入**：上传一篇研究“标准化意外盈利（SUE）预测未来 1 个月股票收益”的 PDF，指定美股、2008-2024、日频持仓月度再平衡、行业/规模中性、AUM 1 亿美元。

1. 系统保存 PDF 哈希，抽取公式 `SUE=(EPS_q-EPS_{q-4})/std(EPS_q-EPS_{q-4}, 8 quarters)`，证据为第 7 页公式 2；抽取样本过滤、延迟和五分层设定。
2. `diluted_eps` 映射到 PIT 基本面数据；论文未明确供应商到达时间，系统采用 vendor timestamp，并登记为“本地口径差异”，由研究者审批。
3. Formula Agent 生成 `quality.sue_3m@1.0.0` IR。静态分析发现表达式本身无未来窗口，编译器推导信号最早在财报到达后的下一交易日开盘可执行。
4. smoke run 在 2018-2020 的 5% 股票上发现 9% 样本分母为零/历史不足；按预注册策略设为 null，不用横截面均值填充，覆盖率仍为 78%，通过数据门禁。
5. 全量计算得到月度 Rank IC 均值 0.031、NW t=3.1、胜率 59%；五分层近似单调。与盈利质量库中已有因子相关性 0.63；2 倍成本下 top-bottom 仍为正。数值仅作为示例，实际必须由 run artifact 生成。
6. faithful 分支复现论文方向，但幅度较小，报告归因为样本期、退市处理和披露时间更保守；local adaptation 分支做行业/规模中性并进入组合。
7. 使用 3 年训练、1 年验证、6 个月测试滚动，最后 2024 年作为封存 holdout；SUE 与价值、动量因子按收缩 ICIR 加权，证券层做行业中性凸优化，单票 1%、ADV 10%、年化换手上限 400%。
8. 回测按月末收盘生成信号、下一可交易日开盘下单，计入 spread、佣金、非线性冲击、借券费和不可成交；输出订单/成交/持仓/现金账本。
9. 报告展示各折毛/净收益、IC、分层、暴露、换手、回撤、成本拆解、AUM 容量曲线、holdout 和压力测试；每个图链接到 run fingerprint、IR、数据 snapshot 和 PDF bbox。
10. 若封存 OOS 未达预注册门槛，状态为 `REJECTED`，仍发布“研究审计报告”，但不生成可部署策略包；不得调参后覆盖原结果。

## 19. 确定性实现与 LLM 边界总结

**必须确定性实现**：IR schema/编译器、算子语义、双时间数据访问、数据校验、泄漏静态/动态检测、因子计算、统计检验、多重检验、优化、成本/风险模型、回测账本、状态机、哈希/签名、门禁与权限策略。

**可交给 LLM，但必须受约束**：自然语言到 HypothesisSpec、论文段落/表格/公式候选抽取、变量语义映射候选、经济机制与反例生成、失败原因解释、审计报告叙述。其输出必须 typed、带证据、可拒绝且不能直接改变最终数值或审批状态。

## 20. 优于常见做法的 5 条关键判断

1. **统一 IR 是系统核心，不是 notebook 模板**：两条上游在同一语义层汇合，使人工创意、LLM 候选和论文公式接受完全相同的时点、门禁和回测规则，避免两套研究口径。
2. **把“何时可知”做成类型系统的一部分**：多数平台只在回测代码里约定 lag；本方案从输入字段到算子传播 available_time，并在编译期和运行期双重阻断未来函数。
3. **论文复现先对中间证据，不先追最终 Sharpe**：PDF bbox、公式 AST、变量映射和中间表构成证据链，能区分忠实复现与本地适配，减少“结果好看即复现成功”的常见误判。
4. **失败实验和尝试次数也是一等数据**：预注册、候选预算、FDR/DSR 与封存 OOS 共同约束研究自由度，比只保存胜出 notebook 更真实地估计过拟合。
5. **Agent 被限定为语义协作者而非数值裁判**：LLM 提高探索和文献理解效率，但无权执行任意代码、改门禁或发布策略；系统在获得自动化收益的同时保留可重放、可问责的确定性内核。
