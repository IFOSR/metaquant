# Kimi 量化研究 Pipeline 端到端设计方案

版本：v1.0 ｜ 作者：量化系统架构师（Orca worker task_f1e43c4f8346）

---

## 0. 设计立场（先讲取舍）

本方案的核心取舍有三条，后文所有设计都服从它们：

1. **LLM 只负责"提出候选与解释"，确定性代码负责"计算与裁决"。** 因子表达式的生成、论文公式的理解可以交给 LLM；但因子值的计算、IC 计算、门禁判定、回测撮合必须是纯确定性、可重放的代码。LLM 输出永远只是"提案"，不直接进入计算路径。
2. **Factor IR 是全系统唯一的事实源（single source of truth）。** 两条挖掘路径、论文复现、人工输入，最终都必须落成同一份 IR；评估、组合、回测只消费 IR，不关心因子来自哪里。这保证了两条上游路径在下游完全同构。
3. **门禁前置、回测后置。** 大量廉价检查（schema 校验、未来函数静态扫描、数据可得性）在昂贵的全量计算和回测之前运行，尽早杀死坏因子，控制算力与 LLM 成本。

---

## 1. 目标与明确假设

### 1.1 目标

- 支持两类上游输入（研究假设 / 论文 PDF），产出**可审计的候选因子**；
- 候选因子经过统一定义、校验、评估、组合、回测，产出**可审计的研究报告**；
- 全链路每个产物可追溯：谁提出、依据什么数据、用什么代码版本、在哪次实验中、被哪道门禁放行或拒绝。

### 1.2 明确假设（不满足则需重新评审设计）

- 标的范围：中国 A 股股票为主，日频 + 分钟频；后续可扩展期货/ETF。横截面因子为主，时序因子作为二等公民（IR 支持但 MVP 不做专门优化）。
- 数据：已有行情（OHLCV、涨跌停、停复牌、复权因子）、财务报表、行业分类、指数成分等结构化数据源，由独立数据平台团队保障质量；本系统**不**负责采集，只负责校验与消费。
- 用户：量化研究员（人工输入假设）、研究平台自身（LLM 自动挖掘）；不要求用户写代码，但允许高级用户直接提交 IR。
- 非目标：实盘交易执行、高频（tick 级）策略、组合层面的实时风控。回测止步于"研究级回测 + 交易成本与风控建模"，输出供实盘前人工决策。
- LLM 能力：具备长文档解析（百页 PDF）、代码生成、结构化输出（JSON schema 约束解码）能力；但不假设其金融判断可靠，所有数值结论必须由确定性计算复算。

---

## 2. 总体架构与组件边界

```
┌────────────────────────── 上游输入层 ──────────────────────────┐
│  A. 假设输入（人工表单 / LLM 对话）      B. 论文输入（PDF/URL）  │
└──────────────┬───────────────────────────────┬────────────────┘
               ▼                               ▼
      ┌─────────────────┐           ┌──────────────────────┐
      │ 假设挖掘 Agent    │           │ 论文复现 Agent         │
      │ (HypothesisMiner)│           │ (PaperReproducer)     │
      └────────┬────────┘           └──────────┬───────────┘
               │  两者只产出一件事：Factor IR 草案 + 出处证据
               ▼                               ▼
┌──────────────────────── Factor Registry（因子注册中心）────────────────────────┐
│  IR 校验 → 静态安全扫描 → 版本化入库 → 触发评估流水线（状态机驱动）              │
└────────┬─────────────────────────────────────────────────────────────────────┘
         ▼
┌──────────────────── 评估层（全部确定性代码）────────────────────┐
│  数据校验 → 去未来函数/防泄漏 → 因子计算引擎 →                    │
│  IC/分层/换手/稳定性/相关性/容量 评估器 → 验证门禁 Gatekeeper     │
└────────┬────────────────────────────────────────────────────────┘
         ▼ 通过门禁的因子进入因子库（Alpha Pool）
┌──────────────────── 组合与策略层 ────────────────────────────────┐
│  因子组合器（IC加权/正交化/ML 可选）→ 策略构建器（信号→持仓）      │
│  → 交易成本模型 + 风控约束                                        │
└────────┬────────────────────────────────────────────────────────┘
         ▼
┌──────────────────── 回测与报告层 ────────────────────────────────┐
│  Walk-forward / OOS 回测引擎 → 归因与压力分析 → 审计报告生成器    │
└─────────────────────────────────────────────────────────────────┘
                贯穿全局：Orchestrator（状态机）、Metadata/实验追踪、HITL 审批点
```

### 组件边界（每个组件的输入/输出契约）

| 组件 | 输入 | 输出 | 明确不做的事 |
|---|---|---|---|
| HypothesisMiner | 假设文本、市场背景、约束（universe/频率/禁区） | Factor IR 草案列表 + 推理说明 | 不计算因子值、不做评估 |
| PaperReproducer | PDF/URL | Factor IR 草案 + 论文证据链（公式定位、参数表） | 不承诺"复现论文收益" |
| Factor Registry | IR 草案 | 版本化 Factor 实体（含 lineage） | 不评估 |
| Validation 层 | Factor + 数据快照 | 校验报告（pass/fail + 证据） | 不修改因子 |
| Evaluator | Factor + 数据快照 | 标准指标集（IC/分层/…） | 不做策略 |
| Gatekeeper | 校验报告 + 指标集 | 门禁裁决（pass/review/reject） | 不放行例外（例外走 HITL） |
| Composer/Strategy | 因子库 + 组合配置 | 组合定义、目标持仓序列 | 不接触原始数据 |
| Backtester | 持仓序列 + 行情 + 成本/风控模型 | 交易明细、净值、归因 | 不产生新因子 |
| Reporter | 全链路 artifact | 可审计报告（HTML/PDF） | 不写回任何上游状态 |

关键边界原则：**评估层以下永远不知道 LLM 的存在**。下游只认 IR 与数据快照，这使得"人工提交的 IR"和"LLM 挖掘的 IR"享受完全相同的待遇与怀疑。

---

## 3. 两条因子挖掘路径

### 3.1 路径 A：假设驱动挖掘（人工 / LLM）

流程：`假设输入 → 结构化 → 算子组合搜索 → IR 草案集 → 入库`

1. **输入结构化（LLM 可做）**：把自然语言假设（如"高换手的小盘股短期反转更强"）解析为结构化假设卡：
   ```yaml
   hypothesis:
     economic_rationale: 流动性溢价与散户过度交易导致短期反转
     direction: negative          # 因子值越大预期收益越低
     universe_hint: small_cap
     horizon_days: [1, 5, 10]
     constraints: {exclude_st: true, min_listing_days: 120}
   ```
2. **候选生成（LLM 提案 + 确定性枚举混合）**：
   - 模板枚举：预定义算子库（`ts_rank, ts_delta, decay_linear, zscore, group_neutralize…`）× 原子数据字段（`close, volume, turnover, pe…`）做受限笛卡尔积，类似 AlphaGen/WorldQuant alpha 挖掘的确定性部分；
   - LLM 变体生成：基于假设卡生成 10–30 个 IR 表达式变体；
   - 所有候选统一走第 6 节的静态扫描，非法表达式直接丢弃。
3. **预算控制**：每条假设设候选数上限（默认 32）与评估预算上限，防止组合爆炸烧算力。
4. **HITL 点**：假设卡结构化结果展示给用户确认（可配置为免确认）。

### 3.2 路径 B：论文复现挖掘（PDF / URL）

流程：`PDF 解析 → 公式与实验设定抽取 → 映射为 IR → 适配性改写 → 入库`

1. **解析（LLM + 版面解析工具）**：PDF → 结构化文档树（章节、公式、表格、图）。公式用 LaTeX OCR（如 pix2tex 类工具或直接用多模态模型）+ 版面坐标定位。
2. **抽取（LLM）**：产出"论文事实表"（PaperFactSheet）：
   ```yaml
   paper_facts:
     title/authors/year/venue
     claimed_factors:            # 每个因子一条
       - name: Momentum 12-1
         formula_latex: "ret_{t-12}^{t-1}"
         formula_location: {page: 4, eq: 3}
         data_required: [daily_returns]
         parameters: {lookback: 252, skip: 21}
     experiment_setup:
       universe: "US common stocks, CRSP"
       sample_period: "1963-2015"
       rebalance: monthly
       weighting: value-weighted
       reported_metrics: {ic: 0.05, long_short_sharpe: 1.2}
   ```
3. **映射（LLM 提案，确定性校验）**：把公式翻译为 Factor IR 表达式。翻译必须输出**逐项对照表**（论文符号 → IR 算子 → 本地数据字段），缺失字段显式标记 `unavailable`，禁止静默近似。
4. **适配性改写（HITL 必审）**：论文实验设定与本地环境不一致时（如 CRSP 美股 → A 股、月频 → 日频），生成"适配记录"（AdaptationRecord），逐条列出改动及理由，**必须人工确认后才入库**。这是论文路径最重要的 HITL 点。
5. **复现基准**：若论文报告了指标且本地数据可构造相近设定，先跑"原设定复现"，再跑"本地设定"，两者都进报告，避免把"换市场后的衰减"误当"复现失败"。

两条路径的汇合点：都输出 `FactorIR + Provenance`（出处）。路径 A 的出处是假设卡 + 生成日志；路径 B 的出处是 PaperFactSheet + 对照表 + 适配记录。

---

## 4. Factor IR / DSL（统一定义层）

### 4.1 设计原则

- **声明式、无副作用**：因子 = 纯函数表达式 + 元数据。不允许任意 Python 代码入库（安全与可重放性考虑）。高级用户需要自定义算子时，走"算子注册"流程（提交代码评审后进入算子库），而不是在因子里嵌代码。
- **静态可分析**：AST 形式存储，支持静态提取数据依赖、时间窗口、截面操作——这是去未来函数扫描（6.2）能确定性实现的前提。
- **人类可读、机器可执行**：YAML 序列化；计算引擎把 AST 编译为向量化执行计划。

### 4.2 Schema（核心字段）

```yaml
factor_ir:
  id: fctr_01J…              # 系统分配
  version: 3                 # 单调递增，任何字段变更 = 新版本
  name: intraday_reversal_5d
  status: candidate          # 状态机见第 5 节
  expression: |              # DSL，AST 化存储
    group_neutralize(
      industry,
      neg(ts_mean(div(sub(close, open), open), 5))
    )
  semantics:                 # 语义层，供 LLM/报告/HITL 阅读，不参与计算
    description: 日内收益 5 日均值的反转，行业中性化
    direction: negative
    economic_rationale: …
  universe:                  # 显式声明，评估与回测共用
    market: CN_A
    exclude: [st, suspended, listing_lt_120d]
  frequency: 1d
  data_dependencies:         # 静态扫描自动生成，人工声明仅作交叉校验
    - {field: close, lookback: 5, adjustment: qfq}
    - {field: open,  lookback: 5, adjustment: qfq}
    - {field: industry, lookback: 0}
  execution:
    engine: vectorized       # vectorized | dag（复杂依赖时）
    point_in_time: true      # 强制 PIT 数据视图
  provenance:                # 出处（路径 A/B 各一套子结构）
    source: paper            # human | llm_hypothesis | paper
    ref: {paper_id: pp_01J…, formula_location: {page: 4, eq: 3}, adaptation_id: ad_01J…}
    created_by: agent:paper-reproducer@v0.3
  evaluation:                # 评估结果由系统回写（只追加，不覆盖）
    latest_gate: {verdict: pass, run_id: run_01J…, at: …}
```

### 4.3 算子白名单（MVP）

- 时序：`ts_mean, ts_std, ts_delta, ts_rank, ts_max/min, decay_linear, ts_corr, ts_sum, delay`
- 截面：`zscore, rank, winsorize, group_neutralize(industry|market_cap), scale`
- 算术：`add, sub, mul, div(带除零保护), log, sign, abs, neg, clip`
- 数据字段：`open/high/low/close/vwap/volume/amount/turnover/free_float_mktcap/pe/pb/industry/limit_up/limit_down/suspended`

算子即代码库中带单元测试的注册函数；**新算子必须声明其最大 lookback**，否则静态扫描拒绝。

---

## 5. 完整数据流与状态机

### 5.1 数据流（一次因子生命周期的数据视角）

```
输入(假设/PDF)
 → 草案 IR（内存，未入库）
 → [校验+静态扫描] → Registry 持久化（IR v1, status=candidate）
 → Orchestrator 派发评估 Run：
     数据快照锁定（snapshot_id = 数据版本 + universe 版本 + 日历版本）
     → 因子计算（结果落盘：factor_values.parquet, hash 索引）
     → 指标计算（metrics.json）
     → 门禁裁决（gate_verdict.json）
 → 若 pass：进入 Alpha Pool（status=validated）
 → 组合构建消费 Alpha Pool（combination_def.yaml）
 → 策略定义（strategy_def.yaml：信号→持仓规则 + 成本/风控参数）
 → 回测 Run（同样锁定快照）→ trades/nav/attribution
 → 报告生成（report_id，引用上述全部 artifact 的 hash）
```

不可变原则：**快照、计算结果、裁决、回测产物全部按内容 hash 寻址、只追加**。任何"重跑"都是新 Run，永不覆盖旧结果——这是可审计性的根基。

### 5.2 因子状态机

```
draft → candidate → validating → validated → pooled → archived
                     │    │           │
                     ▼    ▼           ▼
                  rejected  review_pending(HITL)  decayed(定期复检降级)
```

- `draft → candidate`：通过 schema 校验 + 静态安全扫描（自动）。
- `candidate → validating`：评估 Run 启动（自动）。
- `validating → validated | rejected | review_pending`：门禁裁决（自动；`review_pending` 必须人工裁决，限时 48h 超时自动 reject）。
- `validated → pooled`：进入因子库可被组合器引用（自动，但组合引用需策略级审批）。
- `pooled → decayed`：定期复检（见 7.4）发现样本外衰减超阈值时自动降级，降级触发引用它的策略的告警。

### 5.3 Run（执行实例）状态机

```
queued → running → succeeded | failed(retryable) | failed(permanent) | cancelled
```

所有重试产生 `attempt_n` 记录；Run 与 Factor/Strategy 版本、数据快照、代码版本四元组绑定。

---

## 6. 论文复现可追溯机制

目标：报告中任意一个数字，能反查到"论文第几页哪个公式、被谁翻译成什么 IR、改了哪些设定、用的哪份数据"。

1. **三级证据链**：
   - L1 论文层：PDF 原件 hash 存证；PaperFactSheet 中每个字段带版面坐标（page/bbox）；公式同时保留 LaTeX 原文与截图切片。
   - L2 翻译层：`TranslationLedger`——论文符号 → IR 算子 → 数据字段的逐项映射表，每一项标注 `confidence`（LLM 自评）与 `status`（exact / approximated / unavailable）。approximated/unavailable 超过 30% 的因子自动转 HITL。
   - L3 适配层：AdaptationRecord（universe/频率/调仓期/加权方式的差异清单 + 人工签字）。
2. **双轨复现**：能构造原设定就先复现原设定（对照论文报告值），再跑本地设定。报告并列展示"论文值 / 原设定复现值 / 本地值"三列。
3. **禁止条款**：LLM 不得修改 PaperFactSheet 中的"论文报告值"；本地指标一律由确定性计算产出。LLM 对论文的"解读性总结"在报告中单独标注为"AI 解读，未经数值验证"。

---

## 7. 因子验证门禁（Gatekeeper）

### 7.1 评估指标体系（全部确定性计算）

| 类别 | 指标 | 说明 |
|---|---|---|
| 预测力 | Rank IC 均值/ICIR、t 值、分年 IC | 多 horizon（1/5/10/20d） |
| 单调性 | 10 分层年化收益、多空价差、单调性检验（Spearman） | 分层收益曲线存图 |
| 换手 | 单边换手率（日/月） | 直接决定容量与成本 |
| 稳定性 | 滚动 12 月 IC 方差、半衰期 | 判衰减速率 |
| 相关性 | 与 Alpha Pool 现有因子 IC 序列最大相关系数 | 增量价值判断 |
| 容量 | 按 ADV（20 日成交额）× 参与率上限估算可承载资金 | 见 9.3 |
| 稳健性 | 分行业/分市值子样本 IC | 防单一暴露驱动 |

### 7.2 门禁规则（默认阈值，组织可配置但变更留痕）

- **自动 reject**：ICIR < 0.15；|IC| < 0.01；与库内因子相关 > 0.85 且 IC 增量不显著；任何静态安全扫描 fail；数据覆盖率 < 90%。
- **自动 pass**：ICIR ≥ 0.3 且 |IC| ≥ 0.02 且分层单调性显著 且 相关 < 0.7 且 容量 ≥ 组织下限。
- **中间地带 → review_pending（HITL）**：宁可多审，不放水。
- 阈值本身纳入版本管理（`gate_policy.yaml`），每次门禁裁决记录所用策略版本。

### 7.3 去未来函数与防泄漏（门禁的前置环节）

1. **静态扫描（确定性）**：IR 的 AST 上做数据流分析——每个算子声明 lookback，静态推导表达式整体的最大回看窗口；检测 `delay` 参数为负、使用了 t 日之后才可得的字段（如财报公告日之前的财报值）。
2. **PIT 数据视图（基础设施级）**：财务数据按公告日（announce date）入库，查询引擎只返回 t 日盘前已公开的数据。这不是因子层的约定，而是数据访问层的硬约束——因子代码物理上拿不到未来数据。
3. **动态对拍（抽查）**：对通过静态扫描的因子，用"延迟一日数据重算"对拍：因子在 t 日的值用截至 t-1 的数据应可完全复现；不一致即 reject 并告警（说明存在隐性泄漏）。
4. **复权与停牌**：统一后复权计算因子、信号落在真实可交易价格上；停牌/涨跌停标的在评估与回测中显式标记为不可成交（见 9）。

### 7.4 定期复检

已入库因子每月用最新数据重算 IC；连续 3 个月 IC 衰减超 50% 或符号翻转 → `decayed` 并通知策略负责人。复检是状态机的一部分，不是临时脚本。

---

## 8. 策略构建方法

### 8.1 因子组合（Composer）

MVP 提供三种组合器，按复杂度递增，默认从最简开始：

1. **等权/IC 加权**：对入选因子 zscore 后按滚动 12 月 ICIR 加权。可解释、易审计，是默认基线。
2. **正交化组合**：按相关性排序，逐个对已有因子残差化（对称正交），控制冗余。需要声明正交化顺序，顺序进版本。
3. **ML 组合（LightGBM，可选启用）**：横截面排序学习，标签为未来 N 日超额收益。**训练/验证/测试严格按时间切分**，特征 = 因子截面值，禁止任何 t 日之后的信息进入特征工程。ML 组合本身也视为一个"复合因子"，重新走一遍门禁。

### 8.2 策略构建器（信号 → 持仓）

- 组合得分 → 目标持仓：`top_n 等权` 或 `得分比例权重`，叠加约束：单票上限、行业偏离上限、双便可交易性过滤（停牌/ST/涨跌停/上市天数）。
- 调仓规则：固定周期（默认日度开盘后以开盘价成交，论文复现按其原设定）+ 缓冲带（目标权重变化 < 阈值不动仓，压换手）。
- 输出：`strategy_def.yaml`（组合配置 + 持仓规则 + 成本/风控参数 + universe + 日历），策略定义与因子一样是版本化 artifact。

### 8.3 交易成本与风控建模

- 成本模型：`cost = commission + stamp_tax(卖出) + slippage`，滑点 = `k × σ_daily × sqrt(order/ADV)` 的平方根冲击模型，k 按历史成交校准，默认保守取 0.5；另设**最低滑点下限**（默认 5bp）防止小盘股成本被低估。
- 风控约束（回测内建模，非实盘）：最大回撤触发降仓、单日换手上限、行业/风格暴露上限、容量约束（持仓金额 ≤ ADV × 参与率上限）。

---

## 9. 回测防偏差清单（Backtest Bias Checklist）

回测引擎的每项防偏差措施都是**默认开启、关闭需显式声明并写入报告**的：

1. **生存者偏差**：universe 用历史成分股时点快照（指数成分按调样日回溯），退市股保留在数据中。
2. **前视偏差**：全部数据走 PIT 视图；信号用 t 日收盘前数据，成交在 t+1 开盘价（或显式声明的撮合时点）。配置与撮合假设写入报告首页。
3. **交易成本低估**：9.3 成本模型 + 最低滑点下限 + 流动性参与率上限；报告同时给零成本净值作对照（明确标注为不可实现上界）。
4. **涨跌停/停牌**：限价单撮合——涨停不能买、跌停不能卖、停牌不成交，顺延处理规则显式声明。
5. **过拟合 / 多重检验**：walk-forward 切分（如 5 年训练 → 1 年验证，滚动推进）；样本外区间在实验设计时**预先注册**（pre-registered OOS window），报告中区分 IS/OOS 指标；对同批挖掘的 N 个因子做 Bonferroni/White Reality Check 校正提示（给出校正后显著性，不隐藏原始值）。
6. **参数微调诱导**：门禁阈值、组合参数、缓冲带阈值在 OOS 区间上**冻结**，OOS 只跑一次；若 OOS 失败重调，则产生新的、更晚的 OOS 区间——重调次数本身写进报告。
7. **数据修正偏差**：财务数据用首次公告版本，不用事后更正版（PIT 的另一层含义）。
8. **随机性**：所有含随机性的组件（ML 组合、抽样对拍）固定 seed 并记录。

---

## 10. Agent / HITL 编排

### 10.1 Agent 分工

| Agent | 职责 | 模型/确定性 |
|---|---|---|
| Orchestrator | 状态机驱动、Run 调度、重试、预算控制 | **确定性**（工作流引擎） |
| HypothesisMiner | 假设结构化、IR 变体生成 | LLM（结构化输出，JSON schema 约束） |
| PaperReproducer | PDF 解析、公式抽取、IR 翻译、适配建议 | LLM + 版面解析工具 |
| Critic | 对 LLM 产出做"红队"审查：查 IR 与假设/论文的一致性、找潜在泄漏模式 | LLM（独立会话，只读） |
| Gatekeeper | 门禁裁决 | **确定性** |
| Reporter | 报告叙事组织 | LLM 写稿 + 模板渲染（数字只能来自 artifact，禁止生成数字） |

原则：**凡是影响数值结论或放行决策的环节，确定性实现；LLM 只在"生成候选、理解文档、组织叙述"三处出现。**

### 10.2 HITL 审批点（共 5 处，均可配置但默认开启）

1. 假设卡确认（路径 A，可关）；
2. **论文适配记录确认（路径 B，不可关）**；
3. 门禁 `review_pending` 裁决（不可关）；
4. 策略进入 OOS 回测前的"实验注册"确认（不可关）；
5. 报告发布确认（不可关）。

审批通过统一前端（或 CLI/IM 机器人）完成，所有审批动作（谁、何时、批注）写入审计日志。审批超时策略：review_pending 48h 自动 reject；OOS 注册不超时（没有注册就没有 OOS，天然阻塞）。

### 10.3 编排实现

- Orchestrator 用持久化工作流引擎（Temporal / 自研状态机 + Postgres 队列表二选一，MVP 用后者），每个状态迁移是幂等事件；
- Agent 间不直接通信，全部通过事件 + artifact（内容寻址存储）交换，保证可重放；
- Critic 与生成 Agent 不共享上下文，避免"自评自夸"。

---

## 11. 建议技术栈及接口

### 11.1 技术栈（带取舍）

| 层 | 选型 | 理由 / 不选什么 |
|---|---|---|
| 语言 | Python 3.11（研究层）| 生态决定；性能热点用 Rust/Polars 而非换语言 |
| 因子计算 | Polars/DuckDB 向量化执行 IR | 不选 pandas 逐行循环；IR→Polars 表达式编译 |
| 存储 | Parquet（数据/因子值）+ Postgres（元数据/状态机）+ 内容寻址对象存储（artifact） | 不上分布式数仓，单机 DuckDB 够到 MVP 后很久 |
| 回测 | 自研事件驱动引擎（持仓序列→撮合） | 不直接用 backtrader/zipline：需要内建 A 股涨跌停、PIT、成本模型的可控实现 |
| 工作流 | MVP：Postgres 队列 + 状态机表；规模化：Temporal | 避免过早引入重型调度 |
| LLM 接入 | 统一 LLM Gateway（多 provider、JSON schema 约束解码、token 计量、缓存） | 禁止各 Agent 直连 API |
| 实验追踪 | MLflow（指标/参数）+ 自研 lineage 表（artifact hash 图） | MLflow 不管血缘，血缘自己建 |
| 前端 | MVP：报告即 HTML + CLI；后续加 Web 审批台 | 不做大而全平台 |
| PDF 解析 | 多模态 LLM + PyMuPDF 版面坐标 | 公式保留坐标与截图切片 |

### 11.2 关键接口（内部 API 契约）

```
POST /factors:submit        {ir: FactorIR}                      → {factor_id, version}
POST /runs:evaluate         {factor_id, snapshot_id, horizons}  → {run_id}
GET  /runs/{id}             → {status, metrics, gate_verdict, artifacts[]}
POST /strategies:submit     {strategy_def}                      → {strategy_id}
POST /runs:backtest         {strategy_id, snapshot_id, window}  → {run_id}
GET  /reports/{id}          → HTML/PDF + manifest(全部 artifact hash)
POST /approvals/{gate}      {artifact_id, decision, comment}    → 审计日志
```

所有写接口幂等（client 提供 idempotency key）；所有读接口可带 `as_of` 参数做时点查询。

---

## 12. 元数据、版本与实验追踪

- **四元组版本钉住一切**：任何 Run 记录 `{factor_version, strategy_version, snapshot_id, code_git_sha}`；报告 manifest 列出全部 artifact 的内容 hash。
- **Lineage 图**：`input(假设/PDF hash) → IR version → Run → metrics → gate → pool → strategy → backtest → report` 构成有向无环图，存 Postgres，支持正反向追溯查询。
- **数据快照**：`snapshot_id = hash(universe_def, calendar, 数据版本清单)`；数据平台每次数据落库打版本标签。
- **实验追踪**：MLflow 记录每次 Run 的参数与指标，用于横向比较；但**裁决依据以 Gatekeeper 落库的 verdict 为准**（MLflow 是分析工具，不是审计工具）。
- **LLM 调用日志**：prompt 模板版本、输入输出、token 数、成本全部落库（含 PaperFactSheet 等中间产物），既为审计也为成本分析。

---

## 13. 失败处理

| 失败类型 | 处理 |
|---|---|
| LLM 输出不合 schema | 结构化重试 ≤ 3 次（带错误反馈），仍失败 → 该候选丢弃并记录；整条路径失败 → 人工介入 |
| IR 静态校验失败 | 不入库，反馈给生成方（含 Critic 意见），计入生成质量指标 |
| 数据缺失/质量异常 | 数据校验层 fail-fast，Run 标记 `failed(permanent)` 并向数据平台开 ticket；因子覆盖率 < 90% 自动 reject |
| 计算资源超限 | Run 预算（CPU/内存/时长）硬上限，超限 kill 并标记 retryable，指数退避重试 ≤ 2 次 |
| 回测撮合异常（如全期不可成交） | 不视为系统错误，产出"不可成交报告"作为合法结果 |
| Agent/LLM 服务不可用 | LLM 环节排队等待 + 降级（路径 A 退化为纯模板枚举）；确定性环节不受影响 |
| 审批超时 | 按 10.2 超时策略自动处理，留痕 |
| 系统崩溃恢复 | Orchestrator 从持久化状态机恢复，幂等事件重放不产生重复 Run |

所有失败必须落到三类之一并显式标记：`retryable` / `permanent` / `needs_human`。禁止"静默吞掉"。

---

## 14. 安全与成本控制

### 14.1 安全

- **代码执行边界**：IR 是声明式 DSL，不是代码——天然杜绝 eval 注入。算子库代码走正常 code review。LLM 不执行任何它生成的东西。
- **LLM 输出不信任原则**：LLM 产出的所有数字不进入计算路径；其文本输出入库前做 schema 校验与内容 sanitize。
- **Prompt 注入防护**：论文 PDF 是不可信输入——解析时对文档文本做指令清洗（把 PDF 内容严格作为"数据"而非"指令"传给模型，使用 system prompt 隔离），PDF 中发现的疑似注入指令记录在审计日志。
- **权限**：数据只读账号；artifact 存储写一次不可改；审批操作需独立身份认证；API key 统一走 LLM Gateway，不出现在 Agent 环境变量之外的地方。
- **审计**：所有状态迁移、审批、门禁裁决、LLM 调用写入 append-only 审计日志。

### 14.2 成本控制

- **LLM 预算**：按 task/run 设 token 预算（默认：路径 A 每假设 200k tokens，路径 B 每篇论文 500k tokens），超限需 HITL 加额；prompt 缓存复用相同前缀；PDF 解析先启发式裁剪（只送公式/实验相关章节）。
- **算力预算**：因子评估前做"廉价预筛"（单 horizon、3 年样本、粗粒度），预筛不过不跑全量；因子值按 `hash(IR, snapshot)` 缓存，组合评估复用单因子结果。
- **报告**：每次 Run 输出成本卡片（LLM tokens + 计算时长），按月汇总，超预算自动降级（减少候选数上限）。

---

## 15. MVP → 生产路线图

| 阶段 | 范围 | 退出标准（DoD） |
|---|---|---|
| **M0 骨架（2–3 周）** | IR/DSL + 算子库（30 个）+ PIT 数据视图 + 向量化计算引擎 + IC/分层评估 + 单因子 HTML 报告；只有人工提交 IR 一条入口 | 20 个经典因子（反转/动量/换手等）复算出与内部参考一致的 IC；全流程可重放 |
| **M1 挖掘路径 A（3 周）** | HypothesisMiner + Critic + 模板枚举 + 门禁 Gatekeeper + HITL 审批 CLI + LLM Gateway | 一条自然语言假设进 → 报告出，全程 ≤ 1 个人工动作；LLM 候选静态校验通过率、IC 命中率有统计 |
| **M2 回测与策略（3–4 周）** | 自研撮合引擎（涨跌停/停牌/成本）+ 等权/IC 加权组合 + walk-forward + 防偏差清单落地 + 审计报告 v1 | 两个基线策略（沪深 300 内 top50 月度调仓）结果与三方回测对拍误差 < 可解释阈值 |
| **M3 论文路径 B（3 周）** | PaperReproducer + 证据链 + 适配 HITL + 双轨复现 | 3 篇经典因子论文完成端到端复现，证据链在报告中完整可查 |
| **M4 生产化（持续）** | 定期复检与 decay 状态机、容量/成本模型校准、Temporal 迁移、ML 组合器、Web 审批台、权限与多租户 | 月度复检自动运行 3 个周期；P95 评估延迟、月 LLM 成本达标 |

每一阶段结束跑"红队复盘"：故意提交带未来函数的因子、带注入指令的 PDF、阈值边缘因子，验证防线。

---

## 16. 验收指标

**工程正确性**
- 重放一致性：同一 Run 配置重跑，因子值与指标 bitwise 一致（浮点容差 1e-12）。
- 防泄漏有效性：红队注入的 10 个含未来函数因子 100% 被静态扫描或动态对拍拦截。
- 可追溯：随机抽 10 个报告数字，100% 可在 5 分钟内定位到 artifact + 代码版本 + 数据快照。

**研究质量**
- 路径 A：LLM 生成候选的静态校验通过率 ≥ 60%；每个假设至少 1 个因子进入 HITL 审阅的比率 ≥ 30%（太低说明生成质量差，太高说明门禁太松，需复盘）。
- 路径 B：公式抽取准确率（人工抽验 20 篇）≥ 90%；IR 翻译 exact 率 ≥ 60%。
- 端到端：从输入到报告的 P95 时长：路径 A ≤ 2h，路径 B ≤ 4h（含审批等待另计）。

**成本**
- 单因子全链路平均 LLM 成本 ≤ 预算卡片上限；预筛机制节省 ≥ 50% 全量评估算力。

**回测可信度**
- IS→OOS 绩效衰减有统计基线；OOS 预注册执行率 100%（无未注册 OOS 报告流出）。

---

## 17. 关键风险

1. **PIT 数据质量是地基**：若底层数据的公告日、历史成分、退市记录不可靠，所有防泄漏设计失效。缓解：M0 前做数据审计专项，这是整个项目最大的外部依赖。
2. **LLM 生成因子的"伪多样性"**：LLM 倾向生成已知因子的变体，导致挖掘边际价值低、相关性高。缓解：相关性门禁 + Critic 专门审查新颖性 + 模板枚举保持基线产出。
3. **多重检验淹没信号**：批量挖掘必然产生大量"样本内显著"的伪因子。门禁阈值只是第一道闸；OOS 预注册与校正提示是底线，但组织层面要接受"大部分候选会死"的预期。
4. **论文复现的期望管理**：多数论文因子在 A 股、扣费后显著衰减甚至失效。双轨复现 + 报告三列对比设计就是为防止"复现失败"被误读或粉饰。
5. **成本模型校准失真**：滑点模型参数若按乐观历史校准，回测系统性偏乐观。缓解：最低滑点下限 + 参数保守默认 + 定期用实盘/仿真成交校准。
6. **审批瓶颈**：HITL 点若成为瓶颈，研究员会绕过系统。缓解：审批台体验投入 + 可配置（路径 A 假设确认可关）+ 审批 SLA 监控。
7. **状态机复杂度膨胀**：警惕把每个特例都加成状态。规则：新状态必须有对应的自动迁移条件，否则用标签而非状态。

---

## 18. 端到端示例：从论文 PDF 到回测报告

**输入**：研究员提交论文《短期反转在流动性冲击下的增强》（虚构示例）PDF + 约束："A 股全市场，日频，2020-01 起，排除 ST"。

**T+0 分钟**：PaperReproducer 解析 PDF → PaperFactSheet：因子 = 5 日反转 × 成交额冲击哑变量；原设定为美股月频、CRSP universe、报告多空 Sharpe 1.1。LLM 翻译为 IR 草案：

```yaml
expression: mul(neg(ts_mean(div(sub(close, delay(close,1)), delay(close,1)), 5)),
                ts_rank(div(amount, ts_mean(amount, 20)), 20))
```

TranslationLedger：6 项映射，5 项 exact，`liquidity_shock dummy → ts_rank(amount ratio)` 标记为 **approximated**（论文用哑变量，本地用连续 rank，理由附注）。

**T+5 分钟**：适配记录生成（美股→A 股、月频→日频、value-weight→等权）→ 推送 HITL。研究员在审批台确认（12 分钟后批准，动作入审计日志）。

**T+20 分钟**：IR 入库 v1 → 静态扫描通过（最大 lookback 25 日，无负 delay，字段均在白名单）→ 数据校验通过（覆盖率 99.2%）→ 预筛（3 年、1d horizon）：Rank IC 0.031 → 触发全量评估。

**T+50 分钟**：全量评估（2020-2024，1/5/10/20d horizon）：IC 0.034 / ICIR 0.42；10 分层单调性显著（Spearman 0.93）；月单边换手 180%；与库内已有反转因子相关 0.61（< 0.7）；容量估算 8 亿（ADV×10% 参与率）。Gatekeeper：全项达标 → **pass**，因子入池。

**T+60 分钟**：策略构建：该因子与库内 2 个低相关因子 ICIR 加权组合 → top100 等权、日度调仓、缓冲带 2%、行业偏离 ≤ 20% → strategy_def v1 → OOS 实验注册（IS: 2020-2022，OOS: 2023-2024，参数冻结）→ HITL 确认。

**T+2 小时**：walk-forward 回测完成（成本模型：佣金万 2.5 + 印花税 0.05% + 滑点 sqrt 模型 k=0.5，下限 5bp；涨跌停/停牌按规则顺延）。IS 年化超额 11.2%（扣费后）/ Sharpe 1.35；OOS 年化超额 6.8% / Sharpe 0.91；最大回撤 -14%；月均换手 165%，年均交易成本拖累 4.1%。

**T+2.5 小时**：审计报告生成，manifest 包含：PDF hash、PaperFactSheet（含公式页截图）、TranslationLedger、适配记录+审批人、IR v1、快照 id、两次 Run 的代码 sha、全部指标 JSON、IS/OOS 对照、多重检验校正提示（本批共 3 个候选）、成本卡片（LLM 312k tokens，计算 46 分钟）、AI 解读段落（明确标注）。研究员发布前最终确认。

---

## 19. 确定性 vs LLM 分工总结

| 环节 | 实现 | 理由 |
|---|---|---|
| IR 计算、指标、门禁裁决、撮合、PIT 视图、静态扫描、状态机 | **确定性** | 影响数值结论与放行决策，必须可重放可审计 |
| 假设结构化、IR 变体生成、PDF 解析、公式翻译、适配建议、报告叙事、红队审查 | **LLM** | 本质是语言理解/生成与创造性搜索 |
| LLM 产出到确定性系统的接口 | **JSON schema 约束 + 校验器** | 信任边界必须有机器执行的闸门 |

---

## 20. 五条关键判断（本方案优于常见做法之处）

1. **IR 是唯一事实源，而非"LLM 输出直通回测"。** 常见做法让 LLM 生成 Python 因子代码直接执行，换来的是注入风险、不可静态分析、不可重放。本方案用声明式 IR + 算子白名单，牺牲一点表达自由度，换来静态防泄漏扫描、内容寻址缓存和跨路径同构——这是批量挖掘场景下唯一可持续的选择。
2. **防泄漏做在数据访问层（PIT 视图），而非靠研究员自律或事后审查。** 多数团队的"未来函数检查"是 code review 或事后脚本；本方案让因子代码在物理上拿不到未来数据，再叠加 AST 静态推导与延迟一日对拍，形成三道独立防线——任何单一防线失效都不致命。
3. **OOS 预注册 + 重调计数，对抗的是"自己骗自己"。** 常见回测报告只区分 IS/OOS 却不记录 OOS 被"看了几次"；本方案把 OOS 区间冻结、重调产生更晚的新 OOS、且重调次数写入报告——把多重检验从道德约束变成机制约束。
4. **论文复现用三级证据链 + 双轨对照，而不是"复现一个数"。** 把翻译中的近似（approximated）显式化、把"原设定复现"与"本地设定"并列，使"复现失败"可以被归因到翻译误差、市场差异还是原结论脆弱——这比给一个无法解释的收益差数字有信息量得多。
5. **门禁的中间地带一律给人，而不是调阈值迁就通过率。** 常见系统要么全自动放水要么全自动卡死；本方案承认阈值的边界本质上是模糊地带，把模糊地带的裁决权明确交给 HITL 并限时留痕——自动化负责效率，人负责边界，审计负责事后问责，三者各归其位。
