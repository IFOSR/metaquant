# 回测与仿真交互层重构 —— 对齐 NautilusTrader 交互逻辑

日期：2026-08-24
状态：**P1/P2 已实施，P3 部分实施，P4 部分实施（详见文末「实施状态」）**
配套：`2026-08-22-backtest-paper-platform-design.md`（平台边界，保留）
      `2026-08-24-strategy-backtest-interaction-design.md`（对话式回测方案，保留）

## 0. 范围澄清：本次重构做什么、不做什么

**引擎就是 NautilusTrader，不重写、不替换、不封装替代品。** 咱们所有回测与
仿真已经跑在 NT 之上。本次重构的对象是**包住 NT 的那层交互**：API 形态、
任务模型、报告模型、账本对账方式、状态恢复、节点生命周期——让这层的
**交互逻辑**与 NT 自身一致，消除「引擎是 NT 的，但用法不像 NT」的落差。

| 做 | 不做 |
|---|---|
| 策略回测（`strategy_generation/backtest.py`）交互层对齐 NT | 因子回测（`backtest/service.py`、`BacktestService` alpha-pool）本次不动 |
| Paper 仿真（`paper/*`）交互层对齐 NT | 不重写 NT 引擎 / 不引入 Parquet catalog（数据在 PIT store） |
| 报告、任务、账本、状态恢复的交互模型 | 不做 live 实盘 |
| 市场规则 → venue 装配（fee/fill/latency）下沉 | 不重构 `markets/` 事实源本身 |

**既定决策**：同步入口（`POST /strategy-drafts/{id}:backtest`）保持同步等待，
前端交互不变；新增的批量矩阵入口走异步任务。

---

## 1. NT 的交互逻辑（学习清单）

### 1.1 回测的交互：BacktestEngine

NT 回测的「用法」是一条固定的装配流水线，配置驱动、结果从引擎出：

```python
engine = BacktestEngine(BacktestEngineConfig(...))        # ① 配置对象
engine.add_venue(venue, oms_type, account_type,           # ② venue = 全部执行假设
                 starting_balances, fee_model, fill_model,
                 latency_model, price_protection, ...)
engine.add_instrument(instrument)                         # ③ 合约
engine.add_data(bars)                                     # ④ 数据（多流按时间戳合并）
engine.add_strategy(strategy)                             # ⑤ 策略
engine.run()                                              # ⑥ 跑
engine.trader.generate_account_report(venue)              # ⑦ 结果 = 报告
engine.trader.generate_order_fills_report()
engine.trader.generate_positions_report()
engine.dispose()                                          # ⑧ 释放
```

交互要点：

1. **配置驱动**：`BacktestEngineConfig` 描述一次运行；同一份数据换组件重跑 =
   新配置、新引擎。
2. **venue = 执行假设的落点**：撮合/费用/滑点/延迟/价格保护/账户类型都是
   `add_venue` 参数，不是散落在策略或调用方。
3. **结果从报告出**：净值、成交、持仓来自 `trader.generate_*_report()`，
   调用方不重算账本。
4. **确定性显式化**：fill model 的随机种子、latency、价格保护点、流动性消耗
   全部是 venue 参数，可复现。
5. **bar 时间语义**：bar 的 `ts_init` 必须等于区间收盘，撮合才在正确的时点发生。

### 1.2 回测批处理的交互：BacktestNode

当回测从「跑一次」变成「跑一批/多参数」时，NT 提供高级 API：

- `BacktestRunConfig` 一个配置对象描述并标识一次 catalog 支持的运行；
- **每次独立运行使用全新引擎**（fresh engine per run）；
- 批量 = 配置列表，逐项运行，结果按配置 ID 取。

### 1.3 模拟的交互：TradingNode + SandboxExecutionClient

NT 的「模拟/paper」交互模型（`concepts/live` + `adapters/sandbox/execution.py`）：

1. **同一个撮合引擎**：`SandboxExecutionClient` 是一个 `LiveExecutionClient`，
   内部挂 `SimulatedExchange`（与回测同一个类）+ `TestClock` +
   `BacktestExecClient` 桥接。→ 回测与模拟的撮合语义由构造保证一致。
2. **数据走消息总线**：data client 增量拉取行情，发布到
   `data.bars.{bar_type}` topic，策略照常订阅——回测里的「喂数据」变成
   live 里的「推数据」，策略代码零改动。
3. **节点生命周期**：`node.run_async()`（宿主 loop）/ `node.run()`（独占线程）；
   `node.handle()` 提供跨线程 `stop()`；**一个进程一个 LiveNode**。
4. **启动 reconciliation**：启动时恢复缓存中的订单/持仓，与 venue 报告对齐后
   才启动策略；运行期持续校验在途订单/持仓/自有订单簿。
5. **报告同源**：`ReportProvider` 从 cache 生成报告，**回测与 live 同一套**，
   「回测→实盘评估一致」是设计承诺。

### 1.4 状态与事件的交互

- **Cache 即状态**：订单、持仓、账户、行情都在 cache；报告、对账、恢复都
  从 cache 派生。
- **MessageBus 即事件**：成交、持仓变化、账户状态变化都以事件形式在总线上
  流转，订阅者（对账、监控、审计）消费事件，而不是轮询快照 diff。
- **账本 = 事件投影**：把事件持久化即可重建状态（event sourcing 思想），
  这是「重启可恢复」的基础。

---

## 2. 咱们现状对照：哪些交互没学到位

引擎全是 NT 的，但外层的「用法」有几处跟 NT 的交互逻辑不一致：

| NT 交互逻辑 | 咱们现状 | 差距 |
|---|---|---|
| 结果从 `generate_*_report()` 出 | `_strategy_equity_curve` 用成交+bar 手搓净值，期末才跟引擎余额对账 | **双轨**：报告的净值可能不是引擎账本结算的净值 |
| venue = 全部执行假设 | fee_model 挂了，`PriceLimitFillModel` 没挂；latency/seed 无参数；paper 的 `fill_model=None` | 执行假设没全下沉到 venue |
| 配置驱动 + fresh engine per run | 回测在 API 请求内同步跑，无任务对象、无批量、无幂等 | 没有 BacktestNode 那层交互 |
| 报告回测/实盘同源 | 回测手搓、paper 对账也各自算，drift 在两套口径间换算 | 报告不同源 |
| 状态恢复 + reconciliation | `check_restart_safe` 拒绝非空仓重启 | 用运维约束替代状态恢复 |
| 事件驱动对账 | `reconcile()` 每周期轮询 fills/positions 报告快照 diff | 轮询快照替代事件投影 |
| 节点生命周期（handle/graceful stop） | API 内 `subprocess.Popen(paper-node.py)` + 心跳推断在跑 | 没有 handle 语义 |
| bar `ts_init` = 收盘 | `to_nautilus_bars` 里 `ts_init = ts_event`，未核对 PIT event_time 语义 | 撮合时点可能错位 |

---

## 3. 目标交互模型（对齐设计）

### 3.1 策略回测：学 BacktestEngine / BacktestNode 的用法

**交互 ①：配置驱动 + fresh engine per run**

新增 `BacktestRequest`（声明式配置，对应 NT 的 config 对象，内容寻址）：

```python
@dataclass(frozen=True)
class BacktestRequest:
    draft_id: str                # 冻结策略工件
    market: str                  # CN_A / CN_COMMODITY_FUTURES
    instrument_ids: tuple[str, ...]
    frequency: str               # 执行周期
    trend_frequency: str | None  # 趋势周期（多周期）
    start: date | None
    end: date | None
    initial_cash: Decimal
    venue_spec: VenueSpec        # fee/fill/latency/seed/价格保护（见交互②）
    def content_hash(self) -> str: ...
```

每次运行 = `BacktestRunner.run(request)` → **新建引擎、装配、跑、出报告、释放**，
与 NT「每次独立运行用全新引擎」一致；同 request_hash 幂等。

**交互 ②：venue 装配 = 市场规则落点**

新增 `markets/nt/venue.py::VenueSpec`，把 `add_venue` 的参数显式建模：

```python
@dataclass(frozen=True)
class VenueSpec:
    market: str                  # 派生 account_type（CASH/MARGIN）
    fee_model: FeeModel          # AShareFeeModel / FuturesFeeModel
    fill_model: FillModel        # PriceLimitFillModel（涨跌停）
    latency_model: LatencyModel  # 默认 0，可配
    random_seed: int | None      # fill model 确定性
    price_protection_points: int | None
```

- `build_equity_engine/build_futures_engine` 增加 `venue_spec` 入口（旧签名兼容）；
- **`PriceLimitFillModel` 挂上**（现状写了没用），补 golden 测试
  （涨停挂单不成交、跌停卖单不成交、触及后成交，对齐 `markets/cn_a.py`）；
- 报告带口径声明：`cost_basis`、`fee_model`、`fill_model`、`latency`、`seed`。

**交互 ③：结果从报告出，不手搓（直接以 NT 为准）**

- 净值曲线直接改从引擎出：逐 bar 收集 `AccountState`/组合盯市（或
  `generate_account_report()` + positions 快照）派生 equity，
  **删除** `_strategy_equity_curve` 的「成交→持仓→盯市」重算路径，
  不做双轨校验；
- trades/positions 继续用 `generate_order_fills_report()/positions_report()`
  （已经是引擎报告，保留）；
- `backtest_hash` 确定性投影保留（验收门禁）。

**交互 ④：任务化 + 批量（学 BacktestNode）**

新增表 `backtest_tasks` + 执行器：

```
POST /backtests                # 单任务，202，幂等（request_hash）
GET  /backtests/{id}           # 状态 + 报告（DONE 从 MinIO 读）
POST /backtests:matrix         # 参数列表 → 批量任务（每次独立引擎）
```

- 同步入口 `POST /strategy-drafts/{id}:backtest` **保持同步**（内部跑内核，
  返回统一报告 schema），前端不动；
- 批量矩阵的典型维度：窗口（近1年/近2年…）× 频率（1d/5m/15m…）×
  成本口径（gross/net/滑点假设）× seed。

### 3.2 仿真（paper）：学 TradingNode + Sandbox 的用法

**交互 ①：venue 装配与回测同一份**

- `exec_factory_for` 从「按市场选 fee_model」扩展为「按市场选完整 VenueSpec」；
- `ChinaVenueSandboxExecutionClient` 的 `fill_model=None` → 挂
  `PriceLimitFillModel`；latency/seed 可配；
- 回测与 paper 共用 `markets/nt/venue.py`，撮合假设同一来源。

**交互 ②：事件驱动对账（学 MessageBus 交互）**

- 节点内订阅 `OrderFilled` / `PositionEvent` / `AccountState`，事件写账本
  （幂等 upsert，fill_key 逻辑保留），**直接切换，不做快照双写过渡**；
- 心跳 run-state、kill switch、监控保留（它们是运维语义，不是账本语义）。

**交互 ③：状态恢复 + reconciliation（替代拒绝重启）**

- 启动时从 PG 账本恢复：instruments → positions（数量/方向/均价）→
  账户余额，重建 NT cache，再启动策略（订单不回放：市价单 + bar_execution，
  账本已有成交结果）；
- 恢复后与账本对账，不一致则**拒绝启动并报差异**（保留现有保护为兜底，
  默认路径是恢复）；
- 这对应 NT live 的「cache 恢复 + 启动 reconciliation」交互。

**交互 ④：节点生命周期（学 LiveNode handle 语义）**

- 封装 `PaperNodeHandle`：`start()` / `stop()`（graceful，对应
  `node.handle().stop()`）/ `health()`；
- API 新增 `POST /paper/accounts/{id}:stop-node`（幂等）；
- 部署形态不变：一账户一进程（compose `paper-node` profile），API 内
  subprocess 仅为本地演示路径。

**交互 ⑤：报告同源**

- paper 同样产出 `ReportProvider` 报告（fills/positions/account）；
- drift 对拍改为「回测报告 vs paper 账本」**同口径**对比（同一 VenueSpec、
  同一 cost_basis），消除两套 schema 换算。

### 3.3 数据路径

- **bar 语义核对**：确认 PIT `event_time` 是收盘时点；若是开盘时点，
  `to_nautilus_bars` 里 `ts_init = ts_event + interval`（NT 要求 ts_init=收盘）。
  加 golden 测试验证撮合时点。
- **多周期**：继续用现有 trend/exec 双 bar type（NT 多流按时间戳合并已支持）。

---

## 4. 落地范围

本次只改两条线：

1. **策略回测线**：`strategy_generation/backtest.py` +
   `markets/nt/backtest.py`（venue 装配）+ 新增 `backtest_tasks`；
   前端 `/strategy` 回测结果区按统一报告渲染（口径声明行）。
2. **仿真线**：`paper/*`（venue 装配、事件对账、状态恢复、节点生命周期）；
   前端 `/paper` 展示恢复/口径信息。

**不碰**：`backtest/service.py`（因子回测）、`experiment_runtime/backtest_service.py`
（alpha-pool 编排）、`markets/` 事实源本身。

---

## 5. 分阶段落地

### P1：策略回测交互对齐（最高价值）

1. `BacktestRequest` + `VenueSpec`（`markets/nt/venue.py`）+ 引擎工厂接入；
2. 净值曲线直接改为从引擎账户/组合状态派生，**删除手搓路径**（一次性 golden
   case 对拍确认切换无 bug，不做运行时双轨）；
3. `PriceLimitFillModel` 挂载 + golden 测试；报告带口径声明；
4. 同步入口返回统一报告 schema，前端结果区小改。

### P2：回测任务化（学 BacktestNode）

6. `backtest_tasks` 表 + 执行器 + `POST /backtests` / `GET /backtests/{id}` /
   `:matrix`（幂等、批量、每次独立引擎）；
7. 同步入口保持同步（内部跑内核）。

### P3：仿真交互对齐

8. paper venue 装配下沉（fill_model 挂涨跌停、latency/seed 可配）；
9. 事件订阅对账（直接以事件为准，移除轮询快照写）；
10. 账本恢复 + 启动 reconciliation（替代拒绝重启主路径）；
11. `PaperNodeHandle` + `:stop-node`；drift 同口径化。

### P4：收尾

12. bar `ts_init` 语义核对与修正（如需要）+ 撮合时点 golden 测试；
13. 前端参数矩阵 UI、paper 恢复失败原因展示。

---

## 6. 风险与取舍

- **数字变化风险**：净值从手搓切到引擎账本后，历史回测数字可能变化（费用
  时点、保证金、盯市语义）。对策：**一次性 golden case 对拍**验证切换正确性
  （不是运行时双轨）；口径全部显式声明（`cost_basis`/`fee_model`/
  `fill_model`/`latency`/`seed`）。
- **因子回测不动**：alpha-pool 保持 gross 口径现状，`markets/nt/backtest.py`
  的工厂旧签名兼容（默认行为不变），避免影响研究侧评审指标。
- **同步入口保持同步**：`POST /strategy-drafts/{id}:backtest` 前端交互不变，
  批量异步只走新入口。
- **恢复重建的正确性**：SimulatedExchange 无状态，恢复 positions/balances
  依赖确定性 ID（`use_random_ids=False` 已保证）；恢复后必须账实对账，
  不一致宁可拒绝启动（保留现状保护为兜底）。
- **事件对账直接切换**：事件流下 bar 到达/事件到达/落库顺序与轮询不同，
  直接切换后账本完全以事件为准；一致性由幂等 upsert（fill_key）+ 监控
  兜底，不做双写。
- **不做什么**：不重写 NT 引擎、不引入 Parquet catalog、不做 live 实盘、
  不动因子回测、不重构 `markets/` 事实源。

---

## 附：调研来源

- NT 官方文档：`/docs/latest/concepts/backtesting/*`（apis-and-runs、
  data-and-venues、execution-flow、bar-execution、fill-models、
  accounts-and-margin）、`concepts/live`、`concepts/reports`、`concepts/architecture`
- NT 1.231 源码：`nautilus_trader/adapters/sandbox/execution.py`
  （SandboxExecutionClient = SimulatedExchange + BacktestExecClient + TestClock）、
  `config.py`、`examples/backtest/example_01_load_bars_from_custom_csv`
  （canonical 回测流水线）
- 本项目现状：`strategy_generation/backtest.py`、`paper/*`、`markets/nt/*`

---

## 实施状态（2026-08-24）

### P1：策略回测交互对齐 —— 已实施 ✅

- **`BacktestRequest` + `VenueSpec`**（`markets/nt/venue.py`）：声明式配置、内容寻址
  （`content_hash`）、`to_dict/from_dict`；引擎工厂 `build_equity_engine`/
  `build_futures_engine` 增加 `venue_spec` 入口（旧签名兼容）。
- **净值曲线从引擎出**：删除手搓 `_strategy_equity_curve`（成交→持仓→盯市双轨），
  改为订阅 `data.bars.{exec_bar_type}`，逐 bar 采样 `portfolio.equity(venue)[CNY]`
  （引擎自己的组合权益，正确处理账户类型/乘数/费用），运行结束补终值点。
  一次性 golden 对拍：既有数值断言全部通过（切换无数字漂移）+ 新增
  `test_equity_curve_from_engine_is_consistent_with_final_equity`。
- **`PriceLimitFillModel` 挂载**：`venue_spec_for_market` 默认挂涨跌停撮合
  （空 price_limits 时行为不变）；golden 测试已存在（`test_fills.py`）。
- **报告口径声明**：`venue_spec.payload()`（cost_basis/fee_model/fill_model/
  latency/seed/price_protection）写入回测结果；前端回测结果区显示口径行。

### P2：回测任务化 —— 已实施 ✅（路径偏差）

- `backtest_tasks` 表（迁移 0019）+ `BacktestTaskService`（ThreadPoolExecutor 后台执行、
  幂等按 request_hash、结果统一报告 JSON 存 MinIO）。
- 端点：`POST /strategy-backtests`（202，幂等）、`GET /strategy-backtests/{id}`（状态+报告）、
  `GET /strategy-backtests`（列表）、`POST /strategy-backtests:matrix`（批量）。
  **偏差**：设计稿写 `/backtests`，但该路径已被因子回测（experiment_runtime）占用且
  设计明确不碰因子回测，故策略任务挂 `/strategy-backtests`。
- 同步入口 `:backtest` 保持同步（内部跑内核，返回统一报告 schema）。

### P3：仿真交互对齐 —— 部分实施

- ✅ **venue 下沉**：`exec_factory_for` 按市场挂共享 `VenueSpec` 的 fill_model
  （`PriceLimitFillModel`），回测/仿真撮合假设同源。
- ✅ **节点生命周期**：`POST /paper/accounts/{id}:stop-node`（幂等，本地子进程路径
  按进程组 SIGTERM 优雅停；compose 部署路径提示用 docker 停）。
- ⏳ **事件驱动对账**（订阅 OrderFilled/PositionEvent 写账本）与**状态恢复 +
  reconciliation**（从 PG 重建 NT cache）：需要真实 `paper-node` 运行时验证，
  本轮未实施（风险高，见下）。
- ✅ drift 已通过共享 `venue_spec` 对齐口径（回测报告带口径声明，drift 复用
  `backtest_service.run` 即同一口径）。

### P4：收尾 —— 部分实施

- ✅ **bar ts_init 核对**：确认 `to_nautilus_bars` 中 `ts_init == ts_event == bar 收盘时点`
  （PIT event_time 即收盘），加 golden 测试 `test_bar_ts_init_equals_ts_event_close`。
- ⏳ 前端参数矩阵 UI / paper 恢复失败原因展示：未实施（后端能力已具备）。

### 验证

- 后端 ruff / mypy / **758 测试通过**；前端 tsc / eslint / vitest 通过。
- 桌面端 E2E：浏览器打开冻结策略 → 回测 → 结果区显示口径行
  （`net_of_fees · FuturesFeeModel · PriceLimitFillModel`）；任务接口创建→后台执行→
  DONE 落 MinIO→读取结果全链路走通；`:matrix` 批量建任务。

### 后续（未纳入本轮，需真实 paper-node 运行时验证）

- **事件驱动对账**（P3#9）：事件流下 bar/事件/落库顺序与轮询不同，直接切换有风险，
  需在真实节点上验证幂等 upsert 与监控兜底。
- **状态恢复 + reconciliation**（P3#10）：从 PG 恢复 positions/balances 重建 NT cache，
  依赖 SimulatedExchange 无状态 + 确定性 ID；需节点实跑验证账实对账。
- **前端参数矩阵 UI**（P4#13）。

