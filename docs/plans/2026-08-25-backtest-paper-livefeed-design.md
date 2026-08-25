# 回测与 Paper Trading 拆分：LiveFeed 实时数据平面设计

日期：2026-08-25
状态：已与需求方确认方向（方案 C：LiveFeed 接口 + 回放器首实现）

## 背景与问题

平台同时存在两条策略验证链路，引擎层本就分开：

- **回测**：NT `BacktestEngine`，批量跑封闭历史区间 `[start, end]`，跑完出报告。回答"策略在过去行不行"。
- **Paper Trading**：NT `TradingNode`（live 内核），常驻进程，跟随实时行情。回答"策略在部署链路上行不行、从现在开始的表现"。

问题在于 Paper 的数据平面：行情源是静态 PIT 库（一次性批量导入的历史数据），没有新 bar 流入。paper 节点水位线推到最新后只能空转——表现为"一直在跑、永不开仓、永不结束"，看起来像一个跑不完的回测，概念上把两条链路混淆了。

## 概念边界（拆分契约）

| | 回测 | Paper Trading |
|---|---|---|
| 目的 | 历史区间验证策略 | 部署链路验证 + 实时跟踪 |
| 引擎 | NT `BacktestEngine`（批量） | NT `TradingNode`（live） |
| 数据 | PIT 封闭区间 `[start, end]` | LiveFeed 持续写入 PIT → 增量轮询 |
| 生命周期 | 排队 → 运行 → 完成（有终态） | 常驻，直到暂停/关闭 |
| 策略 | 同一份冻结 artifact | 同一份冻结 artifact |
| 撮合语义 | 同一套费率/涨跌停模型（`markets/`） | 同左 |
| 桥梁 | 「对拍」：同区间 paper 净值 vs 回测净值 | 同左 |

两边共享：冻结策略 artifact、撮合语义、NT 引擎家族。唯一新增组件是 **LiveFeed 生产者**。

## 语义约定（已落地，文档化）

- 预热：paper 节点启动时经 NT 历史数据通道（`request_bars` → `on_historical_data`）补齐指标窗口——只喂指标，不产生订单流。
- 信号：策略的订单只能由水位线之后的**新 bar** 触发（实盘通道 `_handle_data`）。
- `bars_total` 只统计实盘通道推送的 bar，不含预热。

## LiveFeed 设计

### 接口

唯一职责：**按节奏把新 bar 写进 PIT**（`pit_observations`，与 `ingest-market-data.py` 同一格式）。paper 节点侧的 `PitBarPoller` 零改动。

```python
class LiveFeed(Protocol):
    def run(self, stop: Event) -> None: ...
```

### 首实现：时钟驱动的历史回放器（ReplayFeed）

把 PIT 中已有的历史分钟线按"虚拟时钟"重新直播：

- **数据源**：PIT 已有分钟线（5m 基础粒度），只回放，不重新采集。
- **节奏**：`--speed N` 倍速（1 = 真实时间 1:1；默认加速以便演示）。每根 bar 的"播出时刻"由其事件时间在回放时钟上映射。
- **交易时段感知**：复用 `markets/nt/sessions.py`（日盘/夜盘时段表），非交易时段不回放；回放时钟跳过非交易时段（或按倍速空转，二选一，默认跳过）。
- **起点**：`--from <ts>` 指定回放起点（默认：PIT 该标的最新 bar 之后无法回放——因此默认从指定日期开始；演示用 `--from 2026-08-17` 这类有数据的区段）。
- **写入语义**：`event_time` 保留 bar 原始时间戳（策略看到的"行情时间"）；`available_time`/`ingested_at` 写入真实当前时刻（PIT 语义：数据"何时可见"）——paper 节点按 event_time 水位线消费，自然逐根可见。
- **幂等**：同 `(field, instrument, event_time)` 重复回放时 revision 递增，PIT 去重，重启安全。

### 后续实现：真实实时行情接入（RealFeed）

iFinD / akshare 实时轮询写 PIT。同一接口，配置切换。本设计不实现，仅留接口位置。

### 运行形态

- `scripts/live-feed.py --instruments RB2610.SHF --from 2026-08-17 --speed 10`（本地/调试）
- compose 服务 `live-feed`（profile: `paper`），与 paper-node 同生命周期管理

## 数据流

```
回测（不变）：
  PIT [start,end] ──> BacktestEngine ──> 回测报告

Paper Trading：
  ReplayFeed ──写入──> PIT pit_observations
                          │ （新 bar 持续到达）
  PitBarPoller 水位线增量轮询 ──> PitDataClient._handle_data
                          │（NT 实盘通道）
                    策略 on_bar → 订单 → 沙箱撮合 → 对账入 PG
```

## 错误处理

- ReplayFeed 读到 PIT 空洞（缺字段的 bar）：跳过该时间戳并计数，日志告警。
- 回放追平数据源末尾：feed 进入空转心跳（每 N 秒无操作），不退出——与真实行情"收盘后无数据"同构。
- paper 节点异常与现状一致：cycle 失败落 `run_state.last_error`，运维页可见。

## 测试

- 单元：回放时钟映射（倍速、时段跳过）、PIT 写入幂等（重复回放不产生重复 bar）。
- 集成：回放器 + paper 节点端到端——feed 开播后节点 `bars_total` 增长、策略有机会在新 bar 上开仓、成交落库。
- 回归：现有 `tests/paper/` 84 项保持不变。

## 范围外（YAGNI）

- 真实实时行情接入（RealFeed）只留接口，不实现。
- 回放不改变 paper 节点的任何执行/对账/风控逻辑。
- 不做多账户多标的的复杂调度（首版单标的多实例即可）。
