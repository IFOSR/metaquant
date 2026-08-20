# Quant Research Platform

量化研究与交易平台的后端工程基线。当前 G0 只提供可复现的本地运行环境、
健康检查和数据库迁移入口，不包含 Factor IR 或量化业务逻辑。

## 本地依赖

- Docker Desktop 或兼容的 Docker Engine
- Docker Compose v2
- `make`

PostgreSQL 和 MinIO 均由 Docker Compose 管理。不要在宿主机安装或初始化
PostgreSQL。

## 启动

进项目目录后，一条命令启动全部（Docker 检查 → 后端 → 前端）：

```bash
./quant
```

子命令：`up`（默认，全部）、`backend`（只后端）、`frontend`（只前端）、
`down`（停止后端，保留数据）、`reset`（删除数据）、`status`、`logs`。

等价的手动方式：

```bash
make bootstrap
make up
curl --fail http://localhost:8091/health/live
curl --fail http://localhost:8091/health/ready
```

默认端口：

| 服务 | 地址 |
|---|---|
| 前端 UI | `http://localhost:3090` |
| API/OpenAPI | `http://localhost:8091/docs` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:55432` |

后端访问令牌（本地开发）：`local-researcher`。

`.env.example` 中的密码仅用于本地开发。执行 `make bootstrap` 后可在未跟踪的
`.env` 中修改。

## 数据库迁移

首次 `make up` 会在 PostgreSQL 健康后自动运行：

```bash
alembic upgrade head
```

手工重跑迁移：

```bash
make migrate
docker compose run --rm migrate alembic current
```

应用使用非超级用户 `quant_app`。PostgreSQL 数据保存在 Compose named volume
`postgres_data`，不会写入容器临时文件系统。

## 因子构建（研报 → 可执行模型）

从研报中挖掘深度学习因子：agent 抽取构建规格 → 生成 model/train/infer 代码 →
沙箱训练/推理 → 因子值 → IC 验证。

前提：后端镜像含 CPU 版 PyTorch（默认 `INSTALL_TORCH=true`），并配置了
DeepSeek/Zhipu 的 agent 后端（`.env` 中的 `DEEPSEEK_API_KEY` 或 `ZHIPU_API_KEY`）。

```bash
# 构建/验证 torch 沙箱（含一个真实 torch 训练→推理→IC 的 smoke）
make sandbox-verify

# 用真实 PIT 数据（pit_observations）跑通 torch 全链路
docker compose run --rm --no-deps api python scripts/verify-real-torch.py
```

前端入口：研究任务详情页的「因子构建」链接，或直接访问
`http://localhost:3090/research/jobs/<job-id>/factor-build`，按 8 步走
「抽取规格 → 生成代码 → 试运行 → 冻结规格 → 注册代码包 → 训练 → 推理 → 验证」。

隔离方式：本地默认用子进程沙箱（AST 安全扫描 + 资源限制）；生产多租户设置
`SANDBOX_USE_DOCKER=true`（`docker/sandbox/Dockerfile` 构建的隔离镜像，
`--network=none` + 只读根文件系统）。

## 工程检查

```bash
make check
```

该命令在 Python 3.12 应用镜像中执行 Ruff 格式检查、Ruff lint、严格 mypy
和 pytest，宿主机无需安装 Python 依赖。

G3 的真实 PostgreSQL/MinIO 门禁使用临时数据库，不修改开发数据库：

```bash
make g3-integration
```

该命令验证迁移 `upgrade -> downgrade -> upgrade`、同 fingerprint 并发运行
幂等性，以及 MinIO 内容地址的 put/get/stat/hash 往返。

## 常用运维

```bash
make logs
make down
make reset
```

`make down` 保留数据；`make reset` 会删除所有本地 named volumes，必须只在
确认不需要本地数据时使用。

架构和产品边界见 `doc/quant-platform-prd.md`、
`doc/integrated-quant-pipeline-design.md` 和
`doc/quant-platform-technical-design.md`。
