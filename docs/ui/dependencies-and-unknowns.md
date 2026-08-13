# 前端依赖与未知项

## 已对齐的领域依赖

| 前端能力 | 领域/API 依赖 |
|---|---|
| 任务导航与详情 | `ResearchJob`、研究状态机、异常状态、attempt |
| 市场上下文 | `MarketDefinition`、`InstrumentMaster`、`TradingRuleVersion` |
| brief 与候选 | `ResearchBrief`、`Hypothesis`、`FactorSpec`、候选账本 |
| IR 诊断 | `CompiledIR`、DatasetContract、temporal/type/unit diagnostics |
| 实验监控 | `ExperimentSpec`、`FactorRun`、budget、run fingerprint |
| 验证页面 | `ValidationBundle`、`GateDecision`、ValidationPolicy |
| 报告与追溯 | signed report、`EvidenceRef`、`DatasetSnapshot`、lineage、`Approval` |
| 权限和危险操作 | RBAC/capabilities、separation of duties、`AuditEvent` |

## G0 已冻结的 Control Plane 决策

1. **认证与 actor：** 生产采用 OIDC，服务/测试客户端可使用 Bearer JWT；actor 只从认证主体推导。
2. **授权模型：** capability 必须带 project、market 和 environment scope；对象不可见与不存在使用同一安全 404 语义。
3. **并发控制：** 所有已有聚合的变更使用 ETag/`If-Match`，命令仍携带 Idempotency-Key。
4. **错误合同：** 使用 `application/problem+json`，包含稳定 code、request ID、retryable、current version 和 field errors。
5. **事件恢复：** 事件仅作提示；任何断线重连都必须先 GET snapshot，再恢复依赖新鲜状态的写操作。
6. **状态机：** ResearchJob、ResearchBriefVersion、ExperimentSpec、ExperimentRun、Attempt、Replication、PackageRelease 和 DeploymentRun 分离。
7. **审批：** 预注册、waiver、报告、paper 和 live 是版本绑定的独立 approval；paper 不可替代 live。
8. **报告 ID：** P0 canonical 路径为 `/v1/reports/{report_id}`；报告对象显式包含 experiment spec/run ID。
9. **P0/P1 页面：** P0 截止于可审计研究报告；Alpha Pool、策略、正式回测和 paper/live 可冻结 schema，但真实页面与操作属于 P1。
10. **市场频率：** G0 formal research 只启用 `1d`，`5m` 待许可、数据和 golden set 通过后开放。

详细裁决见 `docs/architecture/g0-contract-baseline.md`。

## P0 已接受的接口基线

以下接口已进入 G0 mock contract，可用于生成类型和 UI mock；后端实现仍按 G1 任务推进：

- `GET /v1/research-jobs`：任务列表和过滤。
- `GET/POST /v1/research-jobs/{job_id}/brief-versions`：brief 版本历史和草稿创建。
- `GET/PATCH /v1/research-brief-versions/{brief_version_id}` 与 `:freeze`：draft 编辑和冻结。
- `GET /v1/research-jobs/{job_id}/candidates`：完整候选账本。
- `GET /v1/experiments/{experiment_id}`：运行、attempt、预算和 heartbeat 快照。
- `GET /v1/reports/{report_id}`：签名报告。
- `GET /v1/approvals` 与 `POST /v1/approvals`：统一审批收件箱和命令。
- `GET /v1/dataset-snapshots/{snapshot_id}` 与 `/v1/rule-snapshots/{snapshot_id}`：不暴露对象存储的元数据查询。
- `GET /v1/events`：授权事件流。
- `POST /v1/runs/{run_id}:retry` 与 `:cancel`：显式长任务命令。
- `GET /v1/session`：actor、roles、capabilities、environment 和 market scope。

## 仍需后端在 G1 冻结

- OIDC provider、token lifetime、session timeout、MFA 和 live reauthentication 的具体实现。
- capability 名称表、scope 表达式和 policy decision ID 格式。
- SSE envelope、sequence、保留期和 outbox/inbox 的持久化实现。
- 各资源 freshness TTL、heartbeat timeout 和 stale 后允许动作矩阵。
- 可取消阶段、自动重试上限和 operation 查询接口。
- schema deprecation 周期、客户端兼容窗口和事件 replay 工具。

## 需要产品/设计确认

- 默认首页是“我的研究”还是“待办概览”；当前按角色自适应概览设计。
- ResearchJob 创建是否允许草稿；本设计假设允许本地/服务端草稿，但提交才创建正式状态。
- 移动端是否允许批准高风险 waiver；当前允许查看和拒绝，批准可由 policy 配置为桌面限定。
- 报告签名失败时是否允许导出带水印副本；当前默认允许只读查看，禁止作为正式报告导出。
- 中文/英文术语、时区默认值和数值格式尚未形成产品词汇表。

## 外部硬阻断

- 正式数据供应商、许可、PIT/修订和历史 universe 尚未完成 RFI 与 golden set。
- broker、CTP 生产参数、账户权限和程序化交易要求尚未批准。
- paper/live 环境、凭证、双人审批人和运行主机尚未批准。
- 上述阻断不影响 G1 契约、数据 harness 和 UI vertical slice 开发，但阻止 formal 数据源晋级以及任何 paper/live 发布。

## 建立 Next.js 壳层的入口条件

满足以下条件后再创建 `frontend/`：

- 包管理器、Node LTS、Next.js 版本和部署目标确定。
- 认证/session contract 与至少一个 P0 read endpoint 冻结。
- OpenAPI schema 可生成 TypeScript 类型。
- mock server 方案、测试框架和 CI 命令确定。
- 设计 token、字体许可和图表库完成最小选型。

届时壳层仅应包含 layout、路由、session/provider、API client、mock server、状态组件和一条 ResearchJob vertical slice，不实现后端裁决逻辑。
