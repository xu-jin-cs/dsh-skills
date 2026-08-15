# dsh-skills

面向 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 生态的轻量通用技能包。纯文件形态、零依赖、零安装脚本——放进技能发现根即生效。

Reusable, lightweight skills for the DeepSeek Harness ecosystem. Plain files, zero dependencies.

---

## 技能清单 / Skills

| 技能 | 说明 |
|------|------|
| [`parallel-dispatch`](./parallel-dispatch/SKILL.md) | 并行调度与子分身机制总规则。≥2 个无依赖子任务默认主动并行 spawn 子分身；规模轴（免评估轻分身 / S 档 / M·L 档引擎级）× 数量轴（2~5 subagent 扇出 / ≥10 workflow 编排）双维决策；含场景自动匹配表、最小探针、母体合并校验时点分层、禁止清单。 |
| [`archmap`](./archmap/SKILL.md) | 架构测绘 Agent（含 Python 引擎，自包含分发）。零参自动分流 full/lite；需求文本→精准影响面（文件/函数/路由级）；`diff` 零 LLM 行级影响面 + 导入闭包 + 测试选择 + 变更台账；`sync` 增量同步基线并刷新 01~09 报告；ETL 规则注册表项目级可覆盖。以确定性计算替代全库通读，显著节约 tokens。 |

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
2. **通用**：不含任何引擎私有逻辑，不绑定特定后端，他人的 engine 零冲突；
3. **自动触发**：触发词与场景写在 `description` 中，由 DSH 注入会话目录做场景匹配，命中即主动加载，无需显式指令。

## License

MIT
# 自动发布由 launchd WatchPaths 驱动，变更后约 60~90s 自动 commit+push
