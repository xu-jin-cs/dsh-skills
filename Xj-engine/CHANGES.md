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
