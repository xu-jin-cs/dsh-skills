# dsh-skills

面向 DeepSeek Harness / Claude Code / Kimi Code / Codex 等多 Agent 生态的轻量通用技能包。
纯文件形态、零依赖、零安装脚本——放进各自技能发现根即生效。

Reusable, lightweight skills for multiple AI coding agents: DeepSeek Harness, Claude Code, Kimi Code, Codex, and more. Plain files, zero dependencies.

---

## 兼容矩阵 / Compatibility

| 目标环境 | 技能目录 | 说明 |
|---|---|---|
| DeepSeek Harness | `~/.dsh/skills` 或 `~/.agents/skills` | DSH 原生，支持 watcher 热加载 |
| Claude Code | `~/.claude/skills` | 标准 `SKILL.md` 格式，复制即用 |
| Kimi Code | `~/.agents/skills` | 标准 `SKILL.md` 格式，复制即用 |
| Codex | `~/.codex/skills` | 标准 `SKILL.md` 格式，复制后按环境调整路径 |

> 技能本体统一为标准 `SKILL.md` + YAML frontmatter；不同编辑器仅“技能发现根目录”不同。
> DSH 专用 CLI（`dsh-skill.sh`）仍可用于 DSH 环境，其他环境直接复制技能目录即可。

---

## 上传必看：Git 发布前兼容性检查

> 以后任何项目上传到 Git 前，必须先按此清单检查；不通过禁止上传。

### 1. 路径必须可移植

- [ ] 禁止出现本机绝对路径：`/Users/<用户名>`、`C:\Users\...`、`/home/...`
- [ ] 路径统一使用相对路径 `./data/...`、`$HOME`、`Path.home()` 或环境变量
- [ ] 代码、文档、配置中不得出现私人目录名

### 2. 凭据必须清零

- [ ] 不得出现真实 `password` / `secret` / `token` / `api_key` / 私钥
- [ ] 已泄露的账号密码必须删除
- [ ] 新增 `.env.example`，真实配置通过环境变量注入

### 3. 私有依赖必须剥离

- [ ] 不得 import 外部私有项目模块，例如 `backend.*`、`etl.common.*`
- [ ] 不得出现内部私有项目名：`agent-harness`、`retro-skills-registry`、`Xj-rules`、个人名等
- [ ] 仓库必须能独立 `clone` 后按 README 安装并运行

### 4. 无关文件必须忽略

- [ ] `data/`、`__pycache__/`、`*.pyc`、`.DS_Store`、`node_modules/`、`*.tgz`、`*.zip` 不入库
- [ ] 数据库文件、模型权重、大体积临时文件不入库

### 5. 上传前必须执行校验

```bash
# 绝对路径扫描：应无命中
grep -RIn --exclude-dir=.git --exclude-dir=data -E '/Users/|C:\\Users|/home/' .

# 凭据扫描：不应出现真实密码/密钥
grep -RIn --exclude-dir=.git -iE 'password|secret|token|api[_-]?key' .

# 语法/配置校验
python3 -m py_compile $(find . -name '*.py' -not -path './.git/*')
```

- [ ] Python 语法检查通过
- [ ] YAML / JSON 解析通过
- [ ] 在全新目录 `git clone` 后，按 README 跑通最小示例

## 技能清单 / Skills

| 技能 | 说明 |
|------|------|
| [`parallel-dispatch`](./parallel-dispatch/SKILL.md) | 并行调度与子分身机制总规则。≥2 个无依赖子任务默认主动并行 spawn 子分身；规模轴（免评估轻分身 / S 档 / M·L 档引擎级）× 数量轴（2~5 subagent 扇出 / ≥10 workflow 编排）双维决策；含场景自动匹配表、最小探针、母体合并校验时点分层、禁止清单。 |
| [`archmap`](./archmap/SKILL.md) | 架构测绘 Agent（含 Python 引擎，自包含分发）。零参自动分流 full/lite；需求文本→精准影响面（文件/函数/路由级）；`diff` 零 LLM 行级影响面 + 导入闭包 + 测试选择 + 变更台账；`sync` 增量同步基线并刷新 01~09 报告；ETL 规则注册表项目级可覆盖。以确定性计算替代全库通读，显著节约 tokens。 |
| [`gate-switch`](./gate-switch/SKILL.md) | 通用概率执行门禁骨架（实证族 L2 引擎，零依赖）。治 LLM 三类顽疾：该做的没做 / 缺斤短两 / 伪造声称——把"声称 X 已满足"写成 spec JSON，引擎逐项机械核验，A 放行 / B 阻断列违例，判定权从模型移交脚本。7 检查原语（file_exists/json_field/glob_count/grep_count/mtime_after/script_exit 等），自带 8 个通用门禁实例（验收 verdict、测试证据、部署准入、模式分流等）+ L3 框架闸模板。新场景 = 写新 spec，引擎零改动。与 parallel-dispatch 的 dispatch_switch（路由族）互补。 |

## Xj-agent（PM 全流程工作流）

通用、自包含的 **PM 全流程研发调度骨架**（13 节点：pm_bootstrap→spm→pm_prd_confirm→dpm→[ui_designer ∥ test_lead_design]→fe→be→pm_quality_gate→test_lead_full→ops→qa→process_audit→retro），默认引擎接线为同仓库 [`Xj-engine`](./Xj-engine/)（`xj_engine.kernel.et` / `xj-engine` CLI），引擎可插拔。**不捆绑具体角色技能**：各节点角色执行能力由适配方自行接线对应技能/Agent。含：

- `pm/SKILL.md` — 流程入口与引擎接线说明
- `pm/flow.yml` — 13 节点编排（节点拓扑 / 分支 / 状态机 / 交付物模板）
- `pm/requirements.txt` — 脚本运行依赖（PyYAML / jsonschema）
- `pm/scripts/flow_kernel.py` — 节点流转内核（规则全入参，success 回执才流转）
- `pm/scripts/engine_preflight.sh` — 引擎健康检查（默认 `xj-engine health`）
- `pm/scripts/verify_experience_writeback.sh` — 经验固化机械校验

```bash
pip install -r Xj-agent/pm/requirements.txt
# 查看节点出口
python3 Xj-agent/pm/scripts/flow_kernel.py routes --rules Xj-agent/pm/flow.yml --node be
```


## 安装 / Install

**一键安装（推荐，无需先 clone）/ One-liner**

```bash
# 列出全部技能
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- list

# 安装指定技能（默认符号链接进 ~/.dsh/skills，DSH watcher 热加载即生效）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap

# 安装全部技能 + 自动装依赖
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install --all --with-deps
```

首次运行会自动把发布仓浅克隆到 `~/.dsh/dsh-skills`（可用 `DSH_SKILLS_HOME` 改位置），之后所有命令在本地仓执行。

**已 clone 仓库 / Already cloned**

仓库根目录自带安装入口，无需记忆任何命令：

```bash
git clone https://github.com/xu-jin-cs/dsh-skills.git
cd dsh-skills

./install.sh                      # 交互式选择（列清单，输序号即可）
./install.sh archmap              # 安装指定 agent（引擎类技能）
./install.sh parallel-dispatch    # 安装指定规则（规则类技能）
./install.sh archmap parallel-dispatch   # 一次装多个
./install.sh --all                # 全部安装
```

支持 `--copy`（拷贝模式）、`--target DIR`（换发现根，如项目级 `.dsh/skills`）。本质是 `scripts/dsh-skill.sh` 的友好外壳：

`scripts/dsh-skill.sh` 子命令：

| 命令 | 作用 |
|------|------|
| `list` | 列出发布仓全部技能 |
| `install <技能...\|--all>` | 安装（符号链接进发现根）；`--copy` 拷贝模式；`--target DIR` 切换目标根（如项目级 `.dsh/skills`）；`--with-deps` 自动装 requirements |
| `uninstall <技能...>` | 卸载 |
| `update` | git pull 同步上游（符号链接模式即时生效） |
| `doctor` | 体检：发现根、断链、SKILL.md 完整性、依赖环境 |

DSH 按以下顺序发现技能（命中任意一级即生效）：

```
项目/.dsh/skills → 项目/.agents/skills → ~/.dsh/skills → ~/.agents/skills → bundled
```

**手动安装（不用 CLI）**

```bash
git clone https://github.com/xu-jin-cs/dsh-skills.git ~/dsh-skills
ln -s ~/dsh-skills/parallel-dispatch ~/.dsh/skills/parallel-dispatch
ln -s ~/dsh-skills/archmap ~/.dsh/skills/archmap   # 含 Python 引擎的技能
pip3 install -r ~/dsh-skills/archmap/requirements.txt  # 可选，缺失时自动回退本地哈希向量化
```

无需重启：DSH 的技能 watcher 会热加载新技能。之后命中"并行 / 分身 / 批量 / 多任务"等场景即自动触发，也可显式 `/parallel-dispatch` 调用。

No restart needed — DSH's skill watcher hot-reloads new entries.

## 设计原则 / Principles

1. **轻量化**：规则类技能为单文件 `SKILL.md` + YAML frontmatter（`name` + `description`），无代码、无依赖；引擎类技能（如 `archmap`）自包含分发，依赖显式声明于各自 `requirements.txt`；
2. **通用**：不含任何引擎私有逻辑，不绑定特定后端；标准 `SKILL.md` 格式，可被 DSH / Claude Code / Kimi Code / Codex 等加载；他人的 engine 零冲突；
3. **自动触发**：触发词与场景写在 `description` 中，由 DSH 注入会话目录做场景匹配，命中即主动加载，无需显式指令。

## 方法论 / Methodology

本仓库技能的治理哲学与 27 个实战案例复盘：[《给 LLM 的口头承诺装上机械门禁》](./docs/mechanical-gates-for-llm.md)（[English Version](./docs/mechanical-gates-for-llm.en.md)）——强制填充门元方法、L1/L2/L3 三档门禁、骨架冻结纪律、举一反三泛化闸。

## License

MIT
# 自动发布由 launchd WatchPaths 驱动，变更后约 60~90s 自动 commit+push

---

# dsh-skills (English)

Reusable, lightweight skills for multiple AI coding agents: DeepSeek Harness, Claude Code, Kimi Code, Codex, and more. Plain files, zero dependencies — drop them into the skill discovery root of your agent and they work.

### Compatibility

| Agent | Skill directory |
|---|---|
| DeepSeek Harness | `~/.dsh/skills` or `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Kimi Code | `~/.agents/skills` |
| Codex | `~/.codex/skills` |

## Skills

| Skill | Description |
|-------|-------------|
| [`parallel-dispatch`](./parallel-dispatch/SKILL.md) | Master rules for parallel dispatch & sub-agent clones. ≥2 independent subtasks trigger parallel fan-out by default; two-axis decision matrix (scale: light clone / task-breakdown / engine-level × count: subagent / grouped / workflow); includes scene auto-matching, minimal probe, merge checkpoints, and a mechanical SPDT-style `dispatch_switch` (A/B verdict, no handwritten decisions, full audit log). |
| [`archmap`](./archmap/SKILL.md) | Architecture cartography agent (self-contained Python engine). Zero-arg full/lite auto-routing; requirement text → precise impact analysis (file/function/route level); `diff` mode: zero-LLM line-level impact + import-closure + test selection + change ledger; `sync` incremental baseline refresh. Deterministic computation instead of full-repo reading — massive token savings. |
| [`gate-switch`](./gate-switch/SKILL.md) | Universal probabilistic-execution gate (evidence-family L2 engine, zero deps). Cures three LLM chronic failures: skipped steps / half-done checklists / fabricated "done" claims. Write what must be true as a spec JSON; the engine mechanically verifies each check — A passes, B blocks with violations as the reason. Judgment moves from the model to a script. 7 frozen check primitives (file_exists / json_field / glob_count / grep_count / mtime_after / script_exit …), 8 ready-made generic gates (acceptance verdict, test evidence, deploy admission, mode routing, …) + an L3 framework-gate template. New scenario = new spec, zero engine changes. Complements `dispatch_switch` (routing family). |

## Install

**One-liner (recommended, no clone needed)**

```bash
# List all skills
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- list

# Install a specific skill (symlinked into ~/.dsh/skills, hot-reloaded by DSH's watcher)
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install gate-switch

# Install everything + auto-install dependencies
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install --all --with-deps
```

First run shallow-clones the repo to `~/.dsh/dsh-skills` (override with `DSH_SKILLS_HOME`); all later commands run locally.

**Already cloned**

```bash
git clone https://github.com/xu-jin-cs/dsh-skills.git
cd dsh-skills
./install.sh                # interactive picker
./install.sh archmap        # install a specific skill
./install.sh --all          # everything
```

CLI subcommands (`scripts/dsh-skill.sh`): `list` / `install` (`--copy`, `--target DIR`, `--with-deps`) / `uninstall` / `update` / `doctor`.

DSH discovers skills in order (first hit wins):

```
<project>/.dsh/skills → <project>/.agents/skills → ~/.dsh/skills → ~/.agents/skills → bundled
```

No restart needed — DSH's skill watcher hot-reloads new entries.

## Principles

1. **Lightweight** — rule-type skills are a single `SKILL.md` + YAML frontmatter, no code, no deps; engine-type skills (archmap, gate-switch) are self-contained with explicit `requirements.txt`.
2. **Universal** — no private engine logic, no backend lock-in; standard `SKILL.md` format works with DSH, Claude Code, Kimi Code, Codex, and more; zero conflicts with your own engine.
3. **Auto-trigger** — triggers live in each skill's `description`; DSH injects them into the session catalog for scene matching.

## Methodology

The governance philosophy behind these skills, plus a 27-case battle retrospective: [Mechanical Gates for LLM's Verbal Promises](./docs/mechanical-gates-for-llm.en.md) ([中文版](./docs/mechanical-gates-for-llm.md)) — the Mandatory-Completion Gate meta-method, L1/L2/L3 gate levels, skeleton-freeze discipline, and the "1 proven case + N named siblings" generalization gate.

## License

MIT
