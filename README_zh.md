# dsh-skills

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-orange)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/xu-jin-cs/dsh-skills)](https://github.com/xu-jin-cs/dsh-skills/commits/main)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-brightgreen)](README.md#compatibility)

**[English](README.md)** | **中文**

给 LLM 编码 Agent「装上机械门禁」的轻量通用技能包——能力评估、并行调度、架构测绘、PM 全流程工作流。纯文件形态、标准 `SKILL.md`、零依赖零锁定：DeepSeek Harness / Claude Code / Kimi Code / Codex 放进各自技能发现根即生效。

![Agent 能力雷达图（agent-eval 真实产出）](agent-eval/images/agent_radar.png)

## 为什么是这个仓库

多数技能「寄希望」于模型遵守指令；本仓把**判定权从模型移交给脚本**：spec 驱动的门禁引擎机械核验 Agent 声称的每个条件（A 放行 / B 阻断并列违例），并行扇出走审计留痕的单刀双掷开关，架构测绘用确定性计算替代全库通读。

主推钩子 = **[agent-eval](#技能清单)：Agent/Skills 专项能力评估**——只读采集本机全部技能 → 冻结基线 9 维评分 → 强弱三级判定（阻断/高风险/一般优化，带行动指引）→ 综合排名 → 深色科技风雷达图 + 排名榜 + HTML 报告。Agent 评估工具是当前行业缺口；RAG/ETL 引擎（[Xj-engine](#xj-engine)）作配套。

## 60 秒快速跑通

```bash
# 1. 一键安装全部四个技能（符号链接进技能发现根，DSH watcher 热加载即生效）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install --all --with-deps

# 2. 给本机全部技能打分 → 雷达图 + 排名榜 + HTML 报告
python3 ~/.dsh/dsh-skills/agent-eval/scripts/eval_agents.py --mode generic

# 3. 看机械门禁核验本仓自己的 README（在仓库根目录执行）
python3 gate-switch/scripts/gate_switch.py --spec examples/gate-switch/demo_spec.json --set target=README.md
```

真实产出样本已随仓附上：[雷达图](agent-eval/images/agent_radar.png) · [排名榜](agent-eval/images/agent_rank.png) · 更多见 [examples/](examples/)。

## 技能清单

| 技能 | 说明 |
|------|------|
| [`agent-eval`](./agent-eval/SKILL.md) | Agent/Skills 专项能力评估与可视化报告：只读采集 → 9 维评分（冻结基线+信号确定性加减）→ 强弱三级 → 综合排名 → 雷达图+排名榜+HTML 报告。 |
| [`archmap`](./archmap/SKILL.md) | 架构测绘 Agent（含 Python 引擎，自包含分发）。零参自动分流 full/lite；需求文本→精准影响面（文件/函数/路由级）；`diff` 零 LLM 行级影响面 + 导入闭包 + 测试选择 + 变更台账；`sync` 增量同步基线并刷新 01~09 报告。以确定性计算替代全库通读，显著节约 tokens。 |
| [`gate-switch`](./gate-switch/SKILL.md) | 通用概率执行门禁骨架（实证族 L2 引擎，零依赖）。治 LLM 三类顽疾：该做的没做 / 缺斤短两 / 伪造声称——把"声称 X 已满足"写成 spec JSON，引擎逐项机械核验，A 放行 / B 阻断列违例。7 检查原语 + 通用门禁实例 + L3 框架闸模板。新场景 = 写新 spec，引擎零改动。 |
| [`parallel-dispatch`](./parallel-dispatch/SKILL.md) | 并行调度与子分身机制总规则。≥2 个无依赖子任务默认主动并行 spawn；规模轴（轻分身 / S 档 / M·L 档引擎级）× 数量轴（subagent 扇出 / 分组 / workflow 编排）双维决策；场景自动匹配表、最小探针、母体合并校验，全部经 `dispatch_switch` 闸机械判定留痕。 |

> 四个技能均为仓库顶层目录，clone 即用或 `install --all` 一键安装。另有 57 技能合集包在 [`Xj-rules/store-package`](./Xj-rules/store-package/skills/)（`store-package-full.zip` / `-lite.zip`）。

## Xj-agent（PM 全流程工作流）

通用、自包含的 **PM 全流程研发调度骨架**（13 节点：pm_bootstrap→spm→pm_prd_confirm→dpm→[ui_designer ∥ test_lead_design]→fe→be→pm_quality_gate→test_lead_full→ops→qa→process_audit→retro），默认引擎接线为同仓库 [`Xj-engine`](./Xj-engine/)，环境变量可插拔。`Xj-agent/agents/` 随包分发 11 个角色技能（senior-pm-agent / detail-product-manager / ui-designer / frontend-development / backend-engineer / operation-deployment / test-lead / whitebox-coverage / api-test-engineer / ui-test-engineer / retro-skill-dispatcher），下载即拥有完整 pm 工作流。

```bash
pip install -r Xj-agent/pm/requirements.txt
python3 Xj-agent/pm/scripts/flow_kernel.py routes --rules Xj-agent/pm/flow.yml --node be
```

## Xj-engine

独立引擎（`engine.kernel.et` / CLI `xj-engine`）：ETL + 任务域 + 桥接执行层，本地数据库，`pip install -e .` 可安装。详见 [`Xj-engine/`](./Xj-engine/)。

## 兼容矩阵

| 目标环境 | 技能目录 | 说明 |
|---|---|---|
| DeepSeek Harness | `~/.dsh/skills` 或 `~/.agents/skills` | DSH 原生，支持 watcher 热加载 |
| Claude Code | `~/.claude/skills` | 标准 `SKILL.md` 格式，复制即用 |
| Kimi Code | `~/.agents/skills` | 标准 `SKILL.md` 格式，复制即用 |
| Codex | `~/.codex/skills` | 标准 `SKILL.md` 格式，复制后按环境调整路径 |

> 技能本体统一为标准 `SKILL.md` + YAML frontmatter；不同编辑器仅"技能发现根目录"不同。

## 安装

**一键安装（推荐，无需先 clone）**

```bash
# 列出全部技能
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- list

# 安装指定技能（默认符号链接进 ~/.dsh/skills，DSH watcher 热加载即生效）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap

# 全部技能 + 自动装依赖
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install --all --with-deps
```

**免 clone 一键下载**

```bash
# 只装 agent-eval（独立安装器：只下载该技能、装依赖、冒烟自检）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/agent-eval/install.sh | bash
```

- 57 技能商店包：[`store-package-full.zip`](./Xj-rules/store-package-full.zip) / [`store-package-lite.zip`](./Xj-rules/store-package-lite.zip)
- 整仓 zip：GitHub 页面 **Code → Download ZIP**，或 `curl -fsSLO https://github.com/xu-jin-cs/dsh-skills/archive/refs/heads/main.zip`

首次运行会自动把发布仓浅克隆到 `~/.dsh/dsh-skills`（可用 `DSH_SKILLS_HOME` 改位置），之后所有命令在本地仓执行。

**已 clone 仓库**

```bash
git clone https://github.com/xu-jin-cs/dsh-skills.git
cd dsh-skills
./install.sh                      # 交互式选择（列清单，输序号即可）
./install.sh archmap              # 安装指定技能
./install.sh --all                # 全部安装
./install.sh --copy --target ~/.claude/skills agent-eval   # 拷贝模式 + 换发现根
```

`scripts/dsh-skill.sh` 子命令：

| 命令 | 作用 |
|------|------|
| `list` | 列出发布仓全部技能 |
| `install <技能...\|--all>` | 安装（符号链接进发现根）；`--copy` 拷贝模式；`--target DIR` 切换目标根；`--with-deps` 自动装 requirements |
| `uninstall <技能...>` | 卸载 |
| `update` | git pull 同步上游（符号链接模式即时生效） |
| `doctor` | 体检：发现根、断链、SKILL.md 完整性、依赖环境 |

DSH 按以下顺序发现技能（命中任意一级即生效）：

```
项目/.dsh/skills → 项目/.agents/skills → ~/.dsh/skills → ~/.agents/skills → bundled
```

## 设计原则

1. **轻量化**：规则类技能为单文件 `SKILL.md` + YAML frontmatter，无代码、无依赖；引擎类技能自包含分发，依赖显式声明于各自 `requirements.txt`；
2. **通用**：不含任何引擎私有逻辑，不绑定特定后端；标准 `SKILL.md` 格式，可被 DSH / Claude Code / Kimi Code / Codex 等加载；
3. **自动触发**：触发词与场景写在 `description` 中，由宿主注入会话目录做场景匹配，命中即主动加载。

## 方法论

本仓库技能的治理哲学与 27 个实战案例复盘：[《给 LLM 的口头承诺装上机械门禁》](./docs/mechanical-gates-for-llm.md)（[English](./docs/mechanical-gates-for-llm.en.md)）——强制填充门元方法、L1/L2/L3 三档门禁、骨架冻结纪律、举一反三泛化闸。

## 上传必看：Git 发布前兼容性检查

> 任何变更上传到 Git 前，必须先按此清单检查；不通过禁止上传。

### 1. 路径必须可移植

- [ ] 禁止出现本机绝对路径：`/Users/<用户名>`、`C:\Users\...`、`/home/...`
- [ ] 路径统一使用相对路径 `./data/...`、`$HOME`、`Path.home()` 或环境变量
- [ ] 代码、文档、配置中不得出现私人目录名

### 2. 凭据必须清零

- [ ] 不得出现真实 `password` / `secret` / `token` / `api_key` / 私钥
- [ ] 新增 `.env.example`，真实配置通过环境变量注入

### 3. 私有依赖必须剥离

- [ ] 不得 import 外部私有项目模块
- [ ] 不得出现内部私有项目名、个人名
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

## License

[CC BY-NC-SA 4.0](LICENSE)（署名—非商业性使用—相同方式共享）：

- **禁止商用**：本仓库及其衍生品不得用于商业目的。
- **署名作者**：二次开发、转载、分发（全部或部分）必须标注作者 **xu-jin-cs**（https://github.com/xu-jin-cs/dsh-skills）。
- **相同方式共享**：二次开发产物须以同一协议发布。
