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

DSH 按以下顺序发现技能（命中任意一级即生效）：

```
项目/.dsh/skills → 项目/.agents/skills → ~/.dsh/skills → ~/.agents/skills → bundled
```

**方式一：用户级（推荐，全局生效）**

```bash
git clone <this-repo> ~/dsh-skills
ln -s ~/dsh-skills/parallel-dispatch ~/.dsh/skills/parallel-dispatch
ln -s ~/dsh-skills/archmap ~/.dsh/skills/archmap   # 含 Python 引擎的技能
```

> `archmap` 额外需要一次依赖安装：`pip3 install -r ~/dsh-skills/archmap/requirements.txt`（`sentence-transformers` 为可选项，缺失时自动回退本地哈希向量化，功能可用）。详见 [`archmap/README.md`](./archmap/README.md)。

**方式二：项目级（仅当前项目）**

```bash
mkdir -p .dsh/skills
cp -r /path/to/dsh-skills/parallel-dispatch .dsh/skills/
```

无需重启：DSH 的技能 watcher 会热加载新技能。之后命中"并行 / 分身 / 批量 / 多任务"等场景即自动触发，也可显式 `/parallel-dispatch` 调用。

No restart needed — DSH's skill watcher hot-reloads new entries.

## 设计原则 / Principles

1. **轻量化**：规则类技能为单文件 `SKILL.md` + YAML frontmatter（`name` + `description`），无代码、无依赖；引擎类技能（如 `archmap`）自包含分发，依赖显式声明于各自 `requirements.txt`；
2. **通用**：不含任何引擎私有逻辑，不绑定特定后端，他人的 engine 零冲突；
3. **自动触发**：触发词与场景写在 `description` 中，由 DSH 注入会话目录做场景匹配，命中即主动加载，无需显式指令。

## License

MIT
