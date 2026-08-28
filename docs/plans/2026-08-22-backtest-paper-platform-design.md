# 回测与仿真（Paper Trading）平台设计

日期：2026-08-22
状态：**已实施**（回测修复 + paper 平台全部落地；见文末实施记录）
关联：`2026-08-22-nl-strategy-pipeline-design.md`、G18 NautilusTrader 集成

## 0. 本文结论来源

本文基于 2026-08-22 对工作区最新未提交代码的逐文件 review：

- `strategy_generation/` 全部 7 个文件（agent/schemas/repository/api/service/backtest）
- 共享面改动：`api/app.py`（DI）、`research/models.py`（strategy_drafts 表）、
  `experiment_runtime/execution_state_service.py`（`:paper` 占位符）、迁移
  `20260822_0015_create_strategy_drafts.py`
- NT 路径：`markets/nt/backtest.py`、`fills.py`、`fees.py`、`futures_fee.py`、
  `backtest/service.py`
- 验证：`pytest tests/strategy_generation` 20 passed。

## 1. 回测 ≠ 仿真：两个平台

回测是**批处理评估任务**；仿真（paper trading）是**常驻交易系统**。二者回答
不同的问题，必须是两个独立平台，只共享该共享的组件。

| | 回测 | 仿真 Paper |
|---|---|---|
| 本质 | 一次性喂全部历史，产出报告即止 | 与真实市场同一时钟持续运行 |
| 数据 | 固定历史，整根 bar 原子到达 | 增量到达，bar 走完才闭合 |
| 成交 | 引擎内预计算撮合 | 订单全生命周期，模拟交易所对后续真实行情撮合 |
| 回答 | 这个策略历史上赚不赚钱 | 这条链路跑不跑得通（时序/重启/断供/滑点假设） |
| 失败 | 重跑 | 告警 + 运维 |

回测永远暴露不了的问题——进程重启丢指标状态、行情迟到、重复推送、错过收盘
时点——正是 paper 存在的意义。**「paper = 延迟一天的回测」是错误表述**；
正确说法是：两者共享策略执行内核与市场规则事实源，但部署形态、数据路径、
账本和运维完全不同。

频率不是平台属性而是策略属性：冻结工件 meta 携带 frequency（1d / 5m / 未来
扩展），两个平台都按 bar_type 参数化，不做日频特判。

## 2. 平台边界与共享件

```text
        FrozenStrategyArtifact（内容寻址 + HMAC 签名）
                      │
          安全加载器（AST 白名单扫描 + 受限实例化）
           共享：markets/ 唯一事实源（费率/涨跌停/T+1/
           合约规格/交易时段）、InstrumentMaster、PIT store
                      │
      ┌───────────────┴───────────────────┐
      ▼                                   ▼
【回测平台 Batch】                  【仿真平台 Paper】
输入: 工件+日期区间+初始资金         输入: 工件 → 创建常驻账户
引擎: NT BacktestEngine             引擎: NT TradingNode(Live 内核)
全量历史一次回放，确定性 hash          + SimulatedExchange 撮合
产出: BacktestResult 工件            + 行情数据客户端(增量推送)
用途: 评估策略好不好                  产出: 订单/成交/持仓/净值账本(PG)
                                      用途: 验证链路和执行假设
```

策略上线流程 = 回测通过（评估）→ paper 账户运行 2-4 周（验证链路）→ live。
live 不在本文范围。

## 3. Review 结论与回测平台修复清单

### 3.1 已确认的问题

| 级别 | 问题 | 位置 |
|---|---|---|
| P0-1 | LLM 生成代码裸 `exec()`，import os/subprocess 等全部可用，无 AST 扫描 | `strategy_generation/backtest.py::load_strategy` |
| P0-2 | 引擎未挂载 FeeModel/FillModel：无佣金/印花税/过户费/期货手续费，无涨跌停阻断；payload 标注 gross_of_fees=True | `markets/nt/backtest.py` 两工厂 + `strategy_generation/backtest.py` |
| P0-2b | T+1 可卖约束不在 NT 路径（只在 markets/cn_a.py 事实源）；5m 频率下当日买卖可违规成交 | 同上 |
| P1-3 | 净值曲线手搓（trades+close 自算），忽略费用，与引擎账本双轨 | `_strategy_equity_curve` |
| P2 | 合约激活/到期伪造、`_CONTRACT_SPECS` 硬编码、freeze 未写 MinIO 工件、POST 无 Idempotency-Key、多标的每标的一实例、夜盘归属 | 记录在案 |

另确认：`FuturesFeeModel.get_commission(order, fill, fill_px, multiplier)` 签名
与 NT `FeeModel.get_commission(order, fill_qty, fill_px, instrument)` 不符，
**从未能真正挂载到引擎**——G18 只验证了其数值语义（golden case 直调）。

### 3.2 本轮实施（回测侧）

1. **P0-1**：新增 `strategy_generation/security.py`——导入白名单（nautilus_trader
   + 无害 stdlib 子集）+ 危险调用黑名单（eval/exec/open/__import__/compile/input）
   + dunder 属性封禁；`load_strategy` 执行前强制扫描，违例拒绝并回显原因。
   残余风险（混淆绕过）由后续 docker 沙箱路径兜底（SANDBOX_USE_DOCKER）。
2. **P0-2**：`build_equity_engine/build_futures_engine` 增加 keyword-only
   `fee_model`/`fill_model` 参数（默认 None 保持旧行为，向后兼容）；策略回测
   路径显式传入 `AShareFeeModel` 与期货费用适配器。
3. **期货费用适配器**：新增 `FuturesVenueFeeModel`（正确 NT 签名），内部复用
   `FeeSchedule/close_offset_fee/offset_from_order` 唯一事实源；未打平今/平昨
   tag 的订单按平昨计（与 G18 决策一致）。
4. **P0-2b（审计式）**：日频 1d 下结构性不可能当日回转（每 bar 一次决策）；
   5m 下可行。本轮实现**成交后审计**：从 fills 报告检测 A 股同日先买后卖
   （T+1 违规）并以 `constraint_violations` 字段披露，不做深度引擎改造。
5. **P1-3（务实版）**：`BacktestTrade` 增加 commission；净值曲线逐笔扣费，
   payload 改为 `cost_basis="net_of_fees"` 并保留费用总额；期末对账引擎账户
   余额，偏差超容差写入 warning 字段。完整的事件级 account 曲线留待 paper
   阶段统一实现。

### 3.3 后续（记录）

- 合约规格/乘数迁往 InstrumentMaster；合约生命周期用真实日期
- freeze 写 MinIO 内容寻址工件（hash 已有，缺不可变存储）
- POST Idempotency-Key；多标的跨标的信号策略形态
- 正式净成本口径下沉为引擎默认（当前 alpha-pool 服务仍为毛回测且 UI 已披露）

## 4. 仿真平台（Paper Trading）设计

### 4.1 核心形态

每个 paper 账户 = 一个常驻 NautilusTrader **TradingNode**（Live 内核），
订单不进真实柜台，进 **SimulatedExchange**：

```text
TradingNode（常驻容器，一账户一节点）
 ├── LiveDataClient    按 bar_type 频率拉行情 → 推 Bar 事件进节点
 ├── SimulatedExchange 用 markets/ 的费率模型+涨跌停 FillModel 模拟撮合，
 │                     对"之后到达的真实行情"成交（非预计算函数）
 ├── Strategy          加载自冻结工件（与回测同一份代码，零改动）
 └── EventLog → PG     订阅节点事件总线，orders/fills/positions 持久化
```

### 4.2 多频率

频率是冻结工件 meta 属性，平台按 bar_type 参数化：

| 频率 | 数据客户端行为 | 时钟依据 |
|---|---|---|
| 1d | 每交易日收盘后拉当日 EOD 推入节点 | sessions.py 日盘时段 |
| 5m | 交易时段内每 5 分钟拉增量 K 线推入 | 同上，含期货夜盘归属 |
| 扩展 | 新增 bar_spec + 拉数节奏 | 架构不变 |

数据源现实约束：AKShare/iFinD 盘中数据为轮询延迟行情，MVP 可接受（PRD FR-602
允许延迟行情）；websocket 实时源只替换 LiveDataClient 实现。

### 4.3 模块结构（全新包，零接触 strategy_generation）

```text
src/quant_platform/paper/
├── contracts.py     # PaperAccount 状态机(ACTIVE/PAUSED/CLOSED)、BarSchedule
├── artifact.py      # 工件加载：MinIO 取对象、验 hash、验签（复用 artifacts/store.py）
├── loader.py        # 复用 strategy_generation/security.py 的安全加载
├── node.py          # TradingNode 装配：数据客户端 + SimulatedExchange + 策略挂载
├── data_client.py   # 按 bar_type 频率轮询 data_gateway、会话感知去重
├── sim_venue.py     # SimulatedExchange 参数全部取自 markets/
├── ledger.py        # 订阅 NT 事件总线 → 幂等写 PG（orders/fills/positions/equity）
├── scheduler.py     # 交易日历感知：何时该有 bar、夜盘归属、节假日跳过
├── monitor.py       # 心跳、行情 stale 检测、kill switch 绑定、对拍作业
├── repository.py    # accounts/runs/orders/fills/positions/equity 表
└── api.py           # 见 4.4
compose 增加 paper-node 服务（每账户一容器编排）
```

### 4.4 账户生命周期 API

```text
POST /v1/paper/accounts                 {draft_id} → 校验 FROZEN → 建账户+起节点
POST /v1/paper/accounts/{id}:pause      停止推数与交易，保留持仓
POST /v1/paper/accounts/{id}:resume
POST /v1/paper/accounts/{id}:close      平仓结算归档
GET  /v1/paper/accounts/{id}/orders|fills|positions|equity
GET  /v1/paper/accounts/{id}/health     节点心跳/最近bar时间/stale状态
```

### 4.5 关键机制

1. **启动恢复**：节点启动时从 PIT store 拉尾部窗口重放预热指标（回测内核唯一
   被借用处），随后对账内存持仓 vs PG ledger，不一致拒绝启动并告警。
2. **撮合真实性**：SimulatedExchange 收到市价单后用下一根真实到达的行情成交并
   叠加滑点——T 日信号 T+1 开盘才成交，时序错误表现为异常成交而非被掩盖。
3. **监控与安全**：行情 stale（该来的 bar 未到）→ PAUSE + 告警；kill switch
   绑节点层，trip 后所有账户拒单；每日对拍作业对比 paper 成交 vs 同窗口回测
   （价格偏差/成交率/成本占比）作为执行假设校验——对拍是工具，不是 paper 定义。
4. **验收标准**：订单全生命周期正确、重启可恢复、数据断供可感知、成交语义与
   markets/ 一致；不以收益接近回测为验收条件。

## 5. 并行开发边界（历史结论，存档）

对方占用（现已合并前状态）：`strategy_generation/**`、app.py 接线、
execution_state 占位符、frontend strategy chat。本文实施的改动仅触及
`markets/nt/backtest.py`（向后兼容可选参数）与 `strategy_generation/backtest.py`
（安全扫描 + 费用挂载），其余全部新增文件。

## 6. 实施记录（2026-08-22）

### 回测侧修复（§3.2 全部完成）

- `strategy_generation/security.py`：AST 白名单扫描接入 `load_strategy`
- `markets/nt/backtest.py`：引擎支持 `fee_model/fill_model`
- `FuturesFeeModel` 修正 NT 签名，可挂载引擎
- 净值曲线 net_of_fees + T+1 同日回转审计
- 潜伏 bug：`_ns_to_iso` 对 pandas Timestamp 失效导致曲线恒为平线（已修）

### Paper 平台（§4 全部完成）

| 设计项 | 实现 |
|---|---|
| contracts / artifact / repository | ✅ 含迁移 `20260822_0016`（5 张表） |
| sim_venue | ✅ `ChinaVenueSandboxExecutionClient` 注入 markets/ 费率 |
| node + data_client + ledger | ✅ TradingNode 装配、水位线增量拉数、幂等对账 |
| monitor | ✅ 心跳/stale/kill switch 绑定进运行循环 |
| drift | ✅ `GET /v1/paper/accounts/{id}/drift` 对拍报告 |
| 重启语义 | ✅ 非空仓拒绝启动（check_restart_safe） |
| compose 服务 | ✅ `--profile paper` + `PAPER_ACCOUNT_ID` |
| 前端运维页 | ✅ `/paper`：账户列表/生命周期/持仓/订单/成交/净值/对拍 |

验证：后端 pytest 704 passed；ruff/mypy/format 零错误；
前端 tsc/build/vitest（61 tests）通过；迁移在真实 PG 应用成功。
