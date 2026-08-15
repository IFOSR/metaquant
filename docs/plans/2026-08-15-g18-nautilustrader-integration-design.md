# G18 NautilusTrader 集成方案：正式回测与执行层替换

**Date:** 2026-08-15（v2 修订）

**Status:** proposed（待确认后执行）

**v2 修订说明：** 按评审结论修订——(1) 明确不做新旧引擎对拍，执行层完全切换
到 NautilusTrader，自研引擎直接退役；(2) 修正 NautilusTrader 概念映射中的事实性
错误（连续合约、T+1、集合竞价、Rust 构建）；(3) 调整落地顺序并补充版本固定、
确定性 replay 和性能三条验收门禁。

## 1. 背景与目标

当前 `backtest/`（五时钟引擎、A 股引擎、期货引擎、账本）与 `execution/`（执行
adapter、shadow、safety）为自研简化实现。按既定架构，正式回测、paper/live、
订单、账本、执行与 broker adapter 全部由 NautilusTrader 承担，自研模块
（Factor IR、PIT Data Gateway、Validation Policy、Registry、lineage、审批、
Strategy Compiler）保持不变。

目标：

- 正式回测与执行统一在 NautilusTrader 之上，回测与 paper/live 共用同一份
  Strategy 代码，消除回测/实盘偏差。
- 适配 CN_A（股票，T+1/涨跌停/集合竞价/ST/印花税）与
  CN_COMMODITY_FUTURES（期货，夜盘/保证金/逐日盯市/平今平昨/换月/强平）。
- 保留研究内核的确定性、内容寻址、fail-closed 纪律。

**已确认的取舍：不做新旧引擎对拍。** 不自建第二套参照系，执行语义以
NautilusTrader 为唯一基准；正确性保障改为 golden set 验收 + 确定性 replay +
中国市场适配的专项单测（见 §8 验收门禁）。

## 2. 架构边界

### 2.1 替换（换成 NautilusTrader 本体）

- `backtest/engine.py`（A 股）、`backtest/futures_engine.py`（期货）、
  `backtest/ledger.py`、`backtest/clocks.py` → NautilusTrader `BacktestEngine`
  及内置订单/账本/撮合。
- `execution/contracts.py`（ExecutionAdapter）、`execution/runtime.py`（shadow）、
  `execution/safety.py` → NautilusTrader `ExecutionEngine`/`LiveExecutionEngine`
  + 自定义 `ExecutionClient` + RiskEngine 交易状态钩子。

### 2.2 保留（自研，不动）

`factor_ir/`、`data_gateway/`（PIT + 数据源门面）、`validation/`、
`strategy/`（StrategySpec/StrategyPackage）、`governance/`（审批/lockbox）、
`research/`（lineage）、`portfolio/`（组合/优化器）。

`markets/`（`cn_a.py`、`futures.py`、`cost.py` 等规则建模）保留，但角色从
"引擎的内置规则"变为"NautilusTrader 适配层的唯一事实源"——Instrument 定义、
费率、换月选择、可交易性判定全部从这里取数，不在适配层重复建模。

### 2.3 衔接点

```
PIT 数据 ──DataClient──▶ NautilusTrader DataEngine（Bar/Tick）
StrategySpec ──StrategyAdapter──▶ NautilusTrader Strategy（on_bar 决策）
信号 ──订单──▶ Order → MatchingEngine → Fill → Position → Portfolio
审批/lineage ──gate/审计，不进入执行热路径
```

## 3. NautilusTrader 概念映射（已核实）

| NautilusTrader 概念 | CN_A | CN_COMMODITY_FUTURES |
|---|---|---|
| Instrument | Equity（600000.SH） | FuturesContract（RB2610.SHF） |
| 换月 | 无 | DataEngine 连续合约拼接（见 §4.6，换月选择仍自研） |
| 交易时段 Session | 09:30-11:30 / 13:00-15:00 | 日盘 + 夜盘 21:00-23:00 |
| 撮合 | 自定义 FillModel（涨跌停） | 自定义 FillModel（涨跌停） |
| 费用 | 自定义 FeeModel（佣金+印花税+过户费） | 自定义 FeeModel（平今/平昨费率） |
| 持仓约束 | T+1（策略层锁定，见 §4.1） | 多空双边、MarginAccount 保证金 |
| 结算 | 无（现金账户） | 自定义逐日盯市结算（见 §4.4） |
| 强平 | 无 | 自定义保证金不足强平（见 §4.7） |

核实结论（2026-08-15，官方文档 + 源码）：

- NautilusTrader **没有**名为 `ContinuousFutures` 的类；连续合约是 DataEngine
  的拼接功能，见 §4.6。
- 涨跌停、T+1、中国式逐日盯市均**无内置支持**，全部需要自定义，官方扩展点
  各不相同，见 §4 逐条落点。
- PyPI `nautilus_trader` 提供预编译 wheel（cp312，Linux/macOS/Windows），
  安装不需要 Rust 工具链。

## 4. 中国市场适配点

1. **T+1**：无内置支持，且 Portfolio/Position 是核心 Rust 组件、无可插拔
   约束接口。落点二选一：策略层记录当日买入量并在生成卖单时扣除（简单、
   首选）；或自定义 `ExecutionAlgorithm` 在 `on_order()` 中 `deny_order()`。
   语义复用现有 `today_buys`。
2. **涨跌停**：无内置 price limit（instrument 的 `max_price`/`min_price` 是
   静态字段，RiskEngine 不校验价格边界）。落点：自定义 `FillModel`
   （`is_limit_filled()`，涨停不买、跌停不卖，可返回空合成盘口）。注意
   **高层 `BacktestVenueConfig.fill_model` 只接受内置模型**，自定义
   FillModel 必须走低层 `BacktestEngine.add_venue()` API——P3 的工作量
   评估据此上调。可交易性判定复用 `markets/cn_a.py` 的
   `TradabilityAssessment`。
3. **集合竞价**：采用简化方案——用现有 `match_call_auction` 产出开盘价，
   作为开盘 bar 喂入 NautilusTrader，订单在开盘价成交。**明确标注：这是
   数据预处理级简化，丢失竞价时段内的订单簿撮合语义**；日频 MVP 可接受，
   分钟频或竞价策略上线前必须重评审。
4. **保证金 + 逐日盯市**：保证金用内置 `MarginAccount`（`margin_init`/
   `margin_maint` 来自 `markets/futures.py`），可选自定义 `MarginModel`。
   **中国式逐日盯市（按结算价每日现金划转）无内置**——内置的只有到期
   最终结算（`settlement_prices` + `InstrumentClose`）和永续资金费结算。
   需要自研结算组件：每日结算价到达时计算盯市盈亏并划转账户现金（语义
   复用 `futures_engine.py` 的盯市结转）。这是 P3 中与撮合并列的最大
   工作项。
5. **平今/平昨费率**：自定义 FeeModel，按持仓开平仓时间分桶，复用
   `markets/futures.py` 的 `CloseOffset` 语义。
6. **换月**：NautilusTrader 只提供连续合约**拼接**——`RequestBars`/
   `SubscribeBars` 的 `params` 传 `continuous_future_transitions`（显式
   转换表：transition 时间、前后合约、前后价格）+ 调整模式
   （`ContinuousFutureAdjustmentType`：BACKWARD/FORWARD × SPREAD/RATIO）。
   官方明确"引擎不发现换月点、不选合约、不推断换月价差，这些是调用方
   的责任"。因此 `markets/futures.py` 的持仓量确认式主力选择逻辑保留，
   职责是生成转换表喂给 DataEngine。**版本注意**：该功能较新，P0 必须
   先确认锁定的 PyPI 版本已包含，否则连续合约拼接降级为适配层自行合成
   bar 序列。
7. **强平**：无内置。自研保证金不足强平逻辑（盯市后权益 < 维持保证金时
   生成强制平仓单），复用 `forced_liquidation` 语义。
8. **ST/停牌**：数据层过滤（`data_gateway` 已有 tradability 阻断），不进入
   NautilusTrader 数据流。

## 5. 分阶段落地计划

### P0 — 依赖 + 版本固定 + 标的定义

- `pyproject.toml` 加 `nautilus_trader` 并 **pin 精确版本**（`==x.y.z`），
  遵守技术设计对 adapter 的强制要求（固定上游版本、依赖锁、镜像 digest）。
  PyPI 有预编译 wheel，**无需 Rust 工具链**；Dockerfile 直接 pip 安装。
- 确认锁定版本包含连续合约拼接功能（§4.6），结果记录到本方案。
- `markets/nt/instruments.py`：`equity_instrument()` / `futures_contract()`
  工厂，从 `markets/cn_a.py` / `markets/futures.py` 规则生成 Instrument。
- `markets/nt/sessions.py`：A 股时段 + 期货日盘/夜盘 Session。

### P1 — DataClient（PIT → NautilusTrader 数据）

- `markets/nt/data_client.py`：实现 DataClient，把 `data_gateway` 的 Bar +
  FrozenSnapshot 转成 NautilusTrader Bar/TradeTick，写入 ParquetDataCatalog。
- 数据源门面（resolver）作为 DataClient 上游，保持不变。

### P2 — BacktestEngine 接通（smoke）

- `markets/nt/backtest.py`：`run_nautilus_backtest()`，BacktestEngine +
  低层 `add_venue()` 装配，先用内置撮合跑通端到端 smoke（PIT 数据进、
  订单/成交/账本出），**不在这个阶段做正确性验收**——中国市场语义尚未
  适配，结果必然与预期有差异。

### P3 — 中国市场撮合适配（最大工作项）

- 自定义 FeeModel、FillModel（涨跌停）、T+1 锁定、逐日盯市结算组件、
  平今平昨分桶、换月转换表生成、强平（§4 逐条落地）。
- 每条适配配专项单测：涨跌停不成交、T+1 卖出被拒、盯市现金结转金额、
  平今费率差异、换月拼接价格、强平触发条件。

### P4 — ExecutionEngine + ExecutionClient

- `markets/nt/execution_client.py`：实现 ExecutionClient（paper + 预留 live）。
- kill switch / notional cap 移入 RiskEngine 交易状态钩子（trading state
  ACTIVE/HALTED/REDUCING）与自定义订单校验。

### P5 — Strategy Compiler → Strategy

- `markets/nt/strategy_adapter.py`：StrategySpec（因子权重 + 风险限制 + 调仓
  规则）编译成 NautilusTrader Strategy 子类（on_bar 执行信号 → 目标仓位 →
  订单）。回测与 paper/live 共用同一份 Strategy 代码。

### P6 — 验收门禁 + 删除旧实现

- 通过 §8 全部验收门禁后，删除 `backtest/engine.py`、`futures_engine.py`、
  `ledger.py`、`clocks.py`、`execution/runtime.py` 等自研等价物。
- `markets/` 规则建模（cn_a.py、futures.py、cost.py）保留为适配层数据源。

## 6. 数据流全景（最终态）

```
数据源门面(AKShare→iFinD兜底) → Bar → PIT快照(FORMAL) → DataClient → ParquetDataCatalog
                                                                      ↓
Factor IR → 因子值 → Strategy Compiler → StrategySpec → StrategyAdapter → Strategy.on_bar
                                                                      ↓
                NautilusTrader 订单 → 撮合(自定义FillModel涨跌停) → 成交
                                                                      ↓
        账本/持仓/保证金/盯市(自研结算组件) → Portfolio/AccountState → 报告/lineage → 审批
```

## 7. 决策点

1. **回测与执行共用 Strategy 代码**：按「是」设计（P5），这是 NautilusTrader
   的核心价值（回测/实盘零偏差）。
2. **不做新旧引擎对拍**：已确认。执行语义以 NautilusTrader 为唯一基准，
   不自建第二套参照系；正确性保障依赖 §8 的 golden set、确定性 replay
   和 P3 专项单测。原自研引擎在 P6 直接删除。
3. **live broker**：paper 阶段先实现 ExecutionClient 的 paper 模拟；live 需接
   真实券商/期货柜台（CTP 等），依赖柜台 SDK/账号，届时再接入。
4. **集合竞价**：采用开盘价 bar 简化（§4.3），分钟频或竞价策略上线前重评审。

## 8. 验收门禁（P6 删除旧实现前必须全部通过）

1. **Golden set**：`docs/golden/` 现有 A 股/期货 golden case（交易成本、
   涨跌停、T+1、换月等）在 NautilusTrader 链路上全部通过。
2. **确定性 replay**：相同 `run_fingerprint` 的两次回测产生相同的关键
   artifact hash（成交序列、账本、NAV 历史）。需验证 NautilusTrader 事件
   循环内的 ID/时间戳生成在固定输入下可复现；如默认不可复现，在适配层
   注入确定性种子后重验。
3. **性能**：3,000-6,000 只 A 股、10 年日频，单次策略回测 P95 小于 10
   分钟（对齐 PRD §7.3）；50-100 个期货主力合约同标准。事件驱动逐 bar
   推送在该规模下的实测数据必须记录在验收报告里。

## 9. 风险

- NautilusTrader 原生适配器主要覆盖加密/外汇，中国市场（T+1、涨跌停、
  逐日盯市、平今平昨）全部需要自定义，P3 是主要不确定性来源；其中
  逐日盯市结算组件基本等于自研一块结算引擎。
- 连续合约拼接功能较新，锁定的 PyPI 版本可能不包含，P0 需先行确认。
- 内容寻址/确定性契约与 NautilusTrader 的事件驱动模型需要对齐（验收
  门禁 2），避免破坏研究内核的可复现性。
- 不做对拍意味着 NautilusTrader 适配层的语义错误没有第二参照系可发现，
  缓解手段只有 golden set 覆盖率和 P3 专项单测的完备性；golden case
  未覆盖的市场行为（如盘中开板、部分成交）属于已知盲区。
