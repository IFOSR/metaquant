# G0 前端产品与交互设计

本目录是量化研究平台 Gate G0 的产品交互与前端契约交付物。其最终裁决同时受 `docs/architecture/g0-contract-baseline.md` 约束。

- `doc/quant-platform-prd.md`
- `doc/integrated-quant-pipeline-design.md`
- `doc/quant-platform-technical-design.md`（任务中所称 `technical-design.md`）

## 交付物

| 文件 | 用途 |
|---|---|
| [g0-product-ux-spec.md](./g0-product-ux-spec.md) | 角色任务、导航、页面地图、P0 流程、状态矩阵和交互规范 |
| [page-acceptance-checklist.md](./page-acceptance-checklist.md) | 页面级验收清单 |
| [dependencies-and-unknowns.md](./dependencies-and-unknowns.md) | API、权限和领域模型依赖及未决项 |
| [control-plane-mock/](./control-plane-mock/) | Control Plane OpenAPI mock contract 和 JSON fixtures |

## 本阶段决策

- G0 不创建 Next.js 工程，避免在 Node/部署目标和 OIDC provider 尚未选型时固化实现依赖。
- 信息架构、页面边界、状态行为、OIDC/Bearer 安全边界和 contract-first 数据接口已冻结。
- G1 可直接以 `control-plane-mock/openapi.yaml` 生成类型，并实现 session + ResearchJob vertical slice。

## G1 最小可运行工作台

`frontend/` 是 G1-004 的 mock-driven Next.js App Router 纵切：

- `npm install`：安装前端依赖。
- `npm run dev`：启动本地工作台。
- `npm run lint`：运行 ESLint/Next 规则。
- `npm run typecheck`：运行严格 TypeScript 检查。
- `npm test`：运行 Vitest + Testing Library 契约测试。
- `npm run build`：验证生产构建。

前端通过 `frontend/lib/api.ts` 的 `QuantApiClient` 统一访问控制面。
`mock-client.ts` 提供确定性本地 adapter，`HttpQuantApiClient` 提供真实 HTTP
adapter；页面和组件不得直接依赖某个 adapter，也不直连 PostgreSQL、MinIO、
编排器或 broker。`session.capabilities` 仍是导航和操作边界的来源。

界面文案集中在 `frontend/lib/i18n.ts`（中/英双词典，`MessageKey` 类型保证
两语言 key 一致）；client 组件用 `useI18n()`，server 组件用
`lib/server-locale.ts` 的 `getServerT()`。语言选择存于 `quant_locale`
cookie，顶栏可切换中/英文，缺省中文。

首页、ResearchJob 列表/创建/详情、Brief draft/freeze 已实现。formal research
开放 `1d` 与全部分钟级频率（`1m/5m/15m/30m/60m`）；商品期货创建强制交易所、
实际合约、结算时钟和不可变 roll policy。环境可选 RESEARCH / PAPER / LIVE；
本地演示身份拥有全部环境与能力。
360px 起支持状态查看、表单完成和 brief 编辑；状态组件覆盖 loading、empty、
error、permission、stale、long-running 的统一呈现约定。

## G2 真实 API 模式

默认启动使用 mock adapter。连接本地 Compose API 时设置：

```bash
NEXT_PUBLIC_QUANT_API_MODE=http \
QUANT_API_UPSTREAM_URL=http://localhost:8000 \
QUANT_API_ACCESS_TOKEN=local-researcher \
npm run dev
```

浏览器统一访问同源 `/api/quant/v1`，Next.js 服务端代理通过非公开环境变量注入
Bearer token，因此不要求后端开放 CORS，也不会把 token 打入浏览器 bundle。
这个 shared static-token 代理是 **localhost-only 的单用户本地演示能力**：
请求的 `Host`、`X-Forwarded-Host` 以及 `Forwarded host=`（如存在）必须全部是
`localhost`、`127.0.0.0/8` 或 `::1`，否则代理返回 403。不得通过反向代理、
端口转发、局域网地址或公网域名暴露该 Next.js 服务。
Server Components 使用相同的非公开环境变量直接访问上游 `/v1`，避免 Node
运行时请求相对 URL。
HTTP adapter 的写操作生成 `Idempotency-Key`，用服务端 `ETag` 或资源版本发送
强 `If-Match`，并把 `application/problem+json` 解析为 `QuantApiProblem`。
命令接口返回 receipt 后，客户端按 `resource_id` 重新 GET 权威快照；
snake_case DTO 通过显式 mapper 转换为 UI camelCase 类型。

`QUANT_API_ACCESS_TOKEN` 是所有访问者共享的服务端身份，只允许单用户 localhost
演示，不能提供真实用户会话、租户隔离或可归责审计。生产 OIDC issuer、token
broker、PAPER/LIVE capability 均未批准，不得使用该变量承载生产凭据。

## 查看与校验

文档无需构建即可查看。JSON fixture 可执行：

```bash
find docs/ui/control-plane-mock/examples -name '*.json' -print0 \
  | xargs -0 -n1 python3 -m json.tool >/dev/null
```

若本地安装了 `npx`，可选执行 OpenAPI lint：

```bash
npx --yes @redocly/cli lint docs/ui/control-plane-mock/openapi.yaml
```

后续前端启动命令尚未定义；建立 Next.js 壳层后应在本文件补充 `install`、`dev`、`test`、`lint`、`typecheck` 和 mock server 命令。
