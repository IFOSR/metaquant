# G0 产品交互与前端信息架构

**版本：** v0.1

**日期：** 2026-08-11

**范围：** G0 信息架构与 P0/P1 页面边界，不实现后端裁决、因子计算或交易执行

## 1. 设计原则

1. **研究证据优先。** 结论旁必须能看见状态、口径、快照、政策版本和 lineage，不以单一收益数字替代证据。
2. **状态机是主线。** 页面只发起命令并展示服务端状态，不在客户端推导或修改研究状态。
3. **市场与环境显式。** `CN_A`、`CN_COMMODITY_FUTURES` 以及 research、paper、live 始终可见且不可混用默认值。
4. **危险操作慢下来。** 审批、waiver、lockbox、发布和 kill switch 使用独立流程、明确后果和追加式审计。
5. **长任务可离开。** 运行页显示阶段、预算、最后心跳和恢复入口；用户离开页面不会中断任务。
6. **只读降级优先。** 事件流中断或数据过期时保留最后成功快照，但禁止依赖新鲜状态的写操作。

## 2. 用户角色到核心任务

| 角色 | 核心任务 | 默认首页 | P0 权限边界 | P1 扩展 |
|---|---|---|---|---|
| `Researcher` | 创建 ResearchJob、填写 ResearchBrief、检查候选和个人实验、阅读报告 | 我的研究 | 创建/查看本人任务；提交预注册；不能自批 waiver/晋级 | 论文复现、研究委员会 |
| `StrategyResearcher` | 比较已通过因子、构建 StrategySpec、查看正式回测 | 因子验证 | P0 只读因子与报告 | Alpha Pool、组合、回测 |
| `ResearchLead` | 审批预注册、waiver、Alpha Pool 晋级和报告结论 | 待我审批 | 审批研究节点；必须填写理由 | 策略包和发布审批 |
| `ExecutionOperator` | 监控 shadow/paper/live、订单、成交、对账和应急操作 | 运行监控 | P0 仅查看研究产物 | 发布、kill switch、恢复 |
| `RiskReviewer` | 审查成本、容量、暴露、尾部风险和规则约束 | 风险审查 | 读取验证和 lineage；可提出阻断意见 | paper/live 风险签核 |
| `DataSteward` | 维护数据合同、许可、PIT 规则、快照质量 | 数据与规则 | 查看字段、快照和时间依赖；处理数据阻断 | 规则版本和质量政策 |
| `PlatformAdmin` | 用户、角色、资源、provider、环境和审计 | 平台状态 | RBAC、资源和审计；不替代业务审批人 | 全环境运维 |

权限展示规则：

- 隐藏完全无权访问的主导航；对可见但无权执行的动作保留只读入口并解释所需角色。
- 对象级权限由 API 返回，不能仅依赖角色名称推断。
- 同一人不得批准自己提交的 waiver、lockbox 或 live 发布；UI 必须展示职责冲突原因。
- `live` 环境使用独立视觉标识、域名/路由前缀和重新认证，不能只靠颜色区分。

## 3. 导航与上下文

### 3.1 全局壳层

桌面端从左到右、从上到下：

1. 产品标识与当前环境：`RESEARCH` / `PAPER` / `LIVE`。
2. 市场域选择器：`CN_A` / `CN_COMMODITY_FUTURES`；切换前检查未保存表单。
3. 全局搜索：ResearchJob、factor version、run、report、artifact ID。
4. 任务中心：正在运行、等待输入、审批、失败和已完成。
5. 审批收件箱、审计入口、帮助和用户菜单。
6. 主导航与页面内容。

移动端保留环境、市场和任务状态；主导航收进抽屉。危险操作不放在底部固定快捷栏。

### 3.2 主导航

```text
概览
研究
  研究任务
  新建研究
因子
  因子注册表
  验证与门禁
报告
审批
数据与规则
审计
策略与回测             [P1]
运行                   [P1: shadow / paper / live]
平台管理               [PlatformAdmin]
```

### 3.3 页面地图与边界

| 页面 ID | 页面/路由建议 | 优先级 | 主要角色 | 页面责任 | 明确不做 |
|---|---|---|---|---|---|
| SH-01 | `/` | P0 | 全部 | 个人任务、阻断、审批和系统健康摘要 | 跨用户利润排行榜 |
| RJ-01 | `/research/jobs` | P0 | Researcher/Lead | 搜索、筛选、分页、状态和预算摘要 | 客户端聚合真实状态 |
| RJ-02 | `/research/jobs/new` | P0 | Researcher | 创建 job、市场/时钟/universe/预算 | 自动补齐缺失市场规则 |
| RJ-03 | `/research/jobs/{id}` | P0 | 研究相关角色 | 状态时间线、brief、候选、run、审批、报告入口 | 直接修改状态 |
| RB-01 | `/research/jobs/{id}/brief` | P0 | Researcher | 假设、机制、反证、数据域、约束 | 自由执行代码 |
| CA-01 | `/research/jobs/{id}/candidates` | P0 | Researcher/Lead | 全量候选、重复/拒绝/超预算原因 | 只展示胜出候选 |
| FA-01 | `/factors/{factorId}/versions/{version}` | P0 | Research/Risk/Data | IR、编译诊断、字段、单位、时间依赖 | 浏览器执行 IR |
| EX-01 | `/experiments/{id}` | P0 | Research/Risk/Lead | 预注册、attempt、预算、运行监控 | 原地覆盖失败 attempt |
| VA-01 | `/experiments/{id}/validation` | P0 | Research/Risk/Lead | Gate 0-5、OOS、成本、容量、风险、决策 | 客户端计算 GateDecision |
| RP-01 | `/reports/{id}` | P0 | 授权角色 | 结论、指标、限制、签名状态、证据和 lineage | 把 exploratory 结果标成正式 |
| LN-01 | `/lineage/{artifactId}` | P0 | 授权角色 | 上下游 artifact、hash、版本、审批 | 直接读取对象存储 |
| AP-01 | `/approvals` | P0 | 审批角色 | 待办、历史、职责冲突、理由和 diff | 批量无理由审批 |
| DR-01 | `/data` | P0 | DataSteward/研究只读 | DatasetContract、Snapshot、RuleSnapshot | 编辑原始数据 |
| AU-01 | `/audit` | P0 | Admin/Lead/Risk | 追加式审计查询和导出 | 修改/删除事件 |
| AL-01 | `/alpha-pool` | P1 | StrategyResearcher/Lead | 已晋级 factor version | 手工绕过 Gate |
| ST-01 | `/strategies/{id}` | P1 | StrategyResearcher | StrategySpec、约束和版本 | 接收未晋级因子 |
| BT-01 | `/backtests/{id}` | P1 | Strategy/Risk | 正式回测、归因、对拍、账本 | 把探索回测当正式回测 |
| OP-01 | `/operations/{env}` | P1 | Execution/Risk | shadow/paper/live 运行态 | P0 开放交易操作 |
| KS-01 | `/operations/live/kill-switch` | P1 | ExecutionOperator | kill switch、影响范围、恢复流程 | 单击立即执行 |

P0 结束于“可审计研究报告”。Alpha Pool、策略构建、正式回测和任何 paper/live 操作均为 P1；P0 可展示禁用入口和依赖说明，但不提供伪实现。

## 4. ResearchJob 到报告的 P0 用户流程

### 4.1 主流程

| 步骤 | 用户动作 | 系统反馈 | 完成条件 | 恢复/阻断 |
|---|---|---|---|---|
| 1. 建立任务 | 选择市场、universe、频率、时钟、horizon、预算 | 即时校验市场隔离与必填项 | `ResearchJob=DRAFT` | 字段未知时保留草稿，不进入运行 |
| 2. 填写 brief | 创建/修订 `ResearchBriefVersion` | 结构化预览、版本和变更摘要 | brief 为 `DRAFT` | frozen 版本不可覆盖 |
| 3. 冻结 brief | 确认假设、机制、方向、反证、数据域与约束 | 展示冻结 diff 和 content hash | brief 为 `FROZEN`，job 可进入 `READY` | 修改必须创建新版本 |
| 4. 数据可行性 | 查看字段覆盖、许可、available-time、Dataset/RuleSet 快照 | 风险按字段定位，支持 DataSteward 跳转 | 正式引用均为 `SEALED` | 缺许可/规则时 job 为 `BLOCKED_POLICY` |
| 5. 生成候选 | 提交 propose 命令并离开页面 | job 为 `RUNNING`，显示预算和最后心跳 | 候选账本生成 | adapter 失败可降级人工候选 |
| 6. 审查候选 | 查看全部候选及重复、拒绝、超预算记录 | 方向、lookback、公式、输入和失败条件并排 | 候选集合确认 | 不允许删除失败候选 |
| 7. 编译 IR | 触发编译，查看逐字段/逐节点诊断 | 错误定位到表达式和时间依赖 | 新 `FactorVersion=COMPILED` | 修订生成新版本 |
| 8. 预注册 | 确认候选、主指标、OOS、embargo、预算和快照 | 展示冻结前后 diff | `ExperimentSpec=PREREGISTERED` | 关键变更创建新 spec |
| 9. 预注册审批 | Lead 审查 spec、职责冲突和证据 | 审批绑定 spec 版本和 hash | approval 通过 | 未批准不得创建 formal run |
| 10. 运行验证 | 启动 `ExperimentRun`，监控 attempt、预算和 gates | 事件提示 + 定期 GET snapshot | run 为 `SUCCEEDED` 或明确失败终态 | retry 创建新 attempt |
| 11. 裁决与报告 | Lead/Risk 查看 GateDecision、异常和 waiver，生成签名报告 | 每项结论可定位证据、代码、镜像、政策和审批 | 报告为 `SIGNED` | `QUARANTINED/NON_REPRODUCIBLE` 阻断批准 |
| 12. 结案 | 将研究任务标记成功、失败、取消或归档 | 记录服务端 actor、reason、版本和时间 | job 为 `SUCCEEDED/FAILED/CANCELLED/ARCHIVED` | 不等同于 P1 paper/live 发布 |

### 4.2 页面内部结构

`RJ-03` 使用稳定的任务页骨架：

```text
标题 / 市场 / 状态 / owner / 最后更新
阻断或 stale 横幅
步骤导航：Brief → Candidates → Factor IR → Experiment → Validation → Report
主内容
右侧上下文：预算、snapshot、policy、run fingerprint、审批
底部审计时间线
```

移动端按“状态与阻断 → 当前步骤 → 关键指标 → 证据 → 审计”单列排列，侧栏改为可展开摘要。

## 5. 页面状态矩阵

| 状态 | 触发 | 页面表现 | 允许动作 | 禁止/审计 |
|---|---|---|---|---|
| `loading` | 首次请求未完成 | 保留页面骨架；表格用固定列 skeleton；显示加载对象 | 返回、取消本地导航 | 不显示伪造 0 值；超过 10 秒转 long-running 提示 |
| `empty` | 请求成功且集合为空 | 解释“没有数据”的原因和前置条件 | 有权限时显示单一主 CTA | 不把无权限伪装为空 |
| `error` | 请求失败或 contract 不兼容 | problem code、可读原因、request ID、最后成功时间 | retryable 才显示重试；支持复制诊断 | 写请求不得自动重复，除非使用同一 Idempotency-Key |
| `permission denied` | API 返回 403/对象级拒绝 | 显示缺少的 capability、资源范围和申请路径 | 返回、申请访问、查看自己的审计请求 | 不泄露对象敏感字段或“对象是否存在” |
| `stale` | 超过资源 TTL、事件流断开或版本落后 | 顶部 persistent banner；数据标记 `as_of` | 刷新、查看最后快照；纯只读浏览 | 禁用审批、发布、重试等依赖新鲜状态的写操作 |
| `long-running` | 服务端任务运行且超过页面阈值 | 阶段、已用/剩余预算、started_at、heartbeat、attempt | 离开页面、订阅通知、有权限时请求取消 | 不使用无限 spinner；取消必须显示影响范围 |
| `waiting input` | `WAITING_INPUT` | 列出缺失字段和责任人 | 补充输入、指派 | 补充后生成新版本和 diff |
| `blocked policy` | `BLOCKED_POLICY` | 明确阻断政策、市场、版本和证据 | 请求 waiver、联系 DataSteward | 不提供“仍然运行”按钮 |
| `retryable failure` | `ExperimentRun=FAILED_RETRYABLE` | attempt、错误阶段和自动重试计数 | 使用相同输入创建新 attempt | 不覆盖旧 attempt |
| `terminal failure` | `ExperimentRun=FAILED_TERMINAL` | 根因、受影响 artifact、建议修复 | 创建新 spec/run 或归档 job | 禁止原地倒退状态 |
| `quarantined` | `ExperimentRun=QUARANTINED` | 高显著异常警示和隔离原因 | 进入调查清单 | 禁止晋级、报告批准和导出策略 |
| `non-reproducible` | `ExperimentRun=NON_REPRODUCIBLE` | 并排显示期望/实际 fingerprint 和 artifact | 发起调查 | 阻断任何发布链路 |

每种状态必须具有：图标、文本标签、可读说明和机器状态码；颜色只作为辅助。表格行、详情页、任务中心和通知使用同一术语。

## 6. 审批与危险操作

### 6.1 通用审批抽屉

审批操作不使用普通确认弹窗，而使用包含以下内容的独立抽屉/页面：

- 对象名称、不可变版本、市场域、环境和当前状态。
- 提交者、审批者资格、职责冲突检查和所需审批数。
- 前后 diff、受影响 artifact 和下游影响范围。
- 数据快照、规则/政策版本、run fingerprint 和最后更新时间。
- 必填理由、可选证据引用、waiver 到期时间。
- 明确的“批准”“拒绝”“要求修改”动作；关闭抽屉不产生状态变更。

### 6.2 操作等级

| 等级 | 示例 | 交互要求 |
|---|---|---|
| 常规写操作 | 保存 brief 草稿、创建过滤器 | 明确保存状态；可撤销时提供撤销 |
| 受控操作 | 预注册、重试、取消运行、归档 | 显示 diff/影响；必填 reason；Idempotency-Key |
| 高风险审批 | gate waiver、打开 lockbox、Alpha Pool 晋级 | 二次确认、职责分离、对象版本校验、到期/范围 |
| 生产危险操作 | publish live、kill switch、恢复交易 | P1；重新认证/MFA、双人审批、typed confirmation、演练链接、不可复用旧确认 |

具体规则：

- **重试：** 仅对 `FAILED_RETRYABLE` 开放，创建新 attempt；按钮文字为“创建重试 attempt”，不是“重新运行”。
- **取消：** 展示当前阶段、可能遗留 artifact 和不可取消区间；取消结果为 `CANCELLED`，不删除历史。
- **waiver：** 必填政策、范围、理由、补偿控制、到期时间和审批人；过期后自动失效。
- **lockbox：** 先展示会暴露的数据范围和对研究有效性的影响；打开后不可“回到未看过”状态。
- **报告批准：** 只批准当前报告版本和 manifest hash；新版本自动失去旧批准状态。
- **live/kill switch：** G0 仅定义交互，P0 不实现入口；P1 必须从新鲜执行状态发起。

## 7. 数据呈现规范

- 指标卡同时显示值、单位、样本区间、OOS/IS、gross/net、基准和数据时间。
- Gate 结果按 Gate 0-5 排列，每项显示 `PASS/FAIL/WARN/WAIVED/NOT_RUN`、政策阈值和证据链接。
- `CN_A` 默认突出 Rank IC、分层、换手、容量、暴露、T+1 和不可成交。
- `CN_COMMODITY_FUTURES` 默认突出时序收益、换月稳定性、保证金、结算、杠杆、合约流动性和极端行情。
- 图表必须有文本摘要、可下载表格和异常点清单；tooltip 不是获取关键值的唯一方式。
- 所有 hash 使用短格式展示、完整值可复制；所有时间展示时区并支持查看原始 UTC。
- exploratory、formal、paper proxy 和 live actual 使用文字标签，不仅依靠颜色或位置。

## 8. 响应式与可访问性

### 8.1 桌面

- 支持 1280px 以上双栏研究工作台；关键表格可横向滚动并冻结标识列。
- 主要内容最大阅读宽度约 1440px；报告正文控制行长，图表可突破正文宽度。
- 密集表格提供列管理、过滤器摘要和可复制稳定 URL。

### 8.2 移动

- 360px 起可完成：查看任务状态、处理等待输入、阅读报告摘要、查看审批详情和拒绝审批。
- 新建 ResearchJob 使用分步表单和断点续填；复杂 IR 编辑、宽表分析和 live 危险操作提示转桌面完成。
- 表格降级为优先字段卡片，不用缩小字体塞入所有列。
- 最小触控目标 44×44 CSS px，底部安全区不遮挡操作。

### 8.3 可访问性

- 目标 WCAG 2.2 AA；语义标题、landmark、表头和表单 label 完整。
- 所有关键流程可键盘完成；焦点顺序与视觉顺序一致，焦点样式清晰。
- 状态更新通过适当的 `aria-live` 通知，但高频运行事件聚合后播报。
- 错误摘要置于表单顶部并链接到具体字段；不能只用红色边框。
- 图表提供同数据表和 2-4 句文本结论；趋势、阈值和异常点可被屏幕阅读器获取。
- 支持 200% zoom、reduced motion、高对比度和不依赖 hover 的操作。
- 自动刷新默认不抢焦点；用户可暂停事件更新并查看“有 N 条新事件”。

## 9. 前端技术边界

- 只调用 Control Plane API、查询 API 和授权事件流；禁止直连 PostgreSQL、对象存储、Dagster 或 broker。
- 服务端返回状态、capabilities、门禁结论、风险结论和 freshness；前端只负责呈现与发命令。
- 所有写请求携带 `Idempotency-Key`；已有聚合的变更还必须携带 `If-Match`。body 只包含 reason、`parent_artifact_id`、budget 和 `schema_version`，actor 由认证会话注入。
- API contract 生成类型；fixture 仅用于 UI 开发，不能成为正式业务规则来源。
- 缓存 key 至少包含 environment、market、actor scope、resource ID 和 version。
- 事件流只用于增量提示；页面恢复、重连和最终一致性以 GET snapshot 为准。

## 10. G0 视觉 token 与共用组件

视觉方向采用“审计工作台”而非交易大屏：高信息密度、稳定排版、少量语义色和清晰证据层级。首版 token 只冻结语义，不绑定具体品牌色：

- `surface/base`、`surface/raised`、`surface/inset` 区分页面、卡片和代码/证据区。
- `text/primary`、`text/secondary`、`text/muted`、`text/inverse` 满足 AA 对比度。
- `status/pass`、`status/fail`、`status/warn`、`status/info`、`status/stale` 必须同时配图标和文字。
- 间距以 4px 基线递增；正文最小 16px，密集表格最小 14px；代码、hash 和数值使用等宽字体。
- 动效只用于阶段切换、增量事件和抽屉进入；reduced motion 下移除位移和连续动画。

G0 共用组件：

- `EnvironmentBadge`、`MarketBadge`、`FreshnessBanner`、`StatusChip`。
- `TaskProgress`、`BudgetMeter`、`AttemptTimeline`、`BlockerPanel`。
- `GateMatrix`、`MetricWithContext`、`EvidenceLink`、`LineageSummary`。
- `ApprovalDrawer`、`VersionDiff`、`DangerConfirmation`、`AuditTimeline`。
- `StateBoundary` 统一承载 loading、empty、error、permission、stale 和 long-running。
