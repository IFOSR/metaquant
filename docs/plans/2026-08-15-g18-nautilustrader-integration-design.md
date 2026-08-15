# G18 NautilusTrader 集成方案：正式回测与执行层替换

**Date:** 2026-08-15

**Status:** proposed（待确认后执行）

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

## 2. 架构边界

### 2.1 替换（换成 NautilusTrader 本体）

- `backtest/engine.py`（A 股）、`backtest/futures_engine.py`（期货）、
  `backtest/ledger.py`、`backtest/clocks.py` → NautilusTrader `BacktestEngine`
  及内置订单/账本/撮合。
- `execution/contracts.py`（ExecutionAdapter）、`execution/runtime.py`（shadow）、
  `execution/safety.py` → NautilusTrader `ExecutionEngine`/`LiveExecutionEngine`
  + 自定义 `ExecutionClient`。

### 2.2 保留（自研，不动）

`factor_ir/`、`data_gateway/`（PIT + 数据源门面）、`validation/`、
`strategy/`（StrategySpec/StrategyPackage）、`governance/`（审批/lockbox）、
`research/`（lineage）、`portfolio/`（组合/优化器）。

### 2.3 衔接点

```
PIT 数据 ──DataClient──▶ NautilusTrader DataEngine（Bar/Tick）
StrategySpec ──StrategyAdapter──▶ NautilusTrader Strategy（on_bar 决策）
信号 ──订单──▶ Order → MatchingEngine → Fill → Position → Portfolio
审批/lineage ──gate/审计，不进入执行热路径
```

## 3. NautilusTrader 概念映射

| NautilusTrader 概念 | CN_A | CN_COMMODITY_FUTURES |
|---|---|---|
| Instrument | Equity（600000.SH） | FuturesContract（RB2610.SHF） |
| 换月 | 无 | ContinuousFutures（主力连续） |
| 交易时段 Session | 09:30-11:30 / 13:00-15:00 | 日盘 + 夜盘 21:00-23:00 |
| 撮合 | MatchingEngine（自定义涨跌停/集合竞价） | MatchingEngine（自定义涨跌停） |
| 费用 | FeeModel（佣金+印花税+过户费） | FeeModel（平今/平昨费率） |
| 持仓约束 | T+1（买入当日不可卖） | 多空双边、保证金 |
| 结算 | 无（现金账户） | 逐日盯市 settlement |
| 强平 | 无 | 保证金不足强平 |

## 4. 中国市场适配点

1. **T+1**：Equity 持仓买入当日不可卖，在 Strategy/Portfolio 层锁定当日买入
   数量（复用现有 `today_buys` 语义）。
2. **涨跌停**：自定义 FillModel/价格校验，涨停不买、跌停不卖（复用
   `markets/cn_a.py` 的 `TradabilityAssessment`）。
3. **集合竞价**：开盘价用现有 `match_call_auction`，喂入 NautilusTrader 作为
   开盘 bar。
4. **保证金 + 逐日盯市**：期货 AccountState 保证金逻辑 + 自定义 settlement
   事件（复用 `futures_engine.py` 的盯市结转）。
5. **平今/平昨费率**：自定义 FeeModel（复用 `markets/futures.py` 的
   `CloseOffset`）。
6. **换月**：NautilusTrader `ContinuousFutures`（替代手工 delivery/roll 逻辑）。
7. **强平**：自定义保证金不足强平逻辑（复用 `forced_liquidation` 语义）。
8. **ST/停牌**：数据层过滤（`data_gateway` 已有 tradability 阻断）。

## 5. 分阶段落地计划

### P0 — 依赖 + 标的定义

- `pyproject.toml` 加 `nautilus_trader`；Dockerfile 装 Rust 编译产物。
- `markets/nt/instruments.py`：`equity_instrument()` / `futures_contract()`
  工厂，从 `markets/cn_a.py` / `markets/futures.py` 规则生成 Instrument。
- `markets/nt/sessions.py`：A 股时段 + 期货日盘/夜盘 Session。

### P1 — DataClient（PIT → NautilusTrader 数据）

- `markets/nt/data_client.py`：实现 DataClient，把 `data_gateway` 的 Bar +
  FrozenSnapshot 转成 NautilusTrader Bar/TradeTick，写入 ParquetDataCatalog。
- 数据源门面（resolver）作为 DataClient 上游，保持不变。

### P2 — BacktestEngine 集成

- `markets/nt/backtest.py`：`run_nautilus_backtest()`，BacktestEngine +
  TradingNodeConfig，替换 run_a_share_backtest / run_futures_backtest 调用方。
- 与旧引擎对拍：同样目标仓位产出等价订单/成交/账本。

### P3 — 中国市场撮合适配

- 自定义 FeeModel、FillModel、涨跌停、集合竞价、保证金、盯市、平今平昨、
  换月、强平（§4 逐条落地）。最大工作量，核心是「适配目标市场」。

### P4 — ExecutionEngine + ExecutionClient

- `markets/nt/execution_client.py`：实现 ExecutionClient（paper + 预留 live）。
- kill switch / notional cap 移入 NautilusTrader 订单校验钩子（RiskEngine 或
  自定义 OrderFilter）。

### P5 — Strategy Compiler → Strategy

- `markets/nt/strategy_adapter.py`：StrategySpec（因子权重 + 风险限制 + 调仓
  规则）编译成 NautilusTrader Strategy 子类（on_bar 执行信号 → 目标仓位 →
  订单）。回测与 paper/live 共用同一份 Strategy 代码。

### P6 — 删除旧实现 + 全链路验证

- 删 backtest/engine.py、futures_engine.py、execution/runtime.py 等自研等价物。
- 保留 markets/ 规则建模（cn_a.py、futures.py、cost.py），成为适配层数据源。
- 端到端验证：PIT → 因子 → StrategySpec → NautilusTrader 回测 → 账本 →
  lineage/审批。

## 6. 数据流全景（最终态）

```
数据源门面(AKShare→iFinD兜底) → Bar → PIT快照(FORMAL) → DataClient → ParquetDataCatalog
                                                                      ↓
Factor IR → 因子值 → Strategy Compiler → StrategySpec → StrategyAdapter → Strategy.on_bar
                                                                      ↓
                          NautilusTrader 订单 → 撮合(涨跌停/集合竞价) → 成交
                                                                      ↓
              账本/持仓/保证金/盯市 → Portfolio/AccountState → 报告/lineage → 审批
```

## 7. 决策点

1. **回测与执行共用 Strategy 代码**：按「是」设计（P5），这是 NautilusTrader
   的核心价值（回测/实盘零偏差）。
2. **live broker**：paper 阶段先实现 ExecutionClient 的 paper 模拟；live 需接
   真实券商/期货柜台（CTP 等），依赖柜台 SDK/账号，届时再接入。

## 8. 风险

- NautilusTrader 原生适配器主要覆盖加密/外汇，中国市场（T+1、涨跌停、集合
  竞价、平今平昨）全部需要自定义，P3 是主要不确定性来源。
- Rust 核心的编译产物在 Docker 内构建耗时，需预构建基础镜像。
- 内容寻址/确定性契约与 NautilusTrader 的事件驱动模型需要对齐，避免破坏研究
  内核的可复现性。
