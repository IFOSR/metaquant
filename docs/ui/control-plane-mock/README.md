# Control Plane Mock Contract

`openapi.yaml` 是已通过 Gate G0 的 contract-first 基线。后端实现和前端生成类型必须以该 schema 为共同输入；未实现端点仍不代表运行时已经可用。来源分为：

- `x-source: technical-design`：源方案已明确列出的端点。
- `x-source: integrated-design`：综合方案已明确、但详细技术方案未沿用同一路径的端点。
- `x-source: frontend-proposal`：P0 页面需要、但源方案尚未定义的查询或命令端点。
- `x-source: g0-contract-baseline`：Gate G0 为解决架构、安全或版本问题新增的权威契约。

## Fixtures

| 文件 | 场景 |
|---|---|
| `examples/research-job.json` | 商品期货 ResearchJob 的长任务快照 |
| `examples/research-job-events.json` | 事件流断开重连后的增量事件列表 |
| `examples/research-report.json` | 可验证签名报告和 lineage 摘要 |
| `examples/problem.json` | stale version / 并发冲突错误 |

## Mock 约定

- 所有时间均为 RFC 3339，并显式包含时区。
- 所有写命令返回 `202 Accepted`，长任务不在 API 请求内执行。
- 所有写命令要求 `Idempotency-Key`；修改已有聚合还要求 `If-Match`。
- body 不接受 `actor`；actor 由 OIDC/Bearer 认证主体推导。命令 metadata 包含 `reason`、`parent_artifact_id`、`budget` 和 `schema_version`。
- `capabilities` 和 `allowed_actions` 由服务端返回，前端不得从角色名自行推导。
- 事件只用于增量刷新；断线后必须重新 GET 资源 snapshot。
- formal research 开放 `1d` 与分钟级频率（`1m/5m/15m/30m/60m`）；商品期货创建必须声明 exchange、实际合约、settlement clock 和 roll policy。
- fixture 中的指标、hash、签名和 ID 均为虚构数据，不能用于研究结论。

## 建议的本地 mock 方式

在 Next.js 壳层建立后，可使用支持 OpenAPI 的 mock server：

```bash
npx --yes @stoplight/prism-cli mock docs/ui/control-plane-mock/openapi.yaml
```

当前仓库未固定 Node 工具链，因此该命令是可选运行方式，不写入项目依赖。

契约语义测试已纳入 `pytest`，覆盖重复 YAML key、认证、actor、幂等/并发、状态机、市场约束、provenance、策略包 attestation 和重连恢复。
