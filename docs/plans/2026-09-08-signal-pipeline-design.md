# Signal Pipeline 设计：策略生成信号化 + 管道统一

> 日期：2026-09-08　状态：已确认待实施

## 1. 背景与问题

策略生成路径（`strategy_generation/backtest.py::load_strategy`）让 LLM 直接生成完整的
NautilusTrader `Strategy` 子类。agent 需要自己写 bar 订阅、指标实例化/注册/预热、下单、
仓位跟踪、止损状态等全部「管道」代码。实测发现三类典型 bug：

1. **指标预热死锁**：手动喂值的指标其 `update_raw` 被挡在读取 `.initialized` 的门禁之后。
2. **幻觉指标 API**：`DirectionalMovement` 没有 ADX，`.value` 恒为 0，被当成 ADX 用。
3. **自相矛盾的进场条件**：要求金叉（dif≈dea，gap≈0）同时要求 `|gap| >= 0.2*ATR`。

三者都不是交易想法的问题，而是「agent 拥有了不该拥有的管道代码」导致。此外，因子回测
（`backtest/service.py`）与策略生成用了**两套不同的管道**，前者已经信号化（`TargetPositionStrategy`），
后者没有。

## 2. 目标

- 把「策略生成」从「写 Strategy 子类」改为「只写信号」：agent 产出声明式指标清单 + 一个纯函数 `compute_signal(ctx) -> Signal`。
- 管道侧（订阅、指标构建/喂值、下单、仓位、保护单、对账）全部收归平台，**一套共享执行器**同时服务回测 / paper / 实盘，并统一因子回测与策略生成两条线。
- 时间周期由**用户配置**驱动，代码与颗粒度解耦。

## 3. 核心决策

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 信号表达力 | 目标仓位 + 可选止损/止盈保护单（B） |
| 2 | 指标归属 | 声明式：agent 只列指标，平台构建/喂值（A） |
| 3 | 向后兼容 | 一刀切：移除 legacy 完整 Strategy 路径，旧 FROZEN 草稿/paper 产物不再可运行，需重新生成 |
| 4 | 管道统一 | 因子回测也并进共享执行器（A） |
| 5 | 时间周期 | 用户配置（exec / trend 两个角色），代码内不出现具体颗粒度 |
| 6 | 安全/门禁 | 只保留「契约校验 + 注入式命名空间隔离」，删除一切 bug 模式静态检测 |

## 4. 信号契约

### 4.1 产出形态：一个受限 Python 文件

```python
INDICATORS = [
    {"key": "macd", "fast": 10, "slow": 20},
    {"key": "atr",  "period": 14},
    {"key": "adx",  "period": 14},
]

def compute_signal(ctx) -> Signal:
    if ctx.exec.adx.adx < 18:
        return Signal(target_qty=0)
    ...
    return Signal(target_qty=1, stop_price=ctx.bar.close - 2 * ctx.exec.atr.value)
```

- 只含两个必需顶层名：`INDICATORS`（数据）与 `compute_signal`（函数）。
- 指标声明**不含 timeframe**：算子对颗粒度无感知，颗粒度来自用户配置。

### 4.2 指标算子库（v1，平台实现）

| type | 暴露字段 | 说明 |
|---|---|---|
| `macd` | `dif`, `dea` | MACD 线与信号线 |
| `ema` / `sma` | `value` | 均线 |
| `atr` | `value` | 真实波幅 |
| `adx` | `adx`, `di_plus`, `di_minus` | 平台自实现（NT `DirectionalMovement` 无 ADX） |
| `bollinger` | `upper`, `mid`, `lower` | 布林带 |
| `rsi` | `value` | RSI |

### 4.3 上下文 ctx 与 Signal

```python
ctx.bar               # 当前执行周期 bar (open/high/low/close/volume/ts)
ctx.trend_bar         # 趋势周期最新 bar；未配置趋势周期时为 None
ctx.exec.<key>.<f>    # 执行周期上算子 <key> 的当前值
ctx.trend.<key>.<f>   # 趋势周期上算子的当前值（多周期才有）
ctx.prev.exec.<key>.<f> / ctx.prev.trend.<key>.<f>   # 上一根 bar 的算子值（金叉/死叉判断）
ctx.position          # 当前净仓位（手）
ctx.entry_price       # 建仓均价；空仓为 None
ctx.bars_since_entry  # 持仓 bar 数
ctx.stop_price        # 当前挂着的止损价；无则为 None
```

```python
Signal(target_qty: int, stop_price: float | None = None, take_profit: float | None = None)
```

移动止损 = 每根 bar 用 `max(ctx.stop_price, ...)` 重算返回，状态由平台保存，函数保持纯。

### 4.4 时间周期模型

- 用户配置 `exec_timeframe`（必填）与 `trend_timeframe`（可选），沿用现有 `backtest_plan`。
- 平台对每个已声明算子，在 exec / trend 两个周期上各算一套。
- 改周期 = 改配置，代码零改动。单周期策略 `ctx.trend` 为 None。

## 5. 共享执行器

增强 `TargetPositionStrategy`（或新建 `SignalStrategy`），平台实现全部管道：

- 订阅 exec + trend bar type；按声明构建/喂值算子（按周期各一套）
- 每根 exec bar 调 `compute_signal(ctx)`
- 目标仓位 vs 当前仓位 → 市价调仓（`make_qty`）
- 保护单管理：止损/止盈挂单、改单、撤单、OCO；触发即平
- 状态跟踪：仓位、均价、持仓时长、当前止损价

回测 / paper / 实盘三处加载同一执行器；因子回测的 `TargetPositionStrategy` 迁移进来
（因子信号 = 只填 `target_qty` 的退化版，无保护单）。

## 6. 安全模型（极简）

1. **契约校验**（能否跑，而非防 bug）：
   - 文件必须定义 `INDICATORS` 与 `compute_signal`
   - 指标 type 必须在算子库内（否则报「未知算子」，属配置错误）
   - `compute_signal` 签名/返回类型符合契约
2. **执行隔离（几行）**：在注入式命名空间 exec——只注入 `math`、`Signal` 等必需名，
   不暴露 `__import__`/`open`/`os`/网络/环境变量。这是平台自我保护（LLM 代码不可作恶），
   不做任何「逻辑对不对」的静态审查。

明确**不做**：死锁模式检测、禁止 `DirectionalMovement` 等原生类、gap≥ATR 尺度检测——
纯信号模型下前两者结构上不存在，后者由 must-fire 可执行测试覆盖。

## 7. 迁移（一刀切）

- 移除 `load_strategy`（完整 Strategy 子类）在回测/paper/实盘中的调用。
- 旧 FROZEN 草稿与 paper 产物：保留为历史记录，不可再运行；需重新生成信号版。
- 因子回测迁移到共享执行器，回归验证 `backtest_hash` 不变。

## 8. 测试策略

- 算子库正确性（重点：adx 自实现 vs 标准算法）
- 执行器：调仓、止损触发、移动止损 ratchet、止盈、OCO、多周期
- 契约/隔离：未定义必需名、未知算子、危险调用被拒
- **must-fire 合成夹具**：喂构造好的 bar 序列使进场条件无歧义成立，断言至少 1 笔成交（抓「永远不成交」类逻辑 bug）
- 端到端：本次 48 笔案例回归；因子回测迁移回归

## 9. 分期

- **阶段 1**：算子库 + 信号契约 + 共享执行器 + 极简安全，接通策略生成线（回测 + paper）
- **阶段 2**：因子回测迁移 + 回归
- **阶段 3**：agent prompt 改为产出 SignalSpec + 生成管线对接（含 code test 门禁改为「预热完成 + trade_count>0 + must-fire」）
