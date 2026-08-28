# 策略持久化与开仿真盘：交互与实现

日期：2026-08-24
状态：已实施（保存策略列表 + 开仿真盘四步流程 + 数据就绪校验，前后端测试通过）

## 0. 背景

早期「策略对话」页只支持单次会话，存在三个缺口：

1. **保存的策略无处可看**：冻结（freeze）只把草稿持久化到库，但前端没有任何地方
   能列出「已保存（冻结）的策略」，用户关掉对话就找不到自己的策略了。
2. **保存后点不开**：`/strategy` 页只有 Alpha 池与组合契约占位，冻结策略行不可点，
   无法再看、再回测、再进仿真。
3. **仿真盘只是一个按钮**：先前「开仿真盘」直接以草稿默认参数 `POST /paper/accounts`，
   没有「选策略 → 选窗口 → 确认频率/合约 → 校验数据就绪」的选择过程；
   数据没准备好时直接开账户，或在频率不受支持时裸 500。

## 1. 设计原则

1. **冻结 = 不可变快照**：冻结策略内容指纹（content_hash）定型，可被回测/仿真盘安全复用；
   需要继续改时显式「解除冻结」。
2. **选择先于开单，数据先于资金**：开仿真盘前，用户先确认策略/窗口/频率/合约，
   并确保所需数据就绪（复用回测期已拉取的数据，缺则兜底补齐），再创建账户。
3. **频率与合约由策略派生**：冻结策略代码按特定执行周期与标的编写（`__init__` 参数化
   但仍绑定），因此开仿真盘时频率、合约**只读确认**，可自由改的只有时间窗口与初始资金。
4. **状态可见，失败有下一步**：数据就绪校验逐项展示，缺数据给「采集所需数据」。

## 2. 全流程

```
S1 保存策略            S2 列出已保存            S3 开仿真盘配置         S4 建账户
──────────            ───────────────         ───────────────         ──────────
策略对话 → 冻结    →   /strategy 可见已保存  →   选策略 → 确认窗口  →   POST /paper/accounts
(内容指纹定型)         行可点               →   /确认频率/合约         → 跳转 /paper
                                              + 数据就绪校验           选中新账户
                                              (缺则采集所需数据)
```

## 3. 阶段详设

### S1 保存策略（冻结）

- 对话页「冻结策略」：`POST /strategy-drafts/{id}:freeze`，写入 `content_hash`。
- 冻结后对话锁定（写入 409 `STRATEGY_DRAFT_FROZEN`），但可回测、可开仿真盘。
- 「解除冻结继续编辑」：`POST /strategy-drafts/{id}:unfreeze`，回到 `READY`，
  清空 `content_hash`（再冻结会重算）。

### S2 列出已保存

- `/strategy` 页新增「已保存策略」面板：`GET /strategy-drafts?state=FROZEN`，
  展示标题/市场/标的/周期/内容指纹/冻结时间。
- 每行可点击 → 跳转 `策略对话?draft=<id>`，按 id 重新打开该草稿（含对话记录）。

### S3 开仿真盘配置（`OpenPaperDialog`）

对话框四步 + 数据就绪校验：

| 步骤 | 交互 | 数据来源 |
|---|---|---|
| ① 选择策略 | 下拉列出冻结策略，默认当前页打开的 | `GET /strategy-drafts?state=FROZEN` |
| ② 回测时间段 | 起止日期，默认该策略回测方案窗口，可改 | `backtest_plan.start/end` |
| ③ 数据频率 | 只读展示执行周期 + 趋势周期 | `backtest_plan.exec_timeframe/trend_timeframe` |
| ④ 模拟合约 | 只读展示标的 | `draft.instrument_ids` |
| 初始资金 | 数字输入，默认 1,000,000 | 用户输入 |

数据就绪校验：对「所选策略 × 目标频率 × 窗口」调用
`GET /strategy-drafts/{id}/data-status?start&end`，逐条展示 合约×频率 的可用性；
缺数据给「采集所需数据」(`POST /strategy-drafts/{id}:provision`)，就绪后才能开单。

**取舍（已确认）**：③④ 由冻结策略派生、只读确认——冻结代码按特定周期与合约编写，
改动会破坏内容指纹一致性且未必可执行。可自由改的只有 ② 时间窗口 与 初始资金。

### S4 建账户

- `POST /paper/accounts {draft_id, initial_cash}`，绑定冻结草稿，返回账户。
- 成功后跳转 `/paper?account=<id>` 选中新账户查看持仓/订单/成交/净值/对拍。

## 4. API 变化

| 端点 | 变化 |
|---|---|
| `GET /strategy-drafts?state=` | 新增：列出用户的策略草稿（可过滤 FROZEN） |
| `GET /strategy-drafts/{id}` 快照 | 新增 `content_hash` |
| `POST /strategy-drafts/{id}:unfreeze` | 新增：冻结态退回可编辑（清空 content_hash） |
| `POST /strategy-drafts/{id}/messages` | 冻结态返回 409 `STRATEGY_DRAFT_FROZEN`（防篡改） |
| `GET/POST /paper/accounts…` | 前端代理白名单放行 `paper/*` |

## 5. 数据门控与错误修复

- **数据就绪门控（头尾宽限）**：`data-status` 改为「包含 + 头尾各 7 自然日宽限」，
  避免「数据首根 bar 比计划起点晚 1 天」被误判缺失、锁死回测/开单按钮。
- **仿真盘频率扩展**：paper 从 `1d/5m` 扩展到 `1d/5m/15m/30m/60m`
  （poller 聚合 5m 基础粒度 → 目标频率；`_BAR_SUFFIX`/bar_spec/合约频率同步）。
- **频率门控优雅化**：不受支持的频率（如 `1w`）以 409 `PAPER_ACCOUNT_REJECTED`
  明确提示，而非裸 500。
- **生成代码配置类属性拦截**：静态检查 `SomeConfig.attr` 读取并自动纠错重试
  （pydantic 类属性非 `int`，会崩指标构造）。

## 6. 实施状态

- 后端：`strategy_generation` 新增 list/unfreeze/冻结保护；`paper` 扩展频率 + 优雅门控；
  `service.data_status` 头尾宽限；`paper_run_state` 落库 + `run-status` 接口；
  `:start-node` 接口；`load_strategy` 配置类属性兼容。ruff / mypy / 752 测试通过。
- 前端：`/strategy` 已保存策略面板（可点击）、`OpenPaperDialog` 四步流程 + 数据就绪校验、
  `proxy-url` 放行 `paper/*`、`:unfreeze`、`:start-node`、`run-status`；
  `/paper` 节点运行进度区 + 每 5 秒自动轮询 + 账户列表运行绿点 + 启动按钮。
  typecheck / eslint / vitest 通过。
- 端到端：真实浏览器按用户路径走通
  「构建→回测→冻结→开仿真盘四步→建账户→启动节点→进度实跑」，详见 §8。

## 7. 后续（未纳入本轮）

- 若允许「同一份冻结策略在开仿真盘时换周期/换合约」，需改动冻结快照的绑定语义，
  属于更大改动（见 §3 取舍）。
- 开仿真盘的数据窗口：当前对话框默认沿用策略回测方案的历史窗口；仿真节点需要
  「至今」的近期数据才能推进，若策略窗口是历史区间，节点只会在历史 bar 上预热推进，
  且 `对拍回测`（drift）会因窗口错位报「无数据」。后续可让对话框默认把窗口延伸到今天。

## 8. 仿真盘运行进度（本轮新增）

### 背景

早期「运行中」只是账户生命周期态（ACTIVE），`paper-node` 服务默认不启动
（compose `profiles: ["paper"]`），且节点心跳 `PaperMonitor` 是**进程内**状态、
不落库、无接口——导致运维页看不到任何进度，用户以为在跑其实什么都没发生。

### 交互

`/paper` 运维页新增「节点运行进度」区块（每 5 秒自动轮询，无需手动刷新）：

- **节点状态**：运行中（5 分钟心跳窗口内）/ 未运行 / 出错。
- **阶段**：尚未开始 / 预热中 / 实跑（已过预热）。
- **运行周期 / 已推送 K 线 / 最近行情 / 最近错误**。
- 未运行时出现「**启动仿真节点**」按钮（`POST /paper/accounts/{id}:start-node`，
  在 api 容器内以子进程常驻拉起 `scripts/paper-node.py`，仅当未在跑时允许）。
- 账户列表标注运行绿点，并优先自动选中在跑的账户。
- 启动失败（如策略代码无法加载）也会落 ERROR run-state，页面显示「出错 + 原因」，
  不再静默空白。

### 后端支撑

| 端点/表 | 变化 |
|---|---|
| `paper_run_state` 表（迁移 0018） | 节点每周期 upsert：status / cycles_total / bars_total / last_cycle_at / last_bar_at / last_error |
| `GET /paper/accounts/{id}/run-status` | 读 run_state，派生 `node_running`（心跳）、`warmed_up` |
| `POST /paper/accounts/{id}:start-node` | 拉起节点子进程（幂等：已在跑则 409） |
| `PaperMonitor` | 增加 cycles_total / bars_total 计数与公开属性 |
| `scripts/paper-node.py` | `PitStore(sessionmaker(engine))` 修正；启动失败落 ERROR run-state |

### 实跑暴露并修复的节点运行时 bug

1. `scripts/paper-node.py` 用 `PitStore(engine)`（PitStore 期望 `sessionmaker`）→ 修正为
   `PitStore(sessionmaker(engine))`。
2. `markets/nt/data.py` `to_nautilus_bars` 把字符串 instrument 直接传给 `BarType`
   （期望 `InstrumentId`）→ 兼容 `InstrumentId | str`，str 时 `InstrumentId.from_str`。

## 9. 生成代码「配置类属性」缺陷：三层防错（本轮彻底修复）

### 根因

NautilusTrader 的 `StrategyConfig` 是 pydantic 模型，**类属性是 `member_descriptor`**
（返回描述符对象，不是原始值）。旧生成代码写 `SimpleMovingAverage(MyConfig.ma_period)`，
pydantic 类属性访问返回非 int → Cython 构造抛 `TypeError: an integer is required`，
导致策略 init 失败、回测/仿真节点起不来。

### 三层防线

1. **提示词**：明确禁止 `SomeConfig.attr` 读法，要求用整型字面量或 `self.config`。
2. **静态检查**（agent 生成时）：`_static_check` 匹配 `\b[A-Z]\w*Config\.[a-z_]\w*`，
   命中即抛错并触发 agent 自动纠错重试。
3. **加载器兜底**（`load_strategy`，回测/仿真共用）：exec 前把 `SomeConfig.attr`
   正则改写为 `SomeConfig().attr`（配置**实例**上才是真正的值），让已冻结的旧策略
   也能被救活。

### 验证

- 新生成的多指标策略（浏览器端到端）回测成功，无该错误。
- 旧的「黄金 AU2610 双周期」冻结策略（含该缺陷）经加载器兼容后，仿真节点
  从 ERROR 变为 LIVE / 500 根。

## 10. 端到端确认（浏览器，以用户身份）

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | 策略对话选「商品期货」→ 输入多指标策略 → 发送 | agent 生成 |
| 2 | agent 正确指出市场冲突并提出澄清 | 对话澄清正常 |
| 3 | 策略就绪 + 回测方案 | 「已就绪」 |
| 4 | 点「回测」 | 成功，无 `an integer is required` |
| 5 | 点「冻结策略」 | 出现「已冻结」「开仿真盘」 |
| 6 | 点「开仿真盘」→ 四步对话框 + 数据就绪校验 | 数据「可用」，可提交 |
| 7 | 建账户 | 跳转 `/paper` 选中新账户 |
| 8 | 点「启动仿真节点」 | 节点启动 |
| 9 | 节点运行进度（自动刷新） | 运行中 / 实跑 / 周期增长 / 最近行情有值 |
