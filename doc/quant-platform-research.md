# 量化交易平台调研与选型报告

**调研日期：** 2026-08-10  
**目标：** 为“因子挖掘 → 因子检验 → 策略构建 → 策略回测 → 模拟盘 → 实盘交易”的量化交易 Pipeline 选择平台或组合架构。

## 1. 执行摘要

四个平台并不是同一类型的产品：

- **Vibe Trading**：偏量化研究工作台和研究 Agent，适合因子探索、A 股数据分析和探索性回测。
- **TradingAgents**：偏多 Agent 市场研究框架，适合生成研究假设、观点辩论和风险分析，不是量化回测或交易执行内核。
- **QuantDinger**：偏自托管的一体化 AI 量化平台，适合快速打通 Agent、策略、回测、模拟和交易控制闭环。
- **NautilusTrader**：偏确定性、事件驱动的交易基础设施，适合可信回测、模拟交易、订单管理和实盘执行，不负责因子挖掘和 Agent 编排。

**推荐组合：**

```text
Vibe Trading + TradingAgents
          |
          v
自研 Factor IR / PIT Data Gateway / Factor Validator
          |
          v
版本化 StrategyPackage
          |
          v
NautilusTrader Backtest / Paper / Live
```

QuantDinger 可以作为快速 MVP 的一体化控制面，或作为可选的 broker/execution 接入层，但不建议让其成为唯一的研究事实源。

四个平台都可能提供数据加载器、市场数据接口或 broker connector，但本方案不把这些接口直接当作正式数据事实源。正式研究数据和交易规则由外部授权/官方来源经自研 `Data Gateway`、PIT 快照和 `TradingRuleVersion` 统一管理；平台数据接口最多作为探索性数据源或 Adapter 的输入。

## 2. 评分矩阵

评分范围为 0-10，分数是基于官方站点、官方仓库、公开文档和源码结构的工程判断，不代表平台官方评级。

| 平台 | 研究严谨性 | Agent 能力 | 因子研究 | 回测可信度 | 工程扩展 | 部署成本 | 对本方案适配度 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Vibe Trading | 7 | 9 | 8 | 7 | 8 | 8 | 8 |
| TradingAgents | 4 | 9 | 3 | 3 | 7 | 7 | 5 |
| QuantDinger | 6 | 8 | 6 | 6 | 7 | 6 | 7 |
| NautilusTrader | 8 | 2 | 2 | 9 | 9 | 5 | 7 |

这里的“部署成本”分数越高表示越容易部署；NautilusTrader 的部署、学习和 A 股适配成本明显较高。

## 3. 平台分析

### 3.1 Vibe Trading

**定位**

Vibe Trading 更接近 AI 量化研究工作台：通过自然语言驱动数据探索、因子分析、策略生成、回测、验证和报告输出。

**已核实或可从公开代码观察到的能力**

- 支持多类市场数据加载器，包含 A 股相关数据源。
- 提供因子库、因子分析、回测、Walk-Forward、Bootstrap 和 Monte Carlo 等研究工具。
- 官方仓库包含 Alpha Zoo 和横截面 Alpha 示例。
- 具备研究运行记录、artifacts、warnings 和工具调用痕迹等研究过程信息。
- 存在 broker connector、paper trading 和受限 live trading 相关代码或接口。

**优点**

- 四个平台中最适合快速开始因子挖掘。
- 对 A 股数据研究更友好，适合验证数据源、因子表达式和研究工作流。
- Agent 能力强，适合从研究假设生成候选因子和实验草稿。
- 代码和研究模块相对容易作为 Python 组件拆出或包裹。

**缺点与风险**

- 仍然存在“LLM 生成可执行 Python 策略”的倾向，与本方案要求的“LLM 提案、确定性系统执行”不同。
- 公共数据源不能默认视为机构级 PIT 数据，必须独立验证字段的 available time、修订历史和历史成分。
- 研究回测能力不能直接等同于生产级订单撮合、组合账本和执行引擎。
- 项目迭代快，必须冻结依赖、数据版本、回测语义和接口版本。

**适配建议**

- 复用其研究 Agent、数据探索、因子分析和初步回测模块。
- 增加 `ResearchProposal -> Factor IR` 编译层，禁止 Agent 直接提交实盘代码。
- 用自研 PIT Data Gateway 替换或包裹其数据加载器。
- 只允许其输出候选因子和探索性结果，正式门禁由自研确定性内核执行。

### 3.2 TradingAgents

**定位**

TradingAgents 是多 Agent 市场分析和交易决策研究框架，核心角色包括基本面、情绪、技术分析师、研究经理、交易员和风险管理 Agent。

**优点**

- Agent 角色划分清晰，适合构建研究委员会。
- 适合生成研究假设、证据摘要、市场叙事、反方意见和风险清单。
- LangGraph 编排、checkpoint、结构化输出和多模型 provider 便于独立封装。
- 开源许可对二次开发相对友好。

**缺点与风险**

- 不是因子研究平台，没有完整的 Factor Registry、Factor IR、横截面 IC/IR、多重检验和容量门禁。
- 不是确定性回测引擎，结果受模型、提示词、数据 provider、温度和随机性影响。
- 没有成熟的订单、撮合、组合账本和实盘执行内核。
- 数据 provider 主要服务于市场观点分析，不能直接满足 A 股 PIT 财务数据和交易规则要求。

**适配建议**

- 只复用 Agent 角色、工具调用模式、研究辩论和风险分析机制。
- 将其输出限制为 `ResearchProposal`、`EvidenceBundle` 和 `RiskMemo`。
- 不复用其回测结果作为正式绩效，不让它直接生成或修改 `StrategyPackage`。

### 3.3 QuantDinger

**定位**

QuantDinger 是偏自托管的一体化 AI 量化交易平台，试图通过 MCP 为 Cursor、Claude Code、Codex 等 Agent 提供数据、因子、策略、回测、部署、broker 和交易观测能力。

**已核实或可从公开资料观察到的能力**

- 提供 MCP 接入和 Agent 调用入口。
- 具备 universe、factor、行情、指标、Strategy API、策略部署、回测和交易观察相关能力。
- 具备 broker credential 加密、订单确认、幂等键、notional cap、紧急停止和 paper order 等安全控制设计。
- 支持自托管和容器化部署方向。

**优点**

- 最容易快速构建“Agent → 策略 → 回测 → 模拟/交易”的产品闭环。
- MCP 接入降低了 Agent 集成成本。
- 平台级交易安全控制比纯研究框架更完整。
- 适合 MVP、内部研究平台或希望快速连接交易账户的团队。

**缺点与风险**

- Strategy API、数据模型、任务系统和交易控制形成较强的平台耦合。
- 公开资料不足以确认完整的 PIT、双时间数据、多重检验、lockbox、实验 lineage 和审计能力。
- 官网能力宣称必须以实际 API 行为和源码验证为准。
- 对 A 股 T+1、涨跌停、停牌、ST、历史成分和公司行为的覆盖不能默认视为完整。
- 若研究和执行都围绕其平台抽象构建，后续迁移会产生明显成本。

**适配建议**

- 可用于快速 MVP 的控制面、Agent 接口和 broker 操作。
- 在正式研究路径中保留自研 Factor Registry、PIT Gateway 和实验注册系统。
- 以标准化 `StrategyPackage` 或适配器对接，不让 QuantDinger API 成为内部唯一策略格式。
- 在采用前，必须做 PIT、防泄漏、回测对拍、订单安全和故障恢复验收。

### 3.4 NautilusTrader

**定位**

NautilusTrader 是确定性、事件驱动、多资产交易基础设施，目标是让相同的策略和事件语义覆盖回测、模拟和实盘。其核心运行时使用 Rust，Python 主要用于策略和控制层。

**优点**

- 回测、模拟和实盘共享事件模型、订单模型、组合账本和执行语义。
- 具备数据、订单、撮合、费用、账户、风险、组合、执行适配器和报告等基础设施。
- 事件驱动回测比简单向量化收益回测更接近真实交易过程。
- Rust 核心有利于性能、确定性和长期工程维护。
- 适合成为独立、版本化 `StrategyPackage` 的执行目标。

**缺点与风险**

- 不提供内置 Agent、论文解析、因子挖掘、因子验证或多 Agent 编排。
- 不提供完整的量化研究治理层，例如 Factor Registry、PIT 数据目录、多重检验和 lockbox。
- A 股适配不是开箱即用，需要补交易日历、价格限制、T+1、费用、CTP/broker adapter 和公司行为处理。
- 学习和二次开发成本较高。
- LGPL-3.0 的链接、派生和闭源部署方式需要进行法律评估。

**适配建议**

- 将 NautilusTrader 定位为回测、模拟盘、订单管理、组合账本和实盘执行内核。
- 不让其承担因子挖掘和研究 Agent 职责。
- 自研 `NautilusStrategyAdapter`，将 `StrategyPackage` 编译为 NautilusTrader 策略。
- 先完成单市场、日频、有限 broker 的适配，再扩展高频和多资产。

## 4. 与目标 Pipeline 的逐层适配

| Pipeline 层 | 首选平台/组件 | 说明 |
|---|---|---|
| 研究假设、自然语言入口 | Vibe Trading + TradingAgents | Vibe Trading 偏量化研究，TradingAgents 偏观点和反方分析 |
| 论文/文档理解 | 自研 Paper Agent + TradingAgents | 平台不能替代页级证据链和公式复现治理 |
| 因子候选生成 | Vibe Trading | 生成候选，不直接裁决 |
| Factor Registry / Factor IR | 自研 | 四个平台都不能直接替代 |
| PIT Data Gateway | 自研 | 必须管理 available time、修订、历史成分和数据快照 |
| 因子验证 | 自研确定性内核 + Vibe Trading 工具 | IC/IR、稳定性、容量、多重检验和 OOS 必须可复现 |
| 策略构建 | 自研 Strategy Compiler | 从 Factor IR 生成版本化 StrategyPackage |
| 探索性回测 | Vibe Trading 或 QuantDinger | 只用于快速筛选和开发反馈 |
| 正式回测 | NautilusTrader | 事件驱动、费用、撮合、组合和账本 |
| 模拟盘 | NautilusTrader 或 QuantDinger | 视 broker adapter、监控和安全验收结果决定 |
| 实盘交易 | NautilusTrader 优先 | 需要自行完成 A 股执行适配和运维 |
| 研究委员会/风险意见 | TradingAgents | 作为可插拔的语义分析层 |

## 5. 推荐系统边界

LLM/Agent 可以：

- 解析研究意图和论文。
- 生成候选因子和经济机制。
- 推荐数据字段映射。
- 生成反证条件、负对照和风险清单。
- 解释实验失败和生成研究报告。

LLM/Agent 不可以：

- 直接计算正式因子值。
- 修改统计门槛、样本切分或 lockbox。
- 选择性查看 OOS 结果并反复调参。
- 直接生成未经验证的实盘代码。
- 修改回测结果、账本或审计记录。

正式执行链路应为：

```text
ResearchProposal
  -> EvidenceBundle
  -> Factor IR
  -> Temporal/PIT Checks
  -> Deterministic Factor Validation
  -> Strategy Compiler
  -> Immutable StrategyPackage
  -> Backtest/Paper/Live
```

## 6. 实施路线

### 阶段一：研究内核

- 建立 Factor Registry 和 `factor-ir/v1`。
- 建立 PIT Data Gateway、字段 available-time 和 snapshot catalog。
- 实现数据质量、防泄漏、单因子验证、OOS、稳定性和容量门禁。
- 先支持 A 股日频横截面，不追求全市场和高频。

### 阶段二：研究 Agent

- 接入 Vibe Trading 的数据探索和因子研究能力。
- 接入 TradingAgents 的研究委员会、风险分析和反方辩论。
- 所有 Agent 输出必须编译为结构化 Proposal 和 Evidence Bundle。

### 阶段三：正式回测和执行

- 定义 `StrategyPackage`。
- 对接 NautilusTrader 的事件模型、订单模型、账本和 broker adapter。
- 实现 A 股交易日历、T+1、涨跌停、停牌、ST、费用和公司行为。
- 对正式回测与探索性回测做结果对拍。

### 阶段四：模拟和实盘

- 先 shadow，再 paper，再小资金 live。
- 加入人工审批、kill switch、notional cap、订单幂等、重启恢复、对账和审计。
- 研究平台与执行平台隔离，只通过版本化 `StrategyPackage` 交付。

## 7. 最终决策

**长期架构：** `Vibe Trading + TradingAgents + 自研研究内核 + NautilusTrader`。  
**快速 MVP：** `QuantDinger` 或 `Vibe Trading`，但从第一天保留自有 Factor IR、数据快照和实验记录。  
**单平台选择：**

- 以研究和因子挖掘为第一目标：选择 **Vibe Trading**。
- 以生产级回测和实盘为第一目标：选择 **NautilusTrader**。
- 以最快形成端到端产品闭环为第一目标：选择 **QuantDinger**。
- 不建议选择 **TradingAgents** 作为主平台。

## 8. 主要来源

- Vibe Trading：<https://vibetrading.wiki/home/>；<https://github.com/HKUDS/Vibe-Trading>
- TradingAgents：<https://github.com/tauricresearch/tradingagents>
- QuantDinger：<https://www.quantdinger.com/>；<https://github.com/brokermr810/QuantDinger>
- NautilusTrader：<https://nautilustrader.io/>；<https://github.com/nautechsystems/nautilus_trader>
- 当前综合 Pipeline 设计：[`integrated-quant-pipeline-design.md`](./integrated-quant-pipeline-design.md)

## 9. 证据边界

本报告保存的是截至 **2026-08-10** 的调研结论。平台版本、仓库代码、网站能力、数据源和交易适配器会持续变化；在正式采用前，必须固定 commit/version，并通过以下验收：

- PIT 数据和历史成分对拍。
- 回测防泄漏和 next-bar 执行对拍。
- 费用、滑点、涨跌停、停牌和 T+1 验收。
- 订单幂等、重启恢复、对账和 kill switch 验收。
- 从同一 `StrategyPackage` 运行回测、模拟和实盘的语义一致性验收。
