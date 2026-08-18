# 按需数据供给：研究任务驱动的数据管线设计

日期：2026-08-19
状态：设计稿

## 1. 背景与目标

用户诉求：不要"预先确定合约 + 预先下载数据"的笨重模式，而要"建研究任务时
指定标的池 → 系统按需拉取数据源 → 密封快照 → 研究"的闭环。

核心结论：**"按需拉取"和"密封快照"不矛盾。** 数据获取本就可以按需（iFinD/
AkShare 实时拉任意合约），密封快照是反数据窥探的纪律，不能省。缺的是中间的
**编排层**——把"研究任务 → 数据采集 → 密封 → 验证"自动化。

## 2. 现状诊断

三个 gap：

1. **`universe_ref` 是死字符串。** `"futures:liquid-initial"` 在 research、
   experiments、preconditions 之间传递，但没有任何代码把它解析成具体合约
   列表。数据采集靠手工脚本里的硬编码合约清单。

2. **数据采集是手工脚本。** `ingest-market-data.py` 和
   `regenerate-snapshots.py` 是独立运维脚本，没有接到研究任务生命周期。
   用户建任务时，系统不会自动拉数据。

3. **快照是启动时静态加载的全局 config。** `app.py` 在启动时
   `JsonFormalSnapshotCatalog.from_path(...)` 加载 `formal-snapshots.json`，
   按需生成快照后必须重启容器。不支持运行时注册。

已有资产（可直接复用）：

- `markets/contracts.py`：完整的市场规则建模（MarketDefinition、LicensePolicy、
  RuleCategory，含 `HISTORICAL_UNIVERSE` / `ROLL_POLICY` 规则类别）。
- `markets/futures.py::select_main_contract`：基于持仓量阈值 + 确认天数的主力
  合约选择规则（纯函数，已实现）。
- `data_gateway/`：iFinD（FORMAL）与 AkShare（EXPLORATORY）双数据源，统一
  `RawPITRow` 契约 + `SqlAlchemyPitStore` 入库。
- AkShare `futures_display_main_sina` / `futures_zh_realtime`：可实时拉主力
  合约清单和具体合约代码。

## 3. 目标架构

```
用户建研究任务（标的池规格 + 时间区间）
        │
        ▼
  UniverseResolver —— 解析 universe_ref → 具体合约列表
        │
        ▼
  DataProvisioning —— 采集（iFinD/AkShare）→ 入库 pit_observations
        │
        ▼
  SnapshotSealer —— 生成密封快照（formal + label，decision_time 配套）
        │
        ▼
  快照就绪 → 预注册 → 运行 → 验证（现有流程不变）
```

数据获取按需，密封纪律保留。密封快照成为研究任务的派生产物，而不是全局
预先配置。

## 4. 核心设计

### 4.1 UniverseSpec 与 UniverseResolver

`universe_ref` 从死字符串升级为可解析规格。格式 `<market>:<kind>`：

| universe_ref | 解析规则 |
|---|---|
| `futures:liquid-initial` | AkShare 拉主力清单，按成交量取 top N（默认 30） |
| `futures:explicit` | 用户在建任务时显式给出合约代码 |
| `cn-a:csi300` | 沪深 300 成分股（后续实现） |

新增 `UniverseResolver`（`data_gateway` 或新模块 `markets/universe.py`）：

```python
@dataclass(frozen=True)
class UniverseSpec:
    universe_ref: str
    instruments: tuple[str, ...]      # 解析结果
    resolved_at: datetime
    source: str                        # ifind / akshare / explicit

class UniverseResolver:
    def resolve(self, universe_ref: str, *, explicit: tuple[str, ...] = ()) -> UniverseSpec:
        ...
```

解析结果（具体合约代码）是**可审计的**：记录解析用的数据源、时间、清单，
防止"挑标的池"式的数据窥探。

### 4.2 DataProvisioning 服务

把 `ingest-market-data.py` + `regenerate-snapshots.py` 的逻辑收编为服务
`DataProvisioning`：

```python
class DataProvisioning:
    def provision(self, spec: UniverseSpec, *, start: date, end: date) -> ProvisionResult:
        # 1. 采集：对每个合约拉日频（iFinD FORMAL，回退 AkShare）
        # 2. 入库：pit_observations
        # 3. 密封：生成 formal + label 快照（decision_time 配套，复用 regenerate 逻辑）
        # 4. 返回 snapshot_id + manifest_hash + decision_time
        ...
```

采集时间约 1-3 分钟（30 合约 × 几百天），阶段 1 采用**同步**执行（建任务时
阻塞等待，带进度提示）；阶段 2 再异步化（后台任务 + 状态轮询）。

### 4.3 快照动态注册

`FormalSnapshotCatalog` 从"启动时静态加载 config"扩展为"支持运行时注册"。
在 `InMemoryFormalSnapshotCatalog` 上增加 `register()` 方法，或新增一个
可变的 `RegistryCatalog`。快照 payload 同时落库（新表 `snapshot_registry`），
容器重启后从数据库恢复，不再依赖全局 config 文件。

### 4.4 研究任务状态机

`ResearchJobState` 增加 `DATA_PROVISIONING`：

```
DRAFT → DATA_PROVISIONING（采集/密封中）→ READY → RUNNING → ... → SUCCEEDED
                                              └→ FAILED（采集失败，可重试）
```

建任务接口从"必须预先有快照"改为"任务创建后系统自动准备数据"。

## 5. 与现有纪律的关系（为什么密封快照不能省）

按需拉取不破坏纪律，因为：

1. **解析可审计**：universe → 合约清单 的解析记录了数据源和时间，不能随意
   "挑合约"。
2. **密封不可篡改**：快照生成后 hash 锁定，预注册时校验 `snapshot_manifest_hash`。
3. **决策时点配套**：decision_time 与 label 一起密封，未来收益标签的可用时间
   严格晚于决策时点，杜绝未来泄漏。

"按需"改变的是**什么时候、由谁生成快照**（从手工脚本 → 研究任务触发），
不改变**快照必须密封**这个纪律。

## 6. 分阶段落地

### 阶段 1：最小闭环（同步）

- `UniverseResolver`：解析 `futures:liquid-initial` 和 `futures:explicit`
- `DataProvisioning`：收编 ingest + regenerate 逻辑为服务
- 新端点 `POST /v1/data-provisioning`：给定 universe + 时间区间 → 采集 + 密封
  → 返回 snapshot_id + manifest_hash + decision_time
- 前端建任务时自动调该端点，预注册直接使用返回的快照

### 阶段 2：快照持久化

- 快照落库 `snapshot_registry`，catalog 运行时注册 + 重启恢复
- 去掉"重启 api 加载 config"的步骤

### 阶段 3：异步化 + 状态机整合

- 后台任务队列，`DATA_PROVISIONING` 状态 + 轮询
- 任务生命周期完整整合（建任务 → 数据就绪 → 预注册 → 验证）

## 7. 风险与取舍

- **同步采集的阻塞**：阶段 1 建任务时阻塞 1-3 分钟。可接受，前端展示进度；
  阶段 3 异步化解决。
- **iFinD 凭证**：FORMAL 采集依赖 `IFIND_REFRESH_TOKEN`；无凭证回退 AkShare
  （EXPLORATORY，只能回测不能正式验证）。保持现状。
- **郑商所/广期所合约格式**：iFinD 合约代码格式差异（郑商所 3 位数字），
  在 UniverseResolver 里做交易所代码归一化。
