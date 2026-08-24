# Xj-engine 变更记录

## 2026-08-25

### 初始独立化

- 从 `agent-harness/backend/engine` 提取为独立引擎
- 目录：`dsh-skills/Xj-engine/`
- Python 包：`xj_engine`

### 兼容性改造

- 移除 `backend.database` 依赖，新增本地 `database.py`
- 移除 `backend.services.test_skills` 依赖，`skills.py` 改为 stub
- 所有 `backend.engine.*` 导入改为包内相对导入
- `claude_engine.py` 的 `anthropic` 改为可选依赖
- 新增 `.env.example`：`XJ_ENGINE_DB_URL` / `AGENT_ENGINE_SECRET`

### 可安装化

- 新增 `pyproject.toml`
- 支持 `pip install -e .`
- 新增 CLI：
  - `xj-engine health`
  - `xj-engine run --payload '...'`

### 默认引擎注册

- 本机默认引擎注册为 `Xj-engine`
- 注册表：
  - `~/.agents/engine_registry.json`
  - `~/.dsh/engine_registry.json`
- 全局 Agent 配置已声明默认引擎

### 2026-08-25（任务域 + 桥接层）

- 新增 `task.py`：任务生命周期动作
  - `task.complete`
  - `task.cancel`
  - `task.archive`
- 新增 `BridgeExecutor`：内核执行桥接分发，前端 adapter 外部注册
- 新增完成证据校验：
  - `complete` 必须携带非空 `evidence`
- 新增审计事件：
  - `task_complete_event`
  - `task_cancel_event`
  - `task_archive_event`
- 新增 `docs/bridge_contract.md`：桥接契约、adapter 接口、事件结构
- 扩展 `et_contract.py` Payload Schema：新增 `task` 块
- 扩展 Output Schema：新增 `task_result`
