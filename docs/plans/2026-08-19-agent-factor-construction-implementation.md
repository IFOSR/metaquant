# Agent 因子构建（研报 → 可执行模型）技术规划

**日期：** 2026-08-19
**状态：** 技术规划（承接 `2026-08-19-agent-factor-construction.md` 设计稿）
**目标：** 把 agent 的产物形态从「不可执行的 factor-ir JSON」升级为「可执行的
代码工件（model.py / train.py / infer.py）」，由平台在 PIT 安全 + 内容寻址的纪律下
训练 / 推理出因子值，并复用现有验证管道。

---

## 0. 一句话架构

```
研报 --agent--> 构建规格(spec) --agent--> 代码包(model/train/infer) --沙箱--> 权重/因子值 --现有验证--> 晋升
              ↑ 可审计的"研究意图"          ↑ 内容寻址冻结            ↑ PIT 接口强制
```

关键技术栈：FastAPI + SQLAlchemy + PostgreSQL + MinIO（控制面，保持**不引入
torch/pandas**）；PyTorch + pandas + numpy（沙箱镜像，仅供生成的代码使用）。

---

## 1. 定位与范围

### 1.1 本规划覆盖

- **阶段 1**：agent 抽取「构建规格」→ agent 生成 `model.py/train.py/infer.py`，产物
  内容寻址冻结、可审计。不改平台执行引擎。
- **阶段 2**：沙箱试运行闭环（生成 → 运行 → 报错 → 修正），跑通「代码能产出因子值」。
- **阶段 3**：训练/推理执行 + 权重注册为工件 + 因子值进入现有验证管道
  （IC/稳定性/独立性/晋升）。

### 1.2 明确不做（本期）

- 大模型 GPU 训练（阶段 3 只做 CPU 小模型跑通验证，大模型留给研究员本地环境）。
- ONNX 等替代推理格式（先固定 PyTorch）。
- 对现有 `factor_ir` 声明式路径的删除或迁移（两条路径并存，IR 继续服务简单线性因子）。

### 1.3 与现有代码的关系（重要约束）

现有 `research/factor_extract.py` 产出 factor-ir JSON；本功能是**新增一条平行路径**，
不改动 factor-ir 的执行与验证。两处可复用锚点：

1. `experiments/contracts.py::compute_run_fingerprint` 已经预留了
   `code_sha / image_digest / dependency_lock_hash / executor_version / config_hash`
   字段——它们天然映射到本功能的「代码包哈希 / 沙箱镜像 digest / 依赖锁 / 执行器版本」。
2. `factor_executor/model.py::canonical_observations` 已能产出
   `factor-observations/v1` 规范化 JSON——推理产出的因子值**复用同一格式**，从而
   直接进入现有验证管道。

---

## 2. 关键设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 新包名 | `quant_platform/factor_construction/` | 与 `factor_ir` / `factor_executor` 命名对齐 |
| 生成代码导入的接口包 | `quant_platform/ml/`（沙箱内发行） | 设计稿明确 `from quant_platform.ml import load_pit_frame` |
| 控制面是否引 pandas/torch | 否 | 保持控制面确定性、轻量；数据接口客户端在沙箱镜像里 |
| 沙箱取数方式 | 只读 HTTP 数据服务，沙箱不接触 DB | PIT 安全在服务端强制，沙箱零 DB 凭据、零外网 |
| 内容寻址 | 复用 `artifacts/store.py` 的 `sha256:<hex>` + MinIO | 已有成熟实现，直接复用 |
| 因子值格式 | 复用 `factor-observations/v1` | 直接进现有验证管道 |
| 模型权重格式 | PyTorch `state_dict`（bytes 存 MinIO） | 阶段 3 固定 PyTorch |
| 规格 schema | `build-spec/v1` | 与 `factor-ir/v1` 并列版本化 |

---

## 3. 模块布局（新增文件）

```
src/quant_platform/factor_construction/
  __init__.py
  spec.py          # FactorBuildSpec pydantic + canonical hash + LabelSpec
  artifacts.py     # CodeBundle 三文件 manifest、WeightArtifact、FactorValueArtifact
  generator.py     # agent：研报→spec；spec→model/train/infer（prompt + retry）
  runner.py        # SandboxRunner 抽象 + Docker/Subprocess 实现 + 试运行闭环
  data_service.py  # 只读 PIT 数据服务（server 侧，/v1/data/*）
  repository.py    # SQLAlchemy 仓储
  models.py        # SQLAlchemy 表模型
  schemas.py       # API 请求/响应模型
  api.py           # FastAPI 路由

src/quant_platform/ml/            # 沙箱内发行（进镜像，不进控制面依赖）
  __init__.py      # load_pit_frame / load_label_frame / load_exposure_frame / PITFrame

alembic/versions/xxxx_create_factor_construction_tables.py

tests/factor_construction/        # 单元 + 契约测试
tests/data_service/               # 数据服务 PIT 安全测试
tests/ml_interface/               # quant_platform.ml 客户端契约测试
```

依赖：控制面 `pyproject.toml` 不新增重依赖；`quant_platform/ml` 作为独立
`[project.optional-dependencies] ml = ["numpy", "pandas", "torch"]` 或独立
`requirements-sandbox.txt`，仅在沙箱镜像安装。

---

## 4. 领域模型

### 4.1 FactorBuildSpec（构建规格）

agent 第一阶段产出、第二阶段代码生成的输入、全程审计依据。**不可执行**，但
**内容寻址**。

```python
# spec.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

class LabelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)            # 如 future_21d_vwap_return
    price_field: str                            # 如 vwap（必须来自 inputs 的字段）
    horizon: int = Field(ge=1)                  # 交易日
    return_type: str = "simple"                 # simple | log

class FactorBuildSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_version: str = "build-spec/v1"
    factor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    factor_name: str = Field(min_length=1)
    market: str                                  # CN_A | CN_COMMODITY_FUTURES
    universe_ref: str = Field(min_length=1)
    frequency: str = "1d"
    inputs: list[str] = Field(min_length=1)      # ["close","open","high","low","volume","amount","vwap"]
    label: LabelSpec
    architecture: str                            # MLP | LSTM | TRANSFORMER | LINEAR
    style_neutralize: list[str] = Field(default_factory=list)
    expected_direction: str = "POSITIVE"         # POSITIVE | NEGATIVE | NON_MONOTONIC | UNKNOWN
    hyperparameters: dict = Field(default_factory=dict)
    brief: dict = Field(default_factory=dict)    # 复用 BriefContent 的 model_dump
    evidence_ref_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _label_field_in_inputs(self) -> "FactorBuildSpec":
        if self.label.price_field not in self.inputs:
            raise ValueError("label.price_field must be in inputs")
        return self
```

**规范化哈希**：复用 `experiments/contracts.py::canonical_hash`（同仓库已有），
保证 `spec_hash = canonical_hash(spec)` 可复现、可冻结。

### 4.2 CodeBundle（三工件代码包）

| 工件 | 契约（生成代码必须遵守） | 产物 |
|---|---|---|
| `model.py` | 暴露 `def build_model(hyperparams: dict) -> Model`，`Model.forward(x)` | 模型类 |
| `train.py` | 暴露 `def train(data: PITFrame, spec: dict) -> Any`，返回可序列化权重对象 | 权重 |
| `infer.py` | 暴露 `def infer(data: PITFrame, weights: Any) -> Series`，返回因子值 | 因子值（时序） |

每个文件内容寻址（`sha256:<hex>`，复用 `artifacts/store.py`）。包 manifest：

```python
# artifacts.py
BUNDLE_SCHEMA = "code-bundle/v1"

def build_code_bundle(files: dict[str, bytes], *, spec_hash: str) -> dict:
    return {
        "schema_version": BUNDLE_SCHEMA,
        "spec_hash": spec_hash,
        "files": {
            name: {"sha256": content_hash(payload), "size_bytes": len(payload)}
            for name, payload in sorted(files.items())   # 固定 model/train/infer 三键
        },
    }
```

冻结 = 将三文件 + manifest 上传 MinIO，`bundle_hash = canonical_hash(manifest)`，
写入 DB，此后不可改。

### 4.3 WeightArtifact / FactorValueArtifact

```python
WEIGHT_SCHEMA = "model-weights/v1"        # 内容 = torch state_dict 的 bytes（MinIO）
FACTOR_SCHEMA = "factor-observations/v1"  # 复用 factor_executor.model.canonical_observations
```

- 权重：训练脚本产物，MinIO 存 bytes，manifest 记录 `model_hash + bundle_hash + spec_hash + data 指纹`。
- 因子值：推理脚本产物，复用 `canonical_observations` 得到 `output_hash`，即可被现有
  `validation` 模块当作 `FactorComputationArtifact` 的观测值消费。

---

## 5. 数据接口（PIT 安全在服务端强制）

### 5.1 只读数据服务（server 侧，控制面）

沙箱**不接触 DB**，只通过 HTTP 调数据服务取数；PIT 过滤在服务端用现成的
`data_gateway/loader.py::filter_and_resolve` 完成。

```python
# data_service.py —— 只读，无写接口
@router.get("/v1/data/pit-frame")
def pit_frame(
    snapshot_id: str,
    fields: str,                 # "close,open,high,low,volume,amount,vwap"
    decision_time: datetime,     # 必须带时区
    instrument_ids: str | None = None,
) -> dict:
    rows = _store.load(instrument_ids=..., field_prefix="market.eod.", ...)
    visible = filter_and_resolve(rows, decision_time=decision_time)  # available_time <= decision_time
    return _pivot_to_json(visible, fields.split(","))                # 列 = field 末段
```

关键点：

- **推理请求永远不带 label**：`pit-frame` 端点不含任何 label 能力。
- **训练 label 单独端点 + 授权**：`POST /v1/data/label-frame` 要求 `label` 字段 + 训练
  授权 grant，返回的 label 列由 `price_field` 的 `t+horizon / t - 1` 计算（PIT 无关，
  因为 label 天然是未来收益，但只能经此通道产出，绝不混入特征列）。

```python
# data_service.py —— label 只在显式授权下产出
@router.post("/v1/data/label-frame")
def label_frame(command: LabelFrameCommand, actor=Depends(principal)) -> dict:
    _require_grant(actor, {"factor_construction.train"})
    return {"instrument_id": [...], "event_time": [...], "label": [...]}
```

### 5.2 客户端（沙箱内 `quant_platform/ml`）

生成的代码只 import 这个包，看不到任何 DB/网络细节：

```python
# quant_platform/ml/__init__.py —— 沙箱镜像内发行
from __future__ import annotations

import pandas as pd
from dataclasses import dataclass

@dataclass(frozen=True)
class PITFrame:
    data: pd.DataFrame          # index = (instrument_id, event_time), columns = fields
    decision_time: str

    def __post_init__(self) -> None:
        if self.data.index.has_duplicates:
            raise ValueError("PITFrame index must be unique (instrument, event_time)")

def load_pit_frame(
    *,
    snapshot_id: str,
    fields: list[str],
    decision_time: str,
    base_url: str | None = None,          # 默认读环境变量 ML_DATA_SERVICE_URL
) -> PITFrame:
    """只读、只含 available_time <= decision_time 的行；无 label 能力。"""
    resp = _http_get(f"{_base(base_url)}/v1/data/pit-frame", params={...})
    df = pd.DataFrame(resp["rows"]).set_index(["instrument_id", "event_time"])
    return PITFrame(data=df, decision_time=decision_time)

def load_label_frame(
    *,
    snapshot_id: str,
    label_name: str,
    price_field: str,
    horizon: int,
    return_type: str,
    decision_time: str,
    base_url: str | None = None,
) -> pd.Series:
    """训练专用；label 只作为返回值出现，调用方负责不让其进入特征。"""
    ...

def load_exposure_frame(
    *, snapshot_id: str, factors: list[str], decision_time: str
) -> pd.DataFrame:
    """风格暴露（size/volatility/reversal/liquidity），用于 infer 端中性化。"""
    ...
```

**训练/推理边界由两层保证**：服务端（`pit-frame` 无 label，`label-frame` 需训练授权）
+ 客户端（`load_pit_frame` 签名里根本没有 label 参数；infer 运行器强制
`with_label=False`）。

---

## 6. 代码生成（agent）

### 6.1 两阶段生成

复用现有 `factor_extract.py` 的 runner 注入模式（`pi`/DeepSeek/Zhipu 可插拔）。

**阶段 A：研报 → 规格**（改现有 `research-briefs:extract-factor` 或新增端点）

- Prompt 要求返回 `FactorBuildSpec` JSON（不是 factor-ir）。
- 校验：`FactorBuildSpec.model_validate`，失败则带纠正提示重试一次（沿用
  `_build_extraction` 的重试模式）。

**阶段 B：规格 → 三文件代码**

- 输入：spec + 三文件的**契约说明** + `quant_platform.ml` 的用法示例。
- 输出：三份 Python 源文件（用 ```` ```python ``` ```` 分块，按文件名解析）。
- 校验：AST 语法检查（`ast.parse`）+ 契约检查（`model.py` 有 `build_model` 等）。
- 失败重试：把 traceback/校验错误喂回，最多 N 次（默认 3）。

### 6.2 生成契约的骨架（写给 agent 的示例）

```python
# model.py
from quant_platform.ml import PITFrame

def build_model(hyperparams: dict):
    import torch
    return torch.nn.Sequential(
        torch.nn.Linear(hyperparams.get("input_dim", 7),
                        hyperparams.get("hidden_dim", 64)),
        torch.nn.ReLU(),
        torch.nn.Linear(hyperparams.get("hidden_dim", 64), 1),
    )

# train.py
from quant_platform.ml import load_pit_frame, load_label_frame

def train(data: PITFrame, spec: dict) -> dict:
    import torch
    features = data.data.values          # 只取特征列
    y = load_label_frame(...)            # label 单独通道
    model = build_model(spec["hyperparameters"])
    ...                                   # 训练，返回 state_dict

# infer.py
from quant_platform.ml import load_pit_frame

def infer(data: PITFrame, weights: dict):
    model = build_model(...); model.load_state_dict(weights)
    with torch.no_grad():
        return model(torch.tensor(data.data.values)).numpy().ravel()
```

生成时注入三条红线：**不得 import 网络库 / subprocess / os / 文件写**；特征只能来自
`load_pit_frame` 返回的 `data.data`；label 只能来自 `load_label_frame` 返回值。

---

## 7. 沙箱执行与试运行闭环（阶段 2）

### 7.1 SandboxRunner 抽象

```python
# runner.py
class SandboxRunner(Protocol):
    def run(self, *, bundle_hash: str, command: str,
            image_digest: str, cpu_limit: int, mem_limit_mb: int,
            timeout_seconds: int) -> SandboxResult: ...

@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    artifacts: dict[str, str]   # 产物名 -> content hash
    timed_out: bool
```

- `DockerSandboxRunner`：`docker run --network=<仅数据服务白名单> --read-only
  --memory=... --cpus=...`，挂载代码包 + 只读 `/data` 接口，输出目录只写 MinIO。
- `SubprocessSandboxRunner`：本地/测试用，`resource.setrlimit` 限制 CPU/内存，
  无网络能力（测试里 mock 数据服务）。

安全边界（对齐设计稿 §7）：只读数据、只写工件、禁外网、禁任意文件系统写、禁
subprocess 逃逸。

### 7.2 生成 → 运行 → 报错 → 修正循环

```
generate(spec) -> bundle
  -> smoke(bundle, "python -m infer_runner --selfcheck")     # 只验证 import + 空跑
     └ fail -> 把 stderr 喂回 generator 修正 -> 新 bundle（新 hash）
  -> 直到 smoke 通过 或 达到 max_rounds（默认 3，失败回退人工）
```

每次修正产出**新内容寻址 bundle**，不改旧 bundle（不可变）。

---

## 8. 纪律保持

| 纪律 | 实现 |
|---|---|
| 代码冻结 | 三文件 + manifest 内容寻址；`freeze` 后 spec/bundle 不可改（DB 状态机 DRAFT→FROZEN） |
| 可复现 | `run_fingerprint = compute_run_fingerprint(code_sha=bundle_hash, image_digest=..., dependency_lock_hash=..., executor_version=..., config_hash=..., random_seed=..., ...)`，复用现有函数 |
| PIT 安全 | 数据服务端 `filter_and_resolve` 强制 `available_time <= decision_time`；infer 无 label |
| 审计血缘 | `研报 → spec_hash → bundle_hash → weights_hash → factor_values_hash → 验证报告 hash`，全程 lineage 边（复用 `experiments/contracts.py::LineageEdge`） |

---

## 9. 持久化与 API

### 9.1 表模型（alembic 新增）

```python
# models.py
class FactorBuildSpecModel(Base):
    __tablename__ = "factor_build_specs"
    id = mapped_column(String(64), primary_key=True)
    project_id = mapped_column(String(128), index=True)
    research_job_id = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"))
    brief_version_id = mapped_column(String(64))
    spec_hash = mapped_column(String(64), unique=True, nullable=False)
    spec_payload = mapped_column(JSON, nullable=False)
    state = mapped_column(String(16), nullable=False)   # DRAFT | FROZEN
    created_at / created_by / frozen_at / frozen_by ...

class FactorCodeBundleModel(Base):
    __tablename__ = "factor_code_bundles"
    id = mapped_column(String(64), primary_key=True)
    spec_hash = mapped_column(ForeignKey("factor_build_specs.spec_hash"))
    bundle_hash = mapped_column(String(80), unique=True, nullable=False)
    manifest_payload = mapped_column(JSON, nullable=False)  # files -> sha256
    created_at / created_by ...

class FactorBuildRunModel(Base):
    __tablename__ = "factor_build_runs"
    id = mapped_column(String(64), primary_key=True)
    spec_hash = mapped_column(String(64))
    bundle_hash = mapped_column(String(80))
    kind = mapped_column(String(16))                      # SMOKE | TRAIN | INFER
    state = mapped_column(String(32))                     # QUEUED/RUNNING/SUCCEEDED/FAILED_*
    run_fingerprint = mapped_column(String(64), unique=True)
    weights_hash = mapped_column(String(80), nullable=True)
    factor_values_hash = mapped_column(String(80), nullable=True)
    error = mapped_column(Text, nullable=True)
    logs_ref = mapped_column(String(255), nullable=True)
    created_at / updated_at ...
```

命令收据 / 审计 / outbox 复用现有通用表（`research_command_receipts` /
`audit_events` / `outbox_events`）。

### 9.2 API 路由（`/v1`，沿用 Bearer + Idempotency-Key + If-Match + problem+json）

| 路由 | 阶段 | 作用 |
|---|---|---|
| `POST /factor-build-specs:extract` | 1 | agent：研报 → spec 草稿 |
| `POST /factor-build-specs/{id}:freeze` | 1 | 冻结 spec |
| `POST /factor-build-specs/{id}:generate` | 1 | agent：spec → 三文件代码包 |
| `POST /factor-code-bundles/{hash}:smoke` | 2 | 沙箱试运行（import/空跑） |
| `POST /factor-code-bundles/{hash}:train` | 3 | 训练 → 权重工件 |
| `POST /factor-code-bundles/{hash}:infer` | 3 | 推理 → 因子值工件 |
| `GET /factor-build-runs/{id}` | 2/3 | 运行状态 + 日志 ref |

---

## 10. 前端

- 研究详情页新增「因子构建」tab：spec 表单（inputs/label/architecture/style_neutralize/
  hyperparameters）、`extract → freeze → generate → smoke` 一键链路、代码三文件预览
  （只读 + 高亮）、试运行日志与状态。
- 阶段 3 增加 `train/infer` 按钮与权重/因子值工件展示；验证结果复用现有验证报告组件。

---

## 11. 测试策略

| 层 | 用例 |
|---|---|
| spec | 规范化哈希稳定；`label.price_field ∈ inputs` 校验；非法 architecture 拒绝 |
| 数据服务 | **PIT 安全：`available_time > decision_time` 的行绝不出现在 pit-frame**；label 端点无训练授权时 403；推理无 label |
| 客户端 | `PITFrame` 索引唯一；`load_pit_frame` 无 label 参数（类型层面） |
| 代码包 | 三文件 manifest 哈希稳定；缺文件/缺契约函数时拒绝；冻结后不可改 |
| 生成 | mock runner 返回固定三文件 → 校验通过；AST 错误 → 触发重试 |
| 沙箱 | subprocess runner 超时/内存限制；恶意代码（import os / 写文件）被拒 |
| 集成 | Docker Postgres/MinIO：freeze、bundle 上传、train/infer 产出因子值并进入验证 |

---

## 12. 分阶段任务分解（bite-sized）

> 每个任务 = 写失败测试 → 跑测试确认失败 → 最小实现 → 跑测试通过 → 提交。

### 阶段 1：规格 + 代码生成 + 冻结（无沙箱）

**Task 1.1 `FactorBuildSpec` 与规范化哈希**
- 建 `tests/factor_construction/test_spec.py`：`test_spec_hash_is_stable`、
  `test_label_field_must_be_in_inputs`。
- 实现 `spec.py`（§4.1）。

**Task 1.2 代码包 manifest**
- 建 `tests/factor_construction/test_artifacts.py`：`test_bundle_hash_stable`、
  `test_bundle_requires_three_files`、`test_bundle_rejects_missing_contract`。
- 实现 `artifacts.py::build_code_bundle`（§4.2），契约检查用 `ast.parse`。

**Task 1.3 agent：研报 → spec**
- 改 `research/api.py` 新增 `:extract` 端点 + `generator.py::extract_build_spec`，
  复用 `factor_extract.py` 的 runner/重试模式。
- 测试：mock runner 返回 spec JSON → `FactorBuildSpec` 通过；坏 JSON → 重试一次。

**Task 1.4 agent：spec → 三文件代码**
- `generator.py::generate_code_bundle`，prompt 含 §6.2 契约；解析 ```` ```python ````
  分块 → `build_code_bundle`。
- 测试：mock runner 返回三文件 → bundle 通过；语法错误 → 重试。

**Task 1.5 冻结与仓储**
- `models.py`（§9.1）+ alembic 迁移 + `repository.py`。
- API：`POST /factor-build-specs/{id}:freeze`（DRAFT→FROZEN，FROZEN 后不可改）。
- 集成测试：freeze 后 `generate` 拒绝。

### 阶段 2：数据服务 + 沙箱试运行闭环

**Task 2.1 只读 PIT 数据服务**
- `data_service.py`（§5.1）。
- 测试：`tests/data_service/test_pit_safety.py`（未来行绝不出现）、label 授权 403。

**Task 2.2 沙箱客户端 `quant_platform.ml`**
- `src/quant_platform/ml/__init__.py`（§5.2）+ 独立依赖清单。
- 测试：`tests/ml_interface/`（mock 数据服务 → DataFrame 索引唯一、无 label 参数）。

**Task 2.3 `SandboxRunner` + 试运行闭环**
- `runner.py`（§7.1）+ `smoke` 端点（§9.2）。
- 测试：subprocess runner 对「import os / 写文件」代码拒绝；超时/内存限制。
- 闭环：`generate → smoke → stderr 回喂 → 新 bundle`，`max_rounds` 达上限回退人工。

### 阶段 3：训练/推理执行 + 进入验证

**Task 3.1 train/infer 执行器**
- 沙箱内 `train.py`/`infer.py` 的 runner 命令封装；`train` 产出权重（MinIO）、
  `infer` 产出 `factor-observations/v1`。
- 复用 `compute_run_fingerprint` 填 `code_sha=bundle_hash / image_digest /
  dependency_lock_hash`。

**Task 3.2 因子值进验证管道**
- 将 `factor-observations/v1` 适配为现有 `FactorComputationArtifact` 观测值 →
  `validation` 模块（IC/稳定性/独立性）。
- 测试：固定 bundle + 固定权重 → 固定因子值 → 固定验证哈希（可复现）。

**Task 3.3 前端 + 端到端**
- 前端 tab + `train/infer` 按钮；端到端集成测试（Docker）。

---

## 13. 风险与回退（对齐设计稿 §7）

- **生成代码跑不通** → 阶段 2 试运行闭环 + `max_rounds` 后回退人工修正。
- **训练算力** → 阶段 3 CPU 小模型跑通验证；大模型回研究员 GPU 环境。
- **代码安全** → 沙箱只读数据/只写工件/禁外网/禁文件写；数据服务只读无写。
- **框架选择** → 先固定 PyTorch；ONNX 推理留后续。
