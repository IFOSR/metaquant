# Signal Pipeline 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把策略生成从「写 NautilusTrader Strategy 子类」改为「只写信号」，并用一套共享执行器统一策略回测、因子回测、paper、实盘。

**Architecture:** 新增 `quant_platform/signal` 包：算子库（时间周期无关）+ 信号契约（声明式指标 + 纯函数 `compute_signal`）+ 共享 `SignalStrategy`（NT 策略，管全部管道）+ 极简注入式隔离。策略生成与因子回测两条线都改走它。

**Tech Stack:** Python 3.12, NautilusTrader 1.231.0, pytest, SQLAlchemy, FastAPI。

**参考设计：** `docs/plans/2026-09-08-signal-pipeline-design.md`

---

## 阶段 0：前置说明

- 每个 Task 遵循 TDD：先写失败测试 → 跑红 → 最小实现 → 跑绿 → commit。
- 测试运行命令（Docker，镜像内已装 pytest）：
  `docker compose run --rm --no-deps api pytest tests/<path> -q`
- 类型检查：`docker compose run --rm --no-deps api mypy src/quant_platform/signal`
- 现有可复用件：`markets/nt/`（`to_nautilus_bars`、`build_futures_engine`、`build_equity_engine`、`run_engine`、`futures_contract`、`equity_instrument`、`backtest_hash`）、`strategy_generation/backtest.py` 里的 `_extract_strategy_trades`/`_extract_positions`/`_equity_curve_recorder`/`_bar_type_suffix`/`bar_spec_for`/`aggregate_bars`。

---

## 阶段 1：核心信号包

### Task 1: 算子库骨架 —— `Operator` 基类与 `sma`/`ema`

**Files:**
- Create: `src/quant_platform/signal/__init__.py`
- Create: `src/quant_platform/signal/operators.py`
- Test: `tests/signal/test_operators.py`

**Step 1: 写失败测试**

```python
# tests/signal/test_operators.py
from quant_platform.signal.operators import build_operator, SmaOperator, EmaOperator

def test_sma_values():
    op = build_operator({"type": "sma", "period": 3})
    for close in (1.0, 2.0, 3.0, 4.0):
        op.update(close)
    assert op.value == (2.0 + 3.0 + 4.0) / 3  # 3.0
    assert op.initialized is True

def test_ema_values():
    op = build_operator({"type": "ema", "period": 3})
    for close in (1.0, 2.0, 3.0):
        op.update(close)
    # seed = 前 3 根均值 = 2.0；第 4 根 k=2/(3+1)=0.5
    op.update(4.0)
    assert abs(op.value - (2.0 + 0.5 * (4.0 - 2.0))) < 1e-9

def test_unknown_operator_raises():
    import pytest
    with pytest.raises(ValueError):
        build_operator({"type": "nope", "period": 3})
```

**Step 2: 跑测试确认失败**（`build_operator` 不存在）

**Step 3: 最小实现**

```python
# operators.py
class Operator:
    """算子基类：update(close/bar) 推进，value 暴露当前值，initialized 表示预热完成。"""
    def __init__(self, period: int):
        self.period = period
        self.initialized = False
    def update(self, value: float) -> None:
        raise NotImplementedError

class SmaOperator(Operator):
    def __init__(self, period: int):
        super().__init__(period)
        self._buf: list[float] = []
        self.value = 0.0
    def update(self, value: float) -> None:
        self._buf.append(value)
        if len(self._buf) > self.period:
            self._buf.pop(0)
        self.value = sum(self._buf) / len(self._buf)
        self.initialized = len(self._buf) >= self.period

class EmaOperator(Operator):
    def __init__(self, period: int):
        super().__init__(period)
        self._n = 0
        self._seed_sum = 0.0
        self.value = 0.0
    def update(self, value: float) -> None:
        self._n += 1
        if self._n < self.period:
            self._seed_sum += value
            return
        if self._n == self.period:
            self._seed_sum += value
            self.value = self._seed_sum / self.period
            self.initialized = True
            return
        k = 2.0 / (self.period + 1)
        self.value = self.value + k * (value - self.value)

OPERATORS = {"sma": SmaOperator, "ema": EmaOperator}

def build_operator(spec: dict) -> Operator:
    type_name = spec.get("type")
    if type_name not in OPERATORS:
        raise ValueError(f"unknown operator: {type_name}")
    cls = OPERATORS[type_name]
    return cls(period=spec["period"])
```

**Step 4: 跑测试确认通过**　**Step 5: commit**

```bash
git add src/quant_platform/signal/ tests/signal/
git commit -m "feat(signal): sma/ema operators with build_operator registry"
```

### Task 2: `macd` / `atr` 算子

**Files:** Modify `operators.py`、`test_operators.py`

**Step 1: 写失败测试**

```python
def test_macd_fields():
    op = build_operator({"type": "macd", "fast": 3, "slow": 5})
    for c in (1,2,3,4,5,6,7,8,9,10):
        op.update(c)
    assert op.initialized
    # dif = ema(fast) - ema(slow)，dea = ema 由平台以「指标间依赖」另行提供；
    # 本算子只暴露 dif（dea 由 SignalStrategy 用 ema 算子对 dif 序列计算）
    assert op.dif == op.fast_ema.value - op.slow_ema.value

def test_atr_values():
    op = build_operator({"type": "atr", "period": 3})
    bars = [(10,12,9),(11,13,10),(12,14,11)]
    for h,l,c in bars:
        op.update(high=h, low=l, close=c)
    assert op.initialized
    assert op.value > 0
```

**Step 3: 实现**：`MacdOperator` 内部持两个 `EmaOperator`；`AtrOperator` 用 Wilder 平滑 TR。
`build_operator` 处理 `macd` 用 `fast`/`slow`、`atr` 用 `period`。注意 `update` 签名需按算子类型扩展
（`macd`/`ema`/`sma`/`rsi` 只需 close，`atr`/`adx`/`bollinger` 需 high/low/close）。统一成
`update(bar_like)` 或 `update(high, low, close)` 均可，计划采用 `update(high=None, low=None, close=None)`。

**Step 4/5:** 跑绿 + commit（`feat(signal): macd/atr operators`）

### Task 3: `adx`（自实现，含 `adx`/`di_plus`/`di_minus`）—— 本次 bug② 的直接产物

**Files:** Modify `operators.py`、`test_operators.py`

**Step 1: 写失败测试**（用一段已知数据，断言 adx 是 Wilder 平滑的 DX，且非恒 0）

```python
def test_adx_not_zero_and_direction_matches():
    op = build_operator({"type": "adx", "period": 14})
    prev_close = None
    # 造一段单边上涨：+DM 应显著大于 -DM
    import random
    closes = []
    c = 100.0
    for i in range(60):
        high, low = c + 1.0, c - 0.2
        op.update(high=high, low=low, close=c)
        c += 0.5
        closes.append(c)
    assert op.initialized
    assert op.adx > 0          # 关键：不允许恒 0
    assert op.di_plus > op.di_minus
```

**Step 3: 实现**：`AdxOperator` 按 Wilder 法：TR/+DM/-DM 平滑 → +DI/-DI = 100*平滑DM/平滑TR →
DX = 100*|+DI−-DI|/(+DI+-DI) → adx = Wilder 平滑 DX。`update(high, low, close)`，需记 prev high/low/close。

**Step 4/5:** 跑绿 + commit（`feat(signal): self-implemented adx operator`）

### Task 4: `bollinger` / `rsi` 算子

同 Task 1/2 模式。`BollingerOperator` 暴露 `upper`/`mid`/`lower`（k 默认 2）；`RsiOperator` Wilder RSI。

### Task 5: 信号契约 —— `Signal` / `Context` / `load_signal_spec`

**Files:**
- Create: `src/quant_platform/signal/contract.py`
- Test: `tests/signal/test_contract.py`

**Step 1: 写失败测试**

```python
from quant_platform.signal.contract import load_signal_spec, Signal

GOOD = '''
INDICATORS = [{"key": "macd", "fast": 3, "slow": 5}]
def compute_signal(ctx):
    return Signal(target_qty=1)
'''

def test_load_valid_spec():
    spec = load_signal_spec(GOOD)
    assert [i["key"] for i in spec.indicators] == ["macd"]
    sig = spec.compute_signal(None)
    assert sig.target_qty == 1

def test_missing_compute_signal_rejected():
    import pytest
    with pytest.raises(ValueError):
        load_signal_spec("INDICATORS = []")

def test_dangerous_call_rejected():
    import pytest
    with pytest.raises(ValueError):
        load_signal_spec('INDICATORS=[]\ndef compute_signal(ctx):\n    open("/etc/passwd")\n    return Signal(target_qty=0)')
```

**Step 3: 实现**：`load_signal_spec(code)`：
1. AST 扫描禁止 `open`/`__import__`/`eval`/`exec`/`os`/`subprocess`/`socket` 等（沿用 `security.py` 的黑名单思路，但不需要 import allowlist——信号文件**不允许 import**）。
2. 在注入式命名空间 `{"math": math, "Signal": Signal}` 中 `exec`（`__builtins__` 置为安全子集：不含 `open`/`__import__`/`eval`/`exec`）。
3. 校验存在 `INDICATORS`（list of dict）与 `compute_signal`（callable）。
4. 返回 `SignalSpec(indicators, compute_signal)`。

```python
@dataclass(frozen=True)
class Signal:
    target_qty: int = 0
    stop_price: float | None = None
    take_profit: float | None = None

@dataclass
class SignalSpec:
    indicators: list[dict]
    compute_signal: Callable[[object], Signal]
```

### Task 6: 共享执行器 `SignalStrategy`

**Files:**
- Create: `src/quant_platform/signal/strategy.py`
- Test: `tests/signal/test_strategy.py`

**Step 1: 写失败测试**（用 `load_signal_spec` + 真实 NT 引擎跑一段 bar，断言产出成交与保护单）
参照 `tests/strategy_generation/test_backtest.py` 里现有的引擎装配测试写法。

```python
def test_signal_strategy_target_position_orders():
    # INDICATORS 空；compute_signal 永远 target_qty=1 → 首根 bar 应产生 1 手买单
    ...
    assert len(engine.trader.generate_order_fills_report()) >= 1
```

**Step 3: 实现** `SignalStrategy(Strategy)`：

```python
class SignalStrategy(Strategy):
    def __init__(self, config, *, instrument_id, exec_bar_type_str,
                 trend_bar_type_str=None, spec: SignalSpec):
        ...
        self._operators: dict[str, dict[str, Operator]] = {"exec": {}, "trend": {}}
        for item in spec.indicators:
            self._operators["exec"][item["key"]] = build_operator(item)
            if trend_bar_type_str:
                self._operators["trend"][item["key"]] = build_operator(item)
    def on_start(self):
        self.subscribe_bars(self._exec_bar_type)
        if self._trend_bar_type: self.subscribe_bars(self._trend_bar_type)
    def on_bar(self, bar):
        # 1) 喂算子（exec / trend 各自按 bar 周期）
        # 2) 组装 ctx（bar/trend_bar/ind 当前值/prev/position/entry_price/bars_since_entry/stop_price）
        # 3) sig = spec.compute_signal(ctx)
        # 4) 目标仓位 vs 当前仓位 → 调仓市价单（复用 TargetPositionStrategy 语义）
        # 5) 保护单：stop_price/take_profit 变化 → 撤旧挂新；触发 → 平仓
```

关键点：`prev` 值 = 上一次喂值前的快照（在 feed 前保存）；`position` 用
`self.portfolio.net_position(instrument_id)`；`entry_price`/`bars_since_entry` 由策略内
状态跟踪（成交回报 + bar 计数）。

### Task 7: 共享 runner —— `run_signal_backtest`

**Files:**
- Create: `src/quant_platform/signal/runner.py`
- Test: `tests/signal/test_runner.py`

实现 `run_signal_backtest(...)`，组装引擎（复用 `build_futures_engine`/`build_equity_engine`）、
加 `SignalStrategy`、喂 exec+trend bars、`run_engine`、提取 trades/positions/equity（复用
`strategy_generation/backtest.py` 的 `_extract_strategy_trades`/`_extract_positions`/`_equity_curve_recorder`），
返回与 `StrategyBacktestResult.payload()` 兼容的 dict（`strategy-backtest/v1`）。

---

## 阶段 2：策略生成线接入

### Task 8: `StrategyBacktestService.run` 改用 signal runner

**Files:** Modify `src/quant_platform/strategy_generation/service.py`

`run()` 里把 `run_strategy_backtest(...)` 换成 `run_signal_backtest(code=code, ...)`（code 现在
是信号文件文本）。保留数据加载/聚合/趋势预热逻辑不变。补测试：`tests/strategy_generation/test_service.py`
加一条「信号 spec 出成交」用例。

### Task 9: code test 门禁强化

**Files:** Modify `src/quant_platform/strategy_generation/backtest.py::code_test_strategy`

三件事：① 走 signal runner；② 断言算子全部 `initialized`；③ 断言 `trade_count > 0`（代表性数据）。
加 must-fire 合成夹具测试：喂构造的 bar 序列使进场条件无歧义成立，断言 ≥1 成交。

### Task 10: 移除 legacy `load_strategy` 路径（一刀切）

**Files:**
- Modify `src/quant_platform/strategy_generation/backtest.py`（删除/停用 `load_strategy` 的 Strategy 子类分支）
- Modify `src/quant_platform/paper/service.py`、`src/quant_platform/paper/node.py`（改用 `load_signal_spec` + `SignalStrategy`）
- Modify `src/quant_platform/strategy_generation/api.py`（code test / backtest / replay 端点沿用 signal 路径）

删除相关旧测试或改为断言「legacy Strategy 代码被拒」。

---

## 阶段 3：因子回测迁移

### Task 11: `run_factor_backtest` 走 `SignalStrategy`（target-only）

**Files:** Modify `src/quant_platform/backtest/service.py`

把 `TargetPositionStrategy(target_qty_fn=...)` 替换为 `SignalStrategy`（`compute_signal` 由
`target_qty_fn` 包一层：`return Signal(target_qty=target_qty_fn(bar))`）。因子结果 schema 不变。
**回归门槛：`backtest_hash` 必须与迁移前一致**（`tests/backtest/test_service.py` 现有 golden 用例）。

---

## 阶段 4：agent 产出信号 + 生成管线

### Task 12: agent prompt 与 `_static_check` 改为 SignalSpec

**Files:** Modify `src/quant_platform/strategy_generation/agent.py`、`schemas.py`

- prompt 要求产出 `INDICATORS` + `compute_signal(ctx) -> Signal`（不再要求 Strategy 子类）。
- `_static_check` 收缩为：信号引用的指标 key 必须已声明；禁止出现 `subscribe_bars`/`order_factory`/
  `submit_order`/`DirectionalMovement`/`MovingAverageConvergenceDivergence` 等管道/原生类名。

### Task 13: 端到端回归

新增 `tests/signal/test_end_to_end.py`：用本次 48 笔案例的等价信号（双周期 MACD + ADX + 止损）
重写为 SignalSpec，断言 `trade_count > 0` 且能 freeze → 开 paper 账户 → paper 节点启动。

---

## 完成定义

- [ ] 策略生成不再产生任何 `Strategy` 子类，只产信号文件
- [ ] 因子回测与策略回测共用 `SignalStrategy`，因子 `backtest_hash` 回归不变
- [ ] 回测 / paper / 实盘三处加载同一执行器
- [ ] code test 门禁含「算子预热完成 + trade_count>0 + must-fire」
- [ ] 极简隔离：信号文件无法 I/O / 网络 / 读环境变量
- [ ] 旧 FROZEN 草稿/paper 产物不可运行（历史保留），文档已注明
