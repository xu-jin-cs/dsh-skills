# dsh-skills 上传变更记录

> 本文件记录 dsh-skills 仓库每次对外上传/同步的主要变更。
> 之后每次上传前必须同步更新本文件。

## 2026-08-25 · Xj-agent（PM 全流程工作流）新增

### 7. Xj-agent（公开分发骨架版）

- 新增 `Xj-agent/` 资源目录，与 `Xj-engine` / `Xj-rules` 同级，承载通用 PM 全流程工作流。
- 内容：
  - `pm/SKILL.md` — 流程入口与引擎接线说明
  - `pm/flow.yml` — 13 节点编排（节点拓扑 / 分支 / 状态机 / 交付物模板）
  - `pm/readme.md` — 架构说明
  - `pm/scripts/flow_kernel.py` — 节点流转内核（规则全入参）
  - `pm/scripts/engine_preflight.sh` — 引擎健康检查（默认 `xj-engine health`）
  - `pm/scripts/verify_experience_writeback.sh` — 经验固化机械校验
- 引擎接线：默认指向同仓库 `Xj-engine`（`xj_engine.kernel.et` / CLI `xj-engine`），通过环境变量可插拔（`ENGINE_HEALTH_CMD` / `ENGINE_START_CMD` / `PM_HARNESS_SYNC_CMD`）。
- 已做兼容性清理（对齐 Xj-rules/Xj-engine 标准）：
  - 无 `/Users/xujin` 绝对路径
  - 无 `agent-harness` / `retro-skills-registry` / `learned-skills` / `gate-switch` 私有依赖与私有技能引用
  - 无 `output_delivery/` 真实项目产物、无 `archive_*` 历史归档
  - 无 `__pycache__` / `*.pyc` / `.DS_Store`
- 校验：`flow.yml` YAML 解析通过（14 agents / 17 状态跃迁），`flow_kernel.py` `py_compile` 通过。

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

### 6. Xj-engine 开箱即用剥离确认（2026-08-25 追加）

- 确认引擎剥离到位：无 `/Users/xujin` 固定路径、无 `backend.`/`agent-harness` 私有依赖 import
- `database.py` 默认库路径用 `Path(__file__)` 相对定位（跟随安装位置），非固定绝对路径，且可用 `XJ_ENGINE_DB_URL` 覆盖
- `__pycache__`/`*.pyc`/`.DS_Store` 已被 `.gitignore` 忽略，不入库
- 完整可安装：`pyproject.toml`（`pip install -e .`）+ CLI `xj-engine` + `kernel.et` 入口 + 必备文件全齐
- 验证：`kernel.et` import 成功、`xj-engine health` 正常运行
- 达到"别人拿到开箱即用"标准
