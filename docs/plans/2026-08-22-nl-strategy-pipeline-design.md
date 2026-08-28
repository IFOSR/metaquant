# 自然语言策略流水线：NL → NautilusTrader 策略代码 → 回测/仿真/实盘

日期：2026-08-22
状态：设计稿（v2，按评审简化）

## 1. 背景与问题

平台已有研究链路（研报/论文 → 因子 → 验证 → 晋升 → 组合回测），但缺少面向
普通用户的策略主链路：

```
自然语言对话 → 产出交易策略 → 在 NT 里回测 / 仿真 / 实盘
```

当前缺口：

1. **没有 NL 对话入口**：现有 agent 只做「研报/论文 → 因子」。
2. **没有规则型策略的生成路径**：`StrategySpec` 只表达「因子权重组合」，没有
   「自然语言 → 可执行策略」的生成器。
3. **没有策略直通回测**：`/v1/backtests` 只跑因子组合回测，缺「策略 → NT 回测」
   的直通链路。
4. **paper/live 只有订单桥接**：`NautilusOrderGateway` 到单笔订单级别，无完整
   paper 引擎；live 未接真实券商/期货柜台（G18 已写明"届时再接入"）。

## 2. 核心判断

**不发明中间层。** NautilusTrader 原生提供一整套策略因子（指标）和标准的策略
写法，直接基于它：

- 规则型、因子组合型、挖因子，落点都是**一份 NautilusTrader Python 策略代码**，
  回测只认这份代码。
- agent 用自然语言理解用户策略后，**直接生成 NT 策略代码**，用 NT 原生指标，
  按 NT 官方示例的写法。
- 不引入 DSL、算子白名单、默认模板等中间概念。

```
自然语言（多轮对话）
   ↓ agent 理解 → 直接生成 NautilusTrader Python 策略（官方骨架 + 原生指标）
   ↓ 同时生成人话「策略说明」供用户确认
   ↓ 用户确认 → 冻结（内容寻址）→ 回测 / 仿真 / 实盘
```

## 3. NT 原生支持的策略因子（词汇表）

已核实（容器内 `nautilus_trader==1.231.0`）：

| 类别 | 原生指标 |
|---|---|
| 均线 | SimpleMovingAverage、ExponentialMovingAverage、WeightedMovingAverage、WilderMovingAverage、HullMovingAverage、DoubleExponentialMovingAverage、AdaptiveMovingAverage、VariableIndexDynamicAverage |
| 动量/振荡 | MACD、RSI、RelativeVolatilityIndex、ChandeMomentumOscillator、CCI、RateOfChange、Stochastics（KDJ）、EfficiencyRatio、PsychologicalLine、Bias |
| 趋势 | AroonOscillator、DirectionalMovement（DMI/ADX）、IchimokuCloud、DonchianChannel、KeltnerChannel、LinearRegression、Swings、VerticalHorizontalFilter |
| 波动 | AverageTrueRange、BollingerBands、VolatilityRatio |
| 成交量 | OnBalanceVolume、KlingerVolumeOscillator、VolumeWeightedAveragePrice、Pressure、CandleSize/CandleBodySize/CandleDirection/CandleWickSize |

外加原始价量字段 `open/high/low/close/volume`。这是 NL 解析时的词汇表，全部
来自 NT 现成能力。

## 4. 策略代码形态

以 NT 官方示例 `nautilus_trader.examples.strategies.ema_cross.EMACross` 为骨架
（已读源码核实）：

```python
class EMACross(Strategy):
    def __init__(self, config):
        super().__init__(config)
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)

    def on_start(self):
        self.register_indicator_for_bars(self.config.bar_type, self.fast_ema)
        self.register_indicator_for_bars(self.config.bar_type, self.slow_ema)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar):
        if not self.indicators_initialized():     # 指标预热
            return
        if self.fast_ema.value >= self.slow_ema.value:
            if self.portfolio.is_flat(...):        self.buy()
            elif self.portfolio.is_net_short(...): self.close_all_positions(...); self.buy()
        else:
            if self.portfolio.is_flat(...):        self.sell()
            elif self.portfolio.is_net_long(...):  self.close_all_positions(...); self.sell()
```

要点：

1. **多空双边**：官方示例本身就是 long/short 双边（`is_flat/is_net_long/
   is_net_short` 三态 + 先平反向仓再开新仓），MVP 直接支持，无需额外设计。
2. **金叉/死叉**：`cross` 用"上一根值 vs 当前值"比较实现；官方例子的状态机
   写法（flat+above→买，net_long+below→卖）对入场/出场等价于交叉。
3. **指标预热**：`indicators_initialized()` 保证均线等指标算足历史再开仓，
   杜绝早期错误信号。
4. **agent 生成的策略 = 这个骨架 + 用户要的指标组合与条件**。

## 5. 目标架构

```
前端「策略对话」入口
   ↓ 多轮对话：理解需求、逐轮澄清
   ↓ agent 生成 NT 策略代码 + 人话「策略说明」
   ↓ 用户确认 → 冻结（内容寻址）
NautilusTrader Strategy（on_bar 决策，原生指标）
   ↓
数据（iFinD/AKShare → PIT → NT Bar）→ 回测 → 净值曲线 + 指标
   ↓（后续）仿真 / 实盘
```

## 6. 多轮会话

一轮 NL 直接出可用策略不现实，保留多轮但保持简单：

- 每轮：agent 理解本轮输入 → 更新对策略的理解 → 生成/更新「策略说明」→ 对
  缺失或不明确处用人话追问（"止损定多少？""标的哪只？"）。
- 用户全程看的是**人话说明**，不是代码；代码与说明同轮生成、并排展示。
- 用户确认"策略就是我要的"后，冻结策略代码 + 说明，生成内容寻址 hash。
- 轮数设上限（如 6 轮），超限提示人工介入。

LLM 后端复用 `research/factor_extract.py::default_runner`（DeepSeek/Zhipu 同
后端选择）。

## 7. 安全（复用现有，不新增概念）

生成的是 Python 代码，安全沿用 `factor_construction` 已建好的机制：

- 沙箱执行 + AST 白名单扫描 + 资源限制（`docker/sandbox`）。
- 代码只读数据、只提交订单，禁止网络/文件系统写。

不引入新的算子白名单/模板概念——那套由沙箱 + AST 扫描承接。

## 8. 回测直通 API

```
POST /v1/strategies                       创建策略（冻结的代码 + 说明）
POST /v1/strategies/{id}:backtest         直接回测 → 净值/指标
```

复用 `markets/nt/backtest.py`（`build_equity_engine/run_engine`）、
`markets/nt/data.py`（`to_nautilus_bar(s)`）、`backtest/service.py`（净值/指标）。
前端复用 `components/backtest-lab.tsx` 的结果展示，新增「策略对话」入口与
「策略说明」面板。

## 9. 复用点清单

| 能力 | 位置 |
|---|---|
| LLM 后端（DeepSeek/Zhipu） | `research/factor_extract.py::default_runner` |
| NT 原生指标库 | `nautilus_trader.indicators` |
| NT 官方策略骨架 | `nautilus_trader.examples.strategies.ema_cross` |
| NT 回测引擎 | `markets/nt/backtest.py` |
| NT 数据转换 | `markets/nt/data.py` |
| NT 策略骨架（本地） | `markets/nt/strategy.py::TargetPositionStrategy` |
| 回测指标/净值 | `backtest/service.py` |
| 沙箱 + AST 扫描 | `factor_construction`（runner/sandbox） |
| 前端回测结果展示 | `components/backtest-lab.tsx` |

## 10. 分阶段落地

| 阶段 | 内容 | 产物 |
|---|---|---|
| 1 | NL agent：多轮对话 → 生成 NT 策略代码 + 说明 | 对话入口 + 代码 |
| 2 | 代码沙箱试运行闭环（生成 → 试跑 → 报错修正） | 可跑策略 |
| 3 | 回测直通 API + 前端「对话 + 净值展示」 | 「对话 → 回测」闭环 |
| 4（后） | paper 引擎补全 | 仿真 |
| 5（后） | live 接真实柜台（外部依赖） | 实盘 |
| 6（后） | 通达信导出（后续再完善） | 导出 |

第一阶段只交付到阶段 3 的最小闭环。

## 11. 决策点

1. **策略代码 = 直接生成的 NautilusTrader Python 策略**（不引入 DSL/IR/白名单）。
2. **MVP 支持多空双边**，不做高频。
3. **无默认模板、无算子白名单**，一切以 NT 原生能力为准。
4. **安全复用现有沙箱 + AST 扫描**。

## 12. 风险与取舍

- **LLM 生成的代码可能跑不通/写错 API**：阶段 2 的试运行闭环解决——生成 →
  沙箱试跑 → 报错回给 agent 修正，直到能产出订单/净值。
- **代码与说明可能不一致**：两者同轮由 agent 生成并并排展示，用户确认的是
  说明；发现不一致时可要求 agent 重写说明或代码。MVP 接受此弱一致性，不做
  DSL 强绑定（已按评审放弃 DSL）。
- **多空双边在 A 股现货受融券限制**：策略代码本身支持负向目标仓位，能否做空
  由市场规则层（`markets/cn_a.py`）约束；期货天然双边。agent 生成时按市场
  提示用户。
- **内容寻址与事件驱动对齐**：沿用 G18 验收门禁（确定性 replay）保证回测可复现。
