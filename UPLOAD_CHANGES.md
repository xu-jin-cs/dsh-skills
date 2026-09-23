# dsh-skills 上传变更记录

> 本文件记录 dsh-skills 仓库每次对外上传/同步的主要变更。
> 之后每次上传前必须同步更新本文件。

## 2026-09-23（下午·三轮）· gate-switch / parallel-dispatch 全量源码回归公开 + 脱敏 + 协议更换

### 1. 裁定变更

- 2026-09-23 用户裁定：两技能全量源码直接公开（**覆盖 08-25 打包分发裁定**）。`.gitignore` 撤销整目录屏蔽，改为仅排除本地运行态：`gate-switch/runtime/`（会话判定状态）、`gate-switch/council/`（会诊报告）、`gate-switch/data/calibration_examples.json`（校准例句含真实会话引用）——非源码且有泄露面，不入库。

### 2. 脱敏口径（功能保留型）

- **引擎补丁**：`gate_switch.py` 检查原语的路径类字段统一 `os.path.expanduser`（`~` 展开），`script_exit` 的 cmd 执行前 `os.path.expandvars`（`$HOME` 展开，规避 shell 单引号不展开问题）——对既有绝对路径幂等，规格从此可跨机移植。
- **字段级改写**：34 个 spec 共 86 行——path/desc/label 字段 `/Users/xujin`→`~`，cmd 字段→`$HOME`；grep 探测签名 pattern（其职责即检出 `/Users/` 泄露）**不动**。
- **脚本**：`direct_db_write_scan.py` ROOT、`plan_select_contract_check.py` REAL_POOL 改 `expanduser`（前者支持 `AGENT_HARNESS_ROOT` 环境变量覆盖）；`trigger_signals.json` 2 处注入指令同步改写。
- **复扫**：两目录可入库文件 `/Users/xujin` 零命中；密钥/邮箱/内网 IP 零命中（127.0.0.1 本机引擎地址属文档级保留）。

### 3. 回归实证

- 107 个 spec 改写前后判定逐一对比 **diff 为零**；reform_gate（script_exit+expandvars 通道）与 demo 闸复跑判 A；`py_compile` 全通过；trigger_signal_scan 注入指令复跑正常。

### 4. 协议更换：MIT → CC BY-NC-SA 4.0

- 用户裁定口径：**禁止商用；二次开发与转载必须署名作者（xu-jin-cs）；衍生品保持同协议**。CC BY-NC-SA 4.0 三条全中（OSI 系协议无禁商用条款，故不选 MIT/Apache）。
- `LICENSE` 全文替换为官方 legalcode；README 双语 License 节改写为三条白话义务 + badge 换静态 CC BY-NC-SA。

### 5. 功能用途标注

- 新建 `gate-switch/README.md`、`parallel-dispatch/README.md`（功能/用途/快速开始/协议四点式）；主 README 双语技能表链接改回顶层目录（两技能回归一等公民），quickstart 与 examples 演示路径同步改回顶层。

### 6. 留痕

- 计划闸单路径豁免：`EXEMPTION-20260923b_publish_full_source.md`（原样公开=违门禁、盲 sed=毁探测签名且闸失效、继续打包=被本轮裁定否决，唯一合规路径=引擎补丁+字段级脱敏）；并行闸掷 B 串行备案。

## 2026-09-23（下午·二轮）· 一键下载/一键安装全技能不断链

### 1. 安装器商店包回退（dsh-skill.sh）

- 用户要求：上传的每个项目都要支持一键下载、一键安装。实测断点：08-25 裁定后 gate-switch/parallel-dispatch 全量源码不在 git 跟踪内，全新 clone 上 `install --all` 对二者报「仓库内缺少目录」。
- 修复：`scripts/dsh-skill.sh` 的 `install_one` 增加回退源——顶层目录缺失时回退 `Xj-rules/store-package/skills/<name>`，输出标注分发通道。`install.sh` 为透传外壳，无需改动。
- 计划闸：单路径豁免留痕 `~/.agents/logs/plan_select/EXEMPTION-20260923_oneclick_install.md`（重新公开源码违反 08-25 裁定、新建 zip 通道与既有商店包重复，唯一合规路径=安装器回退）；并行闸掷 B 串行备案。

### 2. agent-eval 依赖声明补齐

- 新增 `agent-eval/requirements.txt`（matplotlib/numpy），接通 `--with-deps` 一键装依赖（skills.json 既有 deps 声明现在有实体文件对齐）。agent-eval 另有独立 `install.sh` 支持免 clone curl 直装。

### 3. 实证记录

- 本地全新 clone：`install --all --with-deps` 四技能全成（两顶层 + 两商店包通道），`doctor` 全绿，交互式 `install.sh` 选 a 全量安装通过。
- push 后 GitHub 端到端终验：`curl|bash` 自举（DSH_SKILLS_HOME 隔离）+ agent-eval 独立 install.sh（AGENT_EVAL_TARGET 隔离）。

### 4. README 双语

- 恢复 `install --all --with-deps` 口径（商店包通道自动识别）；新增「免 clone 一键下载」段（agent-eval 独立安装器 / 商店包 zip / 整仓 zip）。

## 2026-09-23 · 三技能归位复核 + 发布前最小脱敏 + README 双语地基

### 1. agent-eval 符号链接归位（publish_sync_check P1 FAIL 修复）

- 铁律口径：对外分发技能真源在 `~/dsh-skills` 仓库，`~/.dsh/skills` 与 `~/.agents/skills` 两个用户根必须是指向仓库的符号链接，禁止双副本漂移。
- 实测：`~/.agents/skills/agent-eval` 为实目录、`~/.dsh/skills/agent-eval` 缺失（archmap/parallel-dispatch 既为符号链接，天然同步）。`diff -rq` 实证实目录与仓库内容全等后，实目录归档至 `~/.agents/archive/agent-eval_20260923`（铁律7 白名单通道），双根各建 symlink 指向仓库。
- 归位后 publish_sync_check P1 通过（P2/P3 随本轮 push 复核）。

### 2. 发布前最小脱敏（BLOCK 级违例清零）

- 背景：09-19 agent-eval 入仓、09-21/22 archmap SKILL.md 更新经 auto-publish 直接外发，跳过脱敏复核，公开仓残留本机绝对路径。
- 清理：`archmap/SKILL.md`（rest-api-doc-standard 引用）与 `parallel-dispatch/SKILL.md`（start.sh 提示）两处 `/Users/xujin` 绝对路径改为 `~` 家目录相对形式（本机功能等价）；`archmap/SKILL.md.bak_20260921` 移出仓库至仓外（对齐 09-15 备份不入仓口径）。
- 复扫：三技能目录（agent-eval/archmap/parallel-dispatch）`/Users/xujin` 零命中；密钥/内网 IP/私人邮箱零命中。
- WARN 级残留保留：`agent-harness`/`retro-skills-registry` 命名引用（home 相对路径，符号链接单副本下中性化会改写本地运行文档与脚本），沿用 08-30 历史口径保留，是否另起全量中性化轮次交用户裁定。另发现 `gate-switch/specs/*.json` 与 `council/` 存历史路径残留（非本轮三技能范围），一并留记录待裁定。

### 3. README 双语地基（推广前置，对齐推广自检清单）

- README.md 重构为英文主版、新建 README_zh.md 中文版，顶部互链。
- 第一屏：badges（License / last-commit / Python 3.10+ / SKILL.md 格式）+ 一句话定位 + agent-eval 雷达图演示 + 60 秒快速跑通三命令。
- 差异化卖点显性化：agent-eval 能力评估拎为主推钩子，Xj-engine 作配套；技能清单表补齐 agent-eval（09-19 入仓后表格漏更）；移除 README 内 launchd 运维内部备注。
- 新增 `examples/`：`gate-switch/demo_spec.json`（核验本仓 README 的演示闸，已实测判 A）+ agent-eval / archmap / parallel-dispatch 演示各带预期输出。

### 4. 闸链留痕

- 计划闸：POOL-20260923_dsh_publish_promote.md（plan_select chosen=方案一 S=7）；推演：deep_analysis/dsh_skills_publish_promote-20260923.md；收益闸/逻辑闸：reform_blocks、logic_blocks/dsh_skills_sync_promote_20260923.md 均判 A；并行闸：dispatch_switch 掷 B 串行（同一 git 仓库产物耦合，理由已备案）。

### 5. 补：README/examples 与 2026-08-25 打包裁定对齐

- 发现：`.gitignore` 第 11-12 行（`/gate-switch/`、`/parallel-dispatch/`）+ commit 80b4693 证实 08-25 用户裁定——两技能全量源码停止公开跟踪，统一经 `Xj-rules/store-package` 分发；但 README 技能表链接、quickstart 命令、`install --all` 文案仍指向仓内不存在路径（08-25 遗留不一致）。
- 修复：README 双语技能表两技能链接改指 `Xj-rules/store-package/skills/` 并加 📦 分发说明；quickstart 第 1/3 命令改为可跑通形式（`install agent-eval archmap --with-deps`；demo 闸走包内 `gate_switch.py`，已实测判 A）；examples/ 两个演示路径同步修正。
- 更正本节第 2 条措辞：`gate-switch/specs/*.json` 与 `council/` 的 `/Users/xujin` 命中位于**未被 git 跟踪的本地真源**（.gitignore 拦截），从未公开，非公开仓残留。
- 遗留建议（交用户裁定，未动）：`skills.json` 清单含两个未跟踪技能，`install --all` 在全新 clone 上对二者报「仓库内缺少目录」；建议安装器增加包内路径回退或清单标注分发通道。

## 2026-09-15 · 发布前脱敏复核（milvus 改造前冻结版上传）

### 1. 全仓敏感信息复合扫描

- 扫描口径：`/Users/xujin` 绝对路径、`retro-skills-registry` 私有命名、私钥/密钥值、内网 IP、私人邮箱，全仓（含 shell/py/md/yaml）grep。
- 结论：无密钥值、无内网 IP、无私人邮箱；真实残留 3 处已全部清理（见下）。

### 2. 三处真实残留清理

- `archive/backup_20260820/`（12 个 archmap SKILL.md 历史 .bak，含 `/Users/xujin` 绝对路径与私有命名）——整目录移出发布仓（git 历史可溯，本地真源备份保留在仓外）。
- `scripts/auto-publish.sh`：`REPO="/Users/xujin/dsh-skills"` 硬编码改为仓根自定位（脚本位于 `<repo>/scripts/` 下向上推导），功能等价、`bash -n` 校验通过。
- `archmap/archmap_agent/etl_rule_registry.py`：规则 ETL-ORCH-07 的 consumers 字段私有目录名改为中性描述「retro 复盘经验入库链路（GENERATE 落库）」。

### 3. 复扫结论

- 清理后复合模式复扫：真实残留零命中；仅存留本台账与 README 发布检查清单中的合规规则/台账文本（与 8/25、8/30 两轮发布口径一致）。

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
