# Examples — 可独立运行的演示

每个 demo 带预期输出。CLI 类 demo 不需要任何 Agent 宿主；Agent 类 demo 标注宿主要求。

## 1. gate-switch：30 秒看清「机械门禁」（纯 CLI）

在仓库根目录执行：

```bash
python3 gate-switch/scripts/gate_switch.py --spec examples/gate-switch/demo_spec.json --set target=README.md
```

预期输出（节录）：

```json
{
  "verdict": "A",
  "gate": "demo_release_hygiene",
  "passed": ["README 至少 3 枚 shields.io badges: 命中=4 ...", "..."]
}
```

退出码 `0` = A 放行。然后做个实验：从 README.md 删掉两行 badge，重跑——判定变为 `B`，`violations` 里逐条列出缺了哪几项。**判定权在脚本，不在模型**——这就是 gate-switch 的全部要义。新场景 = 写一个新 spec JSON，引擎零改动（7 个检查原语见 `gate-switch/SKILL.md`）。

## 2. agent-eval：给本机全部技能打分出图（纯 CLI）

```bash
# 安装（含 matplotlib/numpy 依赖）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install agent-eval --with-deps# 只读采集 ~/.agents/skills 全部技能 → 9 维评分 → 雷达图 + 排名榜 + HTML 报告
python3 ~/.dsh/dsh-skills/agent-eval/scripts/eval_agents.py --mode generic
```

预期输出：

```
[采集] 有效技能 N 个 | 脚本 M 个 | ...
[排名] Top3：#1 xxx(87.3)、#2 yyy(84.1)、#3 zzz(81.9)｜阻断技能 K 个｜阻断短板 J 条
[交付] ~/Desktop/agent-skills-eval-<日期>
```

交付物：`images/agent_radar.png`（多维能力雷达）、`images/agent_rank.png`（综合排名榜）、`report.html`、`shards/*.json`（机器可读分片，支持 `--compare` 跨轮对比）。真实样本见本仓 [`agent-eval/images/`](../agent-eval/images/)。自定义技能根目录/关键技能清单/阈值：`--config your.json`（字段见脚本 `DEFAULT_CONFIG`）。

## 3. archmap：任意项目的架构测绘（Agent 宿主内调用）

archmap 在 Agent 宿主（DSH / Claude Code / Kimi Code）内运行。安装后在会话中：

```
/archmap <你的项目路径>          # 零参自动分流：无基线→full 全量初始化；有基线→lite 极简增量
/archmap <你的项目路径> +diff    # 行级差异影响面 + 导入闭包 + 测试选择（零 LLM）
/archmap <你的项目路径> +sync    # 增量同步基线并刷新 01~09 报告
```

预期产物：目标项目下生成 `archmap/` 目录——`full_index.json`（模块/API 资产）、`file_routes.json`（路由→文件映射）、`01~09` 系列报告与变更台账。`diff` 模式纯确定性计算，不消耗 LLM tokens。

## 4. parallel-dispatch：并行闸单刀双掷（纯 CLI 可见判定）

直接扳开关看机械判定（无需 Agent 宿主）：

```bash
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

预期输出：JSON 门禁声明。裸 shell 下它会拒绝扳动并列出原因（本 turn 任务清单未登记等）——**这不是报错，是门禁在工作**：并行扇出必须先登记任务清单、过基线校验，全程留痕 `~/.agents/logs/dispatch_switch.jsonl`。在 Agent 宿主内，≥2 个无依赖子任务会自动触发同一判定。

---

更多方法论：[《给 LLM 的口头承诺装上机械门禁》](../docs/mechanical-gates-for-llm.md)（[English](../docs/mechanical-gates-for-llm.en.md)）。
