# dsh-skills 上传变更记录

> 本文件记录 dsh-skills 仓库每次对外上传/同步的主要变更。
> 之后每次上传前必须同步更新本文件。

## 2026-08-30 · archmap 发布刷新 + 上架运营物料移出公开仓

### 1. archmap 技能与真源全量同步

- 来源：`~/.agents/skills/archmap`（真源）rsync 全量同步至 `archmap/`（排除 `.pytest_cache`/`__pycache__`），两目录内容一致。

### 2. archmap/README.md 重写

- 新版补齐：作用范围（适用/不适用边界）、五模式能力矩阵、一条命令远程安装（`curl -fsSL .../scripts/dsh-skill.sh | bash -s -- install archmap --with-deps`）、使用方式、产物清单、依赖与离线说明、下游生态对接。
- 移除旧版本机绝对路径（`/Users/xujin/.agents/...`），发布版无私有路径残留。

### 3. 商店上架文案移出公开仓

- `Xj-rules/gumroad-listing-en.md`、`Xj-rules/mianbaoduo-listing-zh.md` 移至仓外 `~/dsh-skills-listing/` 本地维护（上架通用版用运营物料，不公开发布）。
- `Xj-rules/README.md` 同步清理上架文案引用，并加注"运营物料不入本仓"说明。

### 4. archmap 私有路径残留清零

- `SKILL.md` 示例与包装脚本路径、expert-router 引用，`archmap_agent/tests/` 3 个测试文件的运行注释与 `AGENT_HARNESS_ROOT` 默认值，全部改为中性路径（`/path/to/project`、`~/.dsh/skills/archmap/`、`Path.home()` 推导）。
- 全仓 `archmap/` 目录 `/Users/xujin` 残留扫描零命中。

## 2026-08-29 · 治理规则同步（公共包路径范围补 `~/.agents/AGENTS.md`）

### 9. 08_governance_rules.md 增量同步

- 来源：本地 IDE 配置 `~/.agents/rules/08_governance_rules.md` 变更，副本同步至 `Xj-rules/store-package/skills/governance-archive/references/08_governance_rules.md`，本地文件未改动、不影响当前使用。
- 变更内容：公共包（GitHub 可分发）路径范围新增 `~/.agents/AGENTS.md`（2026-08-29 起取代 `~/.dsh/AGENTS.md`）。
- 兼容性剥离：保留仓库中性命名（`retro-registry` / `_retro_experiences_example.json` 示例名），未带入本地环境私有命名；私有残留扫描（`/Users/xujin`、`retro-skills-registry`、`CLAUDE.md` 等）零命中。

## 2026-08-25 · 任务完成方式定稿（撤除 hook/种入闸，仅 `todo_write status:completed`）

### 8. 任务完成 hook + 种入闸（已撤除）

- **终裁（用户裁定）**：任务完成 = `todo_write` 将该任务 `status` 置为 `"completed"`，DSH 面板即显示完成。
- 已撤除以下机制（不再分发/使用）：
  - `Xj-engine/engine/task_complete_hook.py`（完成埋点 hook）
  - CLI `xj-engine complete`
  - `Xj-engine/gate/`（attached_complete / task_complete_attach_gate / check_attached_complete / task_complete_plant_gate）
  - 本地 `attached_plan.py --mode complete` 与相关闸 spec/脚本
- 引擎 `task.complete` 降为**可选的权威记录**，非完成必需路径。
- **简化结论**：完成任务不需要 hook、不需要引擎、不需要复杂闸机制——只需 `todo_write` 置 `status:"completed"`。

## 2026-08-25 · Xj-agent（PM 全流程工作流）新增

### 7. Xj-agent（公开分发骨架版）

- 新增 `Xj-agent/` 资源目录，与 `Xj-engine` / `Xj-rules` 同级，承载通用 PM 全流程工作流。
- 内容：
  - `pm/SKILL.md` — 流程入口与引擎接线说明
  - `pm/flow.yml` — 13 节点编排（节点拓扑 / 分支 / 状态机 / 交付物模板）
  - `pm/readme.md` — 架构说明
  - `pm/requirements.txt` — 脚本运行依赖（PyYAML / jsonschema）
  - `pm/scripts/flow_kernel.py` — 节点流转内核（规则全入参）
  - `pm/scripts/engine_preflight.sh` — 引擎健康检查（默认 `xj-engine health`）
  - `pm/scripts/verify_experience_writeback.sh` — 经验固化机械校验
- 引擎接线：默认指向同仓库 `Xj-engine`（`engine.kernel.et` / CLI `xj-engine`），通过环境变量可插拔（`ENGINE_HEALTH_CMD` / `ENGINE_START_CMD` / `PM_HARNESS_SYNC_CMD`）。
- **角色集收敛为 11 个（2026-08-25 用户裁定）**：`flow.yml` 的 `invoked_skills` 由 18 收敛到 **11 个去重角色**——`senior-pm-agent` / `detail-product-manager` / `ui-designer` / `frontend-development` / `backend-engineer` / `operation-deployment` / `test-lead` / `whitebox-coverage` / `api-test-engineer` / `ui-test-engineer` / `retro-skill-dispatcher`。剔除并入：archmap（非 pm 角色）、acceptance-manager（验收→test-lead）、sv-supervisor（审批→PM/引擎）、task-breakdown（拆解→spm）、test-executor（执行→test-lead）、process-audit（合规→test-lead）、retro-subagent（复盘→retro-skill-dispatcher）。
- 新增 `pm/requirements.txt`（PyYAML / jsonschema）声明脚本运行依赖，使 `flow_kernel.py` 可开箱运行。
- **角色 agent 集分发（2026-08-25 用户裁定）**：`Xj-agent/agents/` 随包分发 pm 的 **11 个角色技能**，下载即拥有完整 pm 工作流——`senior-pm-agent` / `detail-product-manager` / `ui-designer` / `frontend-development` / `backend-engineer` / `operation-deployment` / `test-lead` / `whitebox-coverage` / `api-test-engineer` / `ui-test-engineer` / `retro-skill-dispatcher`。每个均已去敏（无 agent-harness / retro-skills-registry / gate-switch / /Users/xujin 绝对路径），剥离 `learned-skills/` 内部复盘与经验文档；python 脚本语法校验通过、全量私有残留扫描零命中。
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
- 新增 `Xj-engine/engine/` Python 包
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
