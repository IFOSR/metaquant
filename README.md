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

```bash
make bootstrap
make up
docker compose ps
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
```

默认端口：

| 服务 | 地址 |
|---|---|
| API/OpenAPI | `http://localhost:8000/docs` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| PostgreSQL | `localhost:55432` |

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

## 可选服务

Dagster 和 MLflow 已作为 Compose profile 预留，不进入默认最小启动链路：

```bash
docker compose --profile orchestration up --build -d dagster
docker compose --profile tracking up --build -d mlflow
```

启用后，Dagster 位于 `http://localhost:3000`，MLflow 位于
`http://localhost:5000`。MLflow 使用独立的 `quant_mlflow` 数据库，并将
artifact 写入 MinIO 的 `mlflow` bucket。

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
