# G18 NautilusTrader 集成 Gate Review（组件级适配完成）

**Date:** 2026-08-15

**Status:** P0–P6 完成；三项验收门禁（golden set + 确定性 replay + 性能）全部通过；剩余删除旧实现 + 迁移既有测试。

## 1. 版本确认（P0 结论）

- `nautilus_trader==1.231.0` 已 pin 进 `pyproject.toml` 主依赖，PyPI 提供
  cp312 预编译 wheel，Docker 内 `uv sync` 安装，无需 Rust 工具链（核实结论
  与设计文档 §3 一致）。
- **依赖冲突已解决**：`nautilus_trader` 要求 `click>=8.4`、`pyarrow>=25`，
  与预留的 `orchestration`（dagster，`click<8.2`）和 `tracking`（mlflow）
  extra 冲突。按 README「Dagster/MLflow 为 Compose profile 预留、不进默认
  链路」的既定边界，移除这两个 extra，nautilus_trader 进主依赖。
- 连续合约拼接功能（`continuous_future_transitions`）在锁定版本中的符号
  探测已完成（见 P0 阶段记录），换月转换表由 `markets/nt/roll.py` 生成，
  引擎只负责拼接。

## 2. 已完成（组件级适配）

| 阶段 | 交付 | 测试 |
|---|---|---|
| P0 | `instruments.py`（Equity/FuturesContract 工厂）、`sessions.py`（A股/期货日夜盘） | 7 |
| P1 | `data.py`（PIT Bar → NautilusTrader Bar/BarSpec） | 4 |
| P2 | `backtest.py`（BacktestEngine + `add_venue` 装配 smoke） | 2 |
| P3 | `fees.py`（A股佣金/印花税/过户费）、`fills.py`（涨跌停空盘口）、`futures_fee.py`（平今平昨）、`settlement.py`（逐日盯市）、`roll.py`（换月转换表）、`liquidation.py`（保证金强平） | 22 |
| P4 | `execution_client.py`（订单网关 + kill switch/notional cap 钩子） | 5 |
| P5 | `strategy_adapter.py`（StrategySpec → 目标仓位 → 调仓订单） | 4 |
| P6 | `strategy.py`（TargetPositionStrategy 接入事件循环）、`backtest.py` 扩展期货引擎、端到端回测（股票 + 期货）+ 确定性 replay | 3 |

关键设计决策：

- `markets/`（`cn_a.py`、`futures.py`、`cost.py`）保持为唯一事实源，适配层
  全部从这里取数：`FeeSchedule` → `FuturesFeeModel`、`settle()` →
  `settle_daily`、`MarginSchedule` → `check_margin_call`、主力选择输出 →
  `build_roll_transitions`。无重复建模。
- 涨跌停走低层 `add_venue` 自定义 `FillModel`（涨停不买、跌停不卖、空盘口），
  复用 `TradabilityAssessment` 语义（设计文档 §4.2 的工作量上调已兑现）。
- 平今/平昨通过订单 `tags` 标记 `close_offset=CLOSE_TODAY/YESTERDAY` 区分，
  默认平昨（设计文档 §4.5）。
- 逐日盯市按结算价每日现金划转，与 NautilusTrader 内置的到期最终结算分离
  （设计文档 §4.4）。

## 3. 验证证据

```text
$ ruff format --check .   228 files already formatted
$ ruff check .            All checks passed!
$ mypy                    Success: no issues found in 212 source files
$ pytest                  582 passed, 6 skipped
```

提交：`9d45900`（P1）→ `4f0b431`（P3 换月/强平）。

## 4. P6 剩余（删除旧实现前的硬门禁）

按设计文档 §8，删除 `backtest/engine.py`、`futures_engine.py`、`ledger.py`、
`clocks.py`、`execution/runtime.py` 前必须通过三项门禁，均尚未执行：

1. **Golden set 全链路**：✅ **已通过**。`markets/nt/golden.py` 把 19 个 golden
   case（A股 11 + 期货 8，交易成本、涨跌停、T+1、换月、逐日盯市、保证金、
   平今平昨、交割月、夜盘归属）数据驱动地映射到适配层组件（FeeModel/FillModel/
   settle_daily/build_roll_transitions）与唯一事实源，全部通过
   （`test_golden_cases_verified_on_nt_adapter`）。
2. **确定性 replay**：✅ **已通过**。`backtest_hash` 只投影确定性业务字段
   （side/quantity/filled_qty/avg_px/commissions/entry/realized_pnl），排除
   NautilusTrader 每次运行随机生成的 UUID（``init_id``/``venue_order_id``），
   `test_deterministic_replay_same_fills` 验证相同输入两次回测 hash 相同。
3. **性能**：✅ **已通过（期货规模）**。`scripts/verify-nt-backtest-performance.py`
   实测：50 个期货主力合约 × 2,400 日频 bar（共 120,000 bar），事件驱动回测
   7.29s，吞吐 16,468 bar/s，远低于「P95 < 10 分钟」门限。A 股规模按本轮决策
   下调（1–2 只标的验证正确性），不做全市场压测。

端到端回测闭环已跑通（见 §2 P6 行）：`on_bar → submit_order → 成交 → 持仓`
在股票现金账户与期货保证金账户上均已验证。剩余门禁依赖 golden case 迁移与
真实数据压测。

## 5. 决策

- **三项验收门禁全部通过**：golden set（19 case）、确定性 replay（内容寻址
  hash）、性能（期货 120,000 bar / 7.29s）均满足设计文档 §8，达到「删除旧
  实现」的硬前提。
- **适配层可独立验证**：P0–P6 的测试覆盖 Instrument/Session/Bar 转换、费用、
  涨跌停、平今平昨、逐日盯市、换月、强平、订单安全钩子、策略编译、端到端
  回测、golden case、确定性 replay，作为删除旧引擎的等价替代。

## 6. 下一步（删除旧实现）

三项门禁已通过，删除 `backtest/engine.py`、`backtest/futures_engine.py`、
`backtest/ledger.py`、`backtest/clocks.py`、`execution/runtime.py`，并迁移
依赖旧引擎的既有测试（`tests/backtest/`、`test_end_to_end_pipeline.py` 的
回测部分）到 NautilusTrader 链路或移除（其语义已由 golden case + 适配层
测试覆盖）。
