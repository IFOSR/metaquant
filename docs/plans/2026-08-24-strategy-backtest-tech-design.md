# 策略回测交互重构：需求与技术方案

日期：2026-08-24
状态：设计稿（待评审）
配套：交互设计见 `2026-08-24-strategy-backtest-interaction-design.md`

## 1. 需求

### 用户故事

1. 作为用户，我描述策略后，**Agent 主动建议回测周期与时间段并说明理由**，
   我可以用自然语言或在面板上调整，而不是自己去猜该选什么。
2. 作为用户，我可以用**任意时间段**回测（近三年、某段行情），不限于库里
   已采集的数据——系统自动去构建。
3. 作为用户，我可以选**任意周期**（日线、5/15/30/60 分钟），不限于已有的
   1d/5m。
4. 作为用户，我的策略如果是「日线看趋势 + 分钟找点位」，系统能**自动识别
   并准备两套周期数据**（P2）。
5. 作为用户，数据缺失/拉取失败/代码报错时，我都能看到**明确的下一步动作**，
   绝不出现"点完回测才炸"。

### 验收标准（P1）

- 策略 ready 后，对话中出现带理由的回测方案建议；说「用近半年」方案即更新。
- 面板可编辑周期与起止日期；改完数据状态自动重查。
- 点「采集所需数据」可按方案构建任意时间段数据并入库；状态转绿后回测可用。
- 回测结果反映所选时间段与周期；全链路无裸 500、无事后爆炸。

## 2. Agent 输出契约扩展

`AgentOutput` 增加 `backtest_plan`（策略 ready 时必填，否则 null）：

```json
"backtest_plan": {
  "timeframes": ["1d"],
  "trend_timeframe": "1d",
  "exec_timeframe": "1d",
  "start": "2025-08-24",
  "end": "2026-08-24",
  "rationale": "均线趋势策略用日线即可，建议近一年覆盖完整行情段"
}
```

推导规则（写进系统提示词）：

- 趋势/均线/突破类 → 单周期日线，时间段近 1 年。
- 择时/入场点位类（「分钟找买点」「日线看趋势分钟进场」）→ 双周期：
  `trend_timeframe=1d`、`exec_timeframe=5m`，时间段按执行周期给（分钟
  数据给近 2~3 月）。
- 标的无分钟数据源时的降级由系统提示（数据状态），Agent 在对话中说明。
- start/end 由 Agent 按策略类型给建议值，用户可改。

## 3. 数据模型变化

`StrategyDraftModel` 增加 `backtest_plan`（JSON，nullable）：

- 随每轮 `apply_turn` 更新（来自 AgentOutput.backtest_plan）。
- `freeze` 时把 backtest_plan 一并计入 content hash。
- 迁移：新增迁移 `20260824_0016_strategy_backtest_plan`（注意与并行的
  paper 迁移 0016 对齐 revision 链——合入时重排为 0017）。

## 4. 数据构建层

`StrategyDataProvisioner` 扩展：

1. **任意时间段**：`provision(instrument_ids, frequency, start, end)` 已支持
   start/end 参数；P1 把 draft.backtest_plan.start/end 传进去。iFinD
   `date_sequence` 支持任意区间。
2. **任意周期**：新增 15m/30m/60m —— AkShare minute period 支持 1/5/15/30/60；
   `bar_spec`/`bar_type_suffix` 与净值聚合逻辑按周期参数化。周线列为可选。
3. **多周期（P2）**：`provision` 接受 `timeframes` 列表，逐周期构建；
   `data_status` 返回每周期就绪状态。
4. **失败兜底**：单标的失败记录原因，其余继续；全部失败抛
   `StrategyProvisionError`（现状保留）。

## 5. 回测层变化

- **P1 单周期**：`run_strategy_backtest` 接受 start/end（已有）+ frequency
  覆盖（已有）；按方案传入即可。
- **P2 多周期**：策略合约扩展为
  `__init__(self, instrument_id, bar_type_str, trend_bar_type_str=None)`，
  `bar_type_str` 为执行周期，`trend_bar_type_str` 为趋势周期；引擎喂两套
  bar，策略在 `on_bar`（执行周期）里读趋势指标。Agent 提示词加入多周期骨架。
- 分钟级长历史：iFinD `high_frequency` 端点契约待验证（P2 第一项任务）。

## 6. API 变化

| 端点 | 变化 |
|---|---|
| `GET /strategy-drafts/{id}` | snapshot 增加 `backtest_plan` |
| `GET /strategy-drafts/{id}/data-status?frequency=` | 已有；P2 支持 `timeframes=` 多值 |
| `POST :provision` | 接受 `frequency`（已有）+ `start`/`end` 覆盖 |
| `POST :backtest` | 接受 `frequency`/`start`/`end`（已有）；P2 多周期 |

## 7. 前端变化

1. 右侧栏改为三段：**策略产物 / 回测方案 / 数据准备**。
2. 「回测方案」区块：周期选择（P1 单选，P2 多选+角色）、时间段（起止日期 +
   快捷：近3月/近半年/近1年/近2年）、Agent 建议卡片「采用此方案」。
3. 「数据准备」区块：每个 标的×周期×时间段 的就绪/下载中/失败状态 + 重试。
4. 对话内：方案建议以卡片渲染；用户消息可引用方案调整。

## 8. 分阶段落地

### P1（本轮）：对话式回测方案 + 任意时间段数据构建

1. AgentOutput/draft 增加 backtest_plan；提示词加推导规则。
2. 迁移 + repository apply_turn/freeze 携带 plan。
3. provision 传 start/end；data-status 按 plan 周期检查。
4. 前端三段式面板 + 方案卡片 + 时间段/周期编辑。
5. 端到端：对话给方案 → 采集 → 回测。

### P2：多周期策略

6. 策略合约 trend/exec 双 bar type；引擎多套 bar；提示词多周期骨架。
7. iFinD `high_frequency` 端点契约验证 → 分钟级长历史。
8. provision/data-status/backtest 支持 timeframes 多值。

### P3：扩展

9. 15m/30m/60m 全链路；周线；多标的组合回测。

> 实施状态（2026-08-24）：P1/P2/P3 全部完成。与原文档的两点偏差：
> ① 分钟长历史在 P1 即完成（iFinD `high_frequency` 契约提前验证通过）；
> ② 多标的组合回测限定同一市场（单 venue，与既有因子回测一致），跨市场
> 给出明确错误而非静默失败。

## 9. 风险与取舍

- **分钟级历史受新浪限制**（约 10 个交易日）：P1 用 iFinD 日线补长窗口，
  分钟长历史依赖 P2 的 iFinD 高频端点验证；不验证通过就明确标注限制。
- **多周期撮合语义**：趋势 bar 与执行 bar 的时间对齐由引擎按 ts_event 处理，
  信号前视由「T 日信号 T+1 生效」纪律保证，P2 需专项测试。
- **方案与代码一致性**：backtest_plan 随草稿冻结进 content hash，防止
  「说的方案」与「跑的方案」漂移。

## 10. 已修复的生成代码失败类（生成时静态拦截）

- 建单不提交（缺 `submit_order`）
- `quantity` 未用 `instrument.make_qty(...)`
- `subscribe_bars` 误传 instrument_id
- `BarType.from_str` 硬编码字面量（允许 `bar_type_str`/`trend_bar_type_str`）
- `portfolio.net_position(...)` 误用 `.signed_qty`（它返回 Decimal）
- 指标属性幻觉（MACD `.signal` 等，已提供精确属性表 + DEA 自算配方）
- 任意失败（含网络超时）自动纠正重试一次；API 侧任意异常优雅 502
- 配置类属性读取（`SimpleMovingAverage(MyConfig.ma_period)`）：pydantic 类属性是
  `member_descriptor` 非 int，会崩指标构造。三层防错：① 提示词禁止该读法；
  ② 生成时静态拦截并自动纠错；③ `load_strategy` 加载时把 `SomeConfig.attr` 改写为
  `SomeConfig().attr`（配置实例才是真正值），已冻结的旧策略也能加载。
