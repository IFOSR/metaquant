# G18 NautilusTrader 集成 Gate Review（组件级适配完成）

**Date:** 2026-08-15

**Status:** P0–P5 完成；P6（验收门禁 + 删除旧实现）待端到端回测打通后执行。

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

1. **Golden set 全链路**：`docs/golden/` 的 A股/期货 golden case（交易成本、
   涨跌停、T+1、换月）在 NautilusTrader 端到端回测链路上全部通过。
   当前 golden case 仍在自研引擎链路上验证，尚未迁移到 NautilusTrader 链路。
2. **确定性 replay**：相同 `run_fingerprint` 两次回测产生相同 artifact hash。
   需在适配层注入确定性种子后验证 NautilusTrader 事件循环的可复现性。
3. **性能**：3,000–6,000 只 A 股、10 年日频，单次策略回测 P95 < 10 分钟；
   50–100 个期货主力合约同标准。需真实数据 + 完整链路压测并记录实测值。

三项门禁都依赖**端到端回测跑通**（DataClient 写 ParquetDataCatalog + 完整
Strategy 注册 + 事件循环回测），这是当前组件级适配的下一步集成工作，也是
「删除旧实现」的安全前提。

## 5. 决策

- **不删除旧实现**：三项验收门禁未通过前，旧引擎作为既有测试基线保留。
  设计文档明确「通过 §8 全部验收门禁后」才删除，当前不满足。
- **组件级适配已可独立验证**：P0–P5 的 44 个新测试（582 总数中）已覆盖
  Instrument/Session/Bar 转换、费用、涨跌停、平今平昨、逐日盯市、换月、
  强平、订单安全钩子、策略编译，作为端到端集成的可靠基础。

## 6. 下一步（P6 集成）

1. DataClient 完整实现（`data.py` 扩展为写入 ParquetDataCatalog 的
   `PITDataClient`）。
2. Strategy 注册（`strategy_adapter.py` 编译出 NautilusTrader Strategy 子类，
   接入 `BacktestEngine.add_strategy`）。
3. 端到端回测跑通（PIT → DataEngine → Strategy → 订单 → 撮合 → 账本）。
4. 依次执行三项验收门禁，全部通过后删除旧实现并迁移既有测试。
