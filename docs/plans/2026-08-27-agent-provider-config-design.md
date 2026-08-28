# Agent 基座模型配置方案（LLM Provider 选择）

**日期：** 2026-08-27
**状态：** 已评审（按用户反馈定稿）
**目标读者：** 产品 / 工程 / UI
**上游文档：** [2026-08-26-research-workbench-refactor-design.md](./2026-08-26-research-workbench-refactor-design.md)

---

## 0. 一句话目标

让用户在**当前系统内**选择用哪个 Agent（`codex` / `pi`）作为自然语言会话的 LLM 后端，并为其选择 provider 与基座模型；配置只在本系统生效，**绝不改写本机已安装的 `codex` / `pi` 的全局配置**。

---

## 1. 现状（可直接复用的部分）

| 项 | 现状 |
|---|---|
| Agent 后端 | `research/factor_extract.py::default_runner()` 可注入式选择；`_pi_complete` 已实现非交互 `pi -p --no-session --mode text --provider/--model/--api-key` |
| 配置来源 | 全部走 `.env` 环境变量（`PI_PROVIDER/PI_MODEL/PI_API_KEY`、`DEEPSEEK_API_KEY`、`ZHIPU_API_KEY`、`CODE_CLI_API_KEY`） |
| 持久化 | 无 DB 配置表；无「每 provider 缓存 apikey」的能力 |
| codex CLI | `codex exec -m <model> --ignore-user-config --ephemeral <prompt>`；provider 鉴权走 `CODE_CLI_API_KEY` |
| pi CLI | `pi -p --no-session --mode text --provider <P> --model <M> --api-key <K> <prompt>`；`pi --list-models` 直接返回 provider+model 目录 |

结论：调用层隔离机制已经具备（pi 用 CLI 参数、codex 用 `--ignore-user-config` + env），缺的是**「用户可配置 + 持久化 + apikey 复用 + 模型目录」这一层**。

---

## 2. 需求（已明确）

1. **两个 Agent**：`codex`、`pi`。
2. **每个 Agent 都有默认 provider 清单 + 一个 `Other`**：
   - `codex` 默认 provider：`openai`（GPT 家族：`gpt-5.6-sol`、`o3`、`gpt-4.1` 等）。用户可选 `Other` 自定义 OpenAI 兼容端点（起名 + 填 key）。
   - `pi` 默认 provider：`anthropic` / `google` / `openai` / `deepseek` / `kimi` / `openrouter` 等（来自 `pi --list-models` 目录）。用户可选 `Other` 自定义任意 provider。
3. **`Other` 交互**：先给 provider 起名 → 填 API key → 系统自动拉取该 provider 的模型列表。
4. **模型清单自动获取**：用户**只需从自动获取的模型列表中选择**，无需手填模型名。
5. **API key 不加密**（明文存储，仅本系统本地演示）。
6. **单用户**：单份全局活跃配置。
7. **即时生效**：runner 每次调用时读 DB 活跃配置。
8. **保留兜底**：DB 无配置时降级现有 env 链路（`DEEPSEEK_API_KEY` → `ZHIPU_API_KEY` → 遗留 pi）。

---

## 3. 概念模型

```
Agent (codex | pi)
  └─ Provider（默认清单里的一个，或 Other 自定义）
        ├─ api_key      （每 provider 缓存一条，明文，跨次复用）
        └─ Model        （从该 provider 的模型目录自动拉取，用户点选）
```

约束（服务端强制）：
- `agent = codex` → 默认 provider 仅 `openai`（GPT 模型）；`Other` 允许自定义 OpenAI 兼容 provider。
- `agent = pi` → 任意 provider / 任意模型。

---

## 4. 模型目录（自动获取）

服务端新增 `ModelCatalogService`，返回 `[{provider, model, context, max_out, thinking, images}]` 形态的模型列表：

| Agent | 获取方式 | 说明 |
|---|---|---|
| `pi` | `pi --list-models [search]` | 原生目录（`pi update --models` 刷新），含 provider/context/thinking/images 能力位 |
| `codex` | OpenAI 兼容 `/v1/models`（用已存 key） | GPT 模型清单；key 无效时回退静态 GPT 清单 |
| `Other`（pi） | `pi --list-models` 按 provider 过滤 + 自定义端点 | 自定义 provider 按其类型走对应通道 |
| `Other`（codex） | OpenAI 兼容 `/v1/models`（自定义 base_url + key） | 自定义 OpenAI 兼容端点 |

- 结果**缓存**（短期），提供「刷新」能力；拉取失败时给出可读错误并回退到**自由输入模型名**（仅兜底，正常路径用户点选）。
- 用户选择模型后，系统把「provider + model」写入活跃配置；调用时透传给 CLI（`pi --provider/--model`、`codex -m`）。

---

## 5. 存储（明文、单用户）

**`agent_provider_credentials`（provider 凭据，可跨次复用）**

| 列 | 类型 | 说明 |
|---|---|---|
| provider | String(64) PK | 默认 provider 名，或 `Other` 时用户自定义的名字 |
| kind | String(16) | `builtin` / `custom` |
| agent | String(16) | 该凭据归属的 agent（`codex` / `pi`） |
| base_url | String(255) \| null | 自定义 provider 的 OpenAI 兼容端点（Other 时可选） |
| api_key | Text | **明文** |
| updated_at | DateTime | 最近写入 |

**`agent_config`（活跃选择，单行）**

| 列 | 类型 | 说明 |
|---|---|---|
| active_agent | String(16) | `codex` / `pi` |
| active_provider | String(64) | 当前 provider |
| active_model | String(128) | 当前基座模型 |
| updated_at | DateTime | |

> apikey 存入凭据表后，下次再选同一 provider **自动复用**（响应返回掩码 `sk-***abc` + `has_api_key=true`），用户仍可覆盖。

---

## 6. 隔离语义（关键）

调用 CLI 时**只用 CLI 参数 / 进程环境变量**注入项目配置，不写任何全局配置文件：

| Agent | 调用形态 | 隔离保证 |
|---|---|---|
| `pi` | `pi -p --no-session --mode text --provider <P> --model <M> --api-key <K> <prompt>` | 参数只在本次进程生效，不写 `pi` 配置 |
| `codex` | `codex exec --ignore-user-config --ephemeral -m <model> <prompt>`，env 注入 `CODE_CLI_API_KEY`（或自定义 provider 的 base_url） | `--ignore-user-config` 不读 `~/.codex/config.toml`，`--ephemeral` 不落 session |

> 因此在本系统切模型，本机 `pi`/`codex` 的全局配置、auth、会话完全不受影响。

---

## 7. Runner 改动

`default_runner()`：**优先读 DB 活跃配置** → 派发 `_codex_complete` / `_pi_complete`；DB 无配置时降级现有 env 兜底。

```text
default_runner()
  ├─ 读 agent_config(active_agent, active_provider, active_model)
  │    ├─ codex → _codex_complete(model, api_key, base_url?)
  │    └─ pi    → _pi_complete(provider, model, api_key)
  └─ 无 DB 配置 → 现有 env 兜底链（向后兼容，即时回退）
```

- 新增 `_codex_complete(prompt, *, model, api_key, base_url=None)`：`codex exec --ignore-user-config --ephemeral -m <model>` + env `CODE_CLI_API_KEY`。
- `_pi_complete` 从 DB 取 `provider/model/api_key`（不再读 env 变量），非交互形态不变。
- 注入方式：`default_runner` 增加可选 `config` 入参，由有 DB 会话的调用方（research/factor_construction/strategy_generation 的 API 层）解析后传入；无参调用保留 env 兜底。

---

## 8. API（新增 `/v1/agent-config`）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/agent-config` | 活跃配置：`{agent, provider, model, credentials:[{provider, agent, has_api_key, masked_key, kind}]}` |
| GET | `/agent-config/agents` | agent 清单 + 约束：`[{name:"codex", defaultProviders:["openai"]}, {name:"pi", defaultProviders:[...]}]` |
| GET | `/agent-config/providers?agent=` | 该 agent 的默认 provider 清单 + 各自 `has_api_key` + 已存的自定义 provider |
| GET | `/agent-config/models?agent=&provider=` | **模型目录自动获取**（透传 `ModelCatalogService`），返回模型列表 |
| PUT | `/agent-config/credentials` | 保存/覆盖 provider 凭据（`{agent, provider, kind, base_url?, api_key}`；`Other` 必填 name） |
| PUT | `/agent-config` | 设置活跃选择（`{agent, provider, model}`；服务端校验 codex 约束 + 模型在目录内） |

---

## 9. 前端 UI（设置页 · 三步向导）

- 入口：顶栏用户区「Agent 配置」→ `/settings/agent`（复用现有 token 系统，左-右卡片布局）。
- 三步：
  1. **选择 Agent**：`codex`（GPT 基座模型）/ `pi`（任意模型）。
  2. **选择 Provider**：
     - 默认清单逐个展示，标 `已配置 apikey ✓`（显示掩码，可覆盖）或 `未配置`。
     - 末尾 **`Other`**：起名 → 填 API key（→ 可选 base_url）。
  3. **选择模型**：调用 `/models` 自动拉取列表，用户**点选**（含 context/thinking/images 能力位展示）；拉取失败回退自由输入。
- 顶部明示隔离语义：「配置仅在本系统生效，不会改动本机 codex / pi 的配置」。
- 保存即写入 DB，**即时生效**。

---

## 10. 实施顺序（灰度）

| 阶段 | 内容 | 风险 |
|---|---|---|
| P1 | 数据模型 + 迁移（`agent_provider_credentials`、`agent_config`，明文） | 低 |
| P2 | `ModelCatalogService`（pi `--list-models` / codex OpenAI `/v1/models` + 缓存/刷新/回退） | 中 |
| P3 | Runner：新增 `_codex_complete`，`default_runner` 读 DB 配置 + env 兜底 | 中 |
| P4 | API `/agent-config/*`（apikey 复用判断、模型目录透传、codex 约束校验） | 低 |
| P5 | 前端设置页（三步向导含 Other + 隔离提示 + 即时生效） | 中 |
| P6 | 探活/测试连接 + CLI 失败原因透出 | 低 |

---

## 11. 关键风险

- **codex 鉴权依赖**：codex 走 `CODE_CLI_API_KEY`；若用户在 `Other` 填普通 `OPENAI_API_KEY` 可能不生效，表单需明确「填 codex/code-cli 的 key 或 OpenAI 兼容端点凭据」。
- **模型名漂移**：GPT 模型名会变；目录以自动拉取为准，`pi --list-models` 已含最新目录，codex 目录依赖 key 有效性，失败时回退静态清单。
- **`Other` 端点兼容性**：自定义 provider 依赖 OpenAI 兼容协议；对不走该协议的自定义 provider 只能回退到 `pi` 的自有 provider 机制。
- **明文 api_key**：仅本地单用户演示可接受；上线多用户前需升级为加密存储（`AGENT_SECRET` 派生密钥）。
