# G0 页面验收清单

## 全局壳层

- [ ] 当前 environment 和 market 始终可见，切换不会丢失未保存内容。
- [ ] 导航按 capability 裁剪；无权动作显示原因而非静默失败。
- [ ] 全局任务中心覆盖运行中、等待输入、阻断、审批、失败和完成。
- [ ] research、paper、live 不能仅以颜色区分。
- [ ] 断网或事件流中断时保留最后成功快照并进入 stale。

## ResearchJob 列表与创建

- [ ] 列表可按 market、owner、state、updated time 和 blocker 筛选。
- [ ] 创建表单只允许已启用的 `CN_A` 或 `CN_COMMODITY_FUTURES`。
- [ ] G0 formal research 只允许 `1d`；`5m` 显示为未启用能力而不是可提交选项。
- [ ] 商品期货必须填写 exchange scope、实际合约选择、settlement clock 和不可变 roll policy。
- [ ] market 切换会清空或重新验证 universe、时钟、成本和规则字段。
- [ ] draft 与 submitted 状态清楚；重复提交使用同一 Idempotency-Key。
- [ ] 必填错误、许可错误和政策阻断具有不同文案与恢复动作。

## ResearchJob 详情与候选

- [ ] 状态时间线与服务端状态一致，不由客户端推断。
- [ ] ResearchJob、ExperimentSpec、ExperimentRun 和 Attempt 使用各自状态机，不复用一个大状态枚举。
- [ ] 页面显示预算、attempt、最后心跳、snapshot、policy 和 fingerprint。
- [ ] 成功、失败、重复、拒绝和超预算候选均可查。
- [ ] adapter 不可用时保留人工 Factor IR 主路径。
- [ ] 长任务可离开页面，回来后通过 snapshot 恢复。

## Factor IR 与实验

- [ ] IR 展示公式、输入、单位、lookback、市场和时间依赖。
- [ ] 编译错误能定位到字段/AST 节点，并区分 type、unit、temporal、policy。
- [ ] 修订生成新版本，不覆盖已引用版本。
- [ ] 预注册展示 OOS、embargo、主指标、候选集合和冻结 diff。
- [ ] retry 创建新 attempt，旧 attempt 和错误仍可查看。

## 验证、门禁与报告

- [ ] Gate 0-5 显示状态、政策阈值、实际值和证据。
- [ ] OOS/IS、gross/net、market-specific 指标不会混淆。
- [ ] `QUARANTINED`、`NON_REPRODUCIBLE` 阻断批准和导出。
- [ ] 报告中的结论可跳转 factor version、snapshot、rule、code、image、approval 和 evidence。
- [ ] EvidenceRef 支持 artifact hash 以及 PDF page/bbox、数据行或 metric path 定位。
- [ ] manifest hash/签名不可验证时有显著警示。

## 审批与危险操作

- [ ] 审批展示对象版本、diff、影响、提交者和职责冲突。
- [ ] reason 必填并进入 audit；关闭审批面板不提交。
- [ ] waiver 具备范围、补偿控制和到期时间。
- [ ] lockbox 提示不可逆的信息暴露。
- [ ] P0 不提供 paper/live/kill switch 的可执行伪入口。

## 状态、响应式与可访问性

- [ ] 每个 P0 页面覆盖 loading、empty、error、permission、stale、long-running。
- [ ] 错误显示稳定 problem code 和 request ID；不可安全重试的写请求不显示普通重试。
- [ ] 360px 可查看状态、阻断和报告摘要；宽表降级为卡片/优先列。
- [ ] 键盘可完成关键流程，焦点不被自动刷新抢走。
- [ ] 图表有文本摘要和数据表，颜色不是唯一状态编码。
- [ ] 200% zoom、reduced motion 和屏幕阅读器基本流程通过。

## Contract 验收

- [ ] P0 页面只依赖 `docs/ui/control-plane-mock/openapi.yaml` 定义的 Control Plane 接口。
- [ ] 所有写接口包含 Idempotency-Key；修改已有聚合还包含 If-Match。
- [ ] actor 只从认证主体获得，命令 body 不接受客户端 actor。
- [ ] 命令 body 包含 reason、parent artifact、budget 和 schema version。
- [ ] 403 不泄露敏感对象存在性；409 能表达 stale version/职责冲突。
- [ ] 事件流断开后通过 GET snapshot 恢复，不依赖事件历史作为唯一真相源。
- [ ] StrategyPackage payload 不含 approved/status；paper/live 通过独立 attestation 表达。
- [ ] live approval 与 paper approval 分离，并要求两个不同 actor 和职责分离。
- [ ] 前端不直连数据库、对象存储、编排器或 broker。
