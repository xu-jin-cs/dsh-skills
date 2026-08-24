# dsh-skills 上传变更记录

> 本文件记录 dsh-skills 仓库每次对外上传/同步的主要变更。
> 之后每次上传前必须同步更新本文件。

## 2026-08-25

### 1. README 定位调整

- 从“仅 DeepSeek Harness”改为“多 Agent 生态兼容”
- 新增兼容矩阵：DeepSeek Harness / Claude Code / Kimi Code / Codex
- 新增“上传必看：Git 发布前兼容性检查”

### 2. Xj-rules（替代旧 plugins/Xj-rules）

- 删除旧 `plugins/Xj-rules` DSH 专用插件
- 新增 `Xj-rules/` 资源目录，内容来自 kimicode 清理版
- 包含：
  - `store-package/`：57 个独立技能（规则 + 46 闸 + gate-switch 引擎）
  - `store-package-full.zip`
  - `store-package-lite.zip`
  - `gumroad-listing-en.md`
  - `covers/`
- 已做兼容性清理：
  - 无 `/Users/xujin` 绝对路径
  - 无真实密码/密钥
  - 无 `retro-skills-registry` / `agent-harness` 私有依赖
  - 无 `__pycache__` / `*.pyc` / `.DS_Store`

### 3. Xj-engine（独立引擎）

- 从 `agent-harness/backend/engine` 提取为独立引擎
- 新增 `Xj-engine/xj_engine/` Python 包
- 移除 `backend.database` 依赖，新增本地 `database.py`
- 移除 `backend.services.test_skills` 依赖，`skills.py` 改为 stub
- `claude_engine.py` 的 `anthropic` 改为可选依赖
- 新增 `pyproject.toml`，支持 `pip install -e .`
- 新增 CLI：`xj-engine health` / `xj-engine run`
- 新增 `.env.example`：`XJ_ENGINE_DB_URL` / `AGENT_ENGINE_SECRET`
- 默认引擎已注册到：
  - `~/.agents/engine_registry.json`
  - `~/.dsh/engine_registry.json`
  - `~/.dsh/AGENTS.md`
  - `~/.agents/AGENTS.md`
  - `~/.claude/CLAUDE.md`
  - `~/.codex/AGENTS.md`

### 4. Xj-engine 任务域与桥接层（2026-08-25 追加）

- 新增 `task_complete` / `task_cancel` / `task_archive`
- 新增完成证据校验
- 新增审计事件类型
- 新增 `BridgeExecutor` 桥接执行层
- 新增 `docs/bridge_contract.md`

### 5. Xj-engine 重新生成（以本地引擎为真源）

- 本地引擎 `agent-harness/backend/engine` 已补齐任务域和桥接层
- 以本地引擎为真源重新生成 `Xj-engine/` standalone 副本
- 副本包含：
  - `task.py`（task_complete / task_cancel / task_archive）
  - `BridgeExecutor`
  - `docs/bridge_contract.md`
  - `et_contract.py` 新增 `task` 块和 `task_result`
  - `audit.py` 新增任务审计事件
  - `kernel.py` 接入任务动作执行
- 已通过本地引擎验证和 standalone 副本验证
