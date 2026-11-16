# parallel-dispatch — 并行调度与子分身机制总规则（中文说明）

> 单刀双掷开关 + 总规则：**掷 A 并行扇出 / B 串行**——带证据链，不凭感觉。
>
> [English](README.md) · [← 返回 dsh-skills](../README.md)

## 是什么 / 治什么痛点

多任务场景朝两个方向坏掉：全串行（慢、浪费）或盲扇出（混乱、上下文互染、合并冲突）。parallel-dispatch 装上机械判定点：

- 任何 **≥2 个子任务**的场景必须输出 `[PARALLEL-GATE]` 声明——无触发词依赖，强制触发。
- **`scripts/dispatch_switch.py`** 机械掷点：**A 并行扇出 / B 串行**（B 判定必须带依赖链理由，留空即违规），全程 JSONL 留痕。
- 掷 A 前置三道闸：任务清单登记、统一上下文基线、探针实证——**禁止盲扇出**。
- 任务量量纲唯一化：只数**文件数量**（禁用小时/体感）。

## 30 秒安装

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install parallel-dispatch
```

已 clone 本仓：`./install.sh parallel-dispatch`。

## 5 分钟上手

裸 shell 扳一次开关（无需 Agent 宿主）：

```bash
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

预期：裸 shell 下它会**拒绝扳动**并列出原因（任务清单未登记、无基线）。**这不是报错，是门禁在工作。** 真实会话实例：一个 5 任务计划先掷 `CLARIFY` → 补 `--files` / `--units` 与 `--baseline` 基线文件后翻成 `verdict: A`（混合拓扑）。

## 输入 / 输出

- **输入**：`--files N --units N --desc "..."`，可选 `--coupled --baseline <文件> --dep-reason "..."`。文件数量是唯一任务量纲。
- **输出**：JSON 判定（`verdict` / `mechanism` / `fanout` / violations 与理由）+ JSONL 留痕于 `~/.agents/logs/dispatch_switch.jsonl`。
- **双维决策矩阵**（全表见 `SKILL.md`）：
  - 规模轴：≤3 文件轻分身 · >3 文件或契约耦合走 `task_breakdown` 定档 · M/L 引擎级分身
  - 数量轴：2~5 主 agent 并行 · 6~9 分组 · ≥10 workflow 编排

## 能力与边界

- 完整规则在 `SKILL.md`：场景自动匹配表、分身生命周期三槽契约（PRE-SPAWN / RECEIPT / MERGE）、最小探针、母体合并校验时点分层、禁止清单（违例即视为故意串行化或违规并行）。
- **边界**：parallel-dispatch 只决定**是否**与**如何**并行——它不执行任务。

## 组合用法

- **[gate-switch](../gate-switch/README_zh.md)**：掷点前置条件（任务清单已登记、基线文件存在）可写成 gate-switch spec 看守。
- **task_breakdown**：M/L 规模先定档再引擎级分身。
- **[Xj-engine](../Xj-engine/README_zh.md)**：≥10 单元批量走引擎 workflow 编排。

## FAQ

**Q：为什么掷出 CLARIFY？**
开关只对机械信号做判定。补 `--files` / `--units`，耦合工作再给 `--baseline` 文件——然后它才判定。

**Q：模型能悄悄决定串行吗？**
不能——只评估不执行视为故意串行化，JSONL 留痕可审计。

**Q：B 档是「错」吗？**
不是。B = 带理由的串行，一等公民判定。**留空理由**才是违例。

---

许可：[自定义源码可用许可](../LICENSE)（中文对照：[LICENSE-zh.md](../LICENSE-zh.md)）——仅供个人非商用本地使用；未经书面授权禁止公开 Fork、商用分发、SaaS 服务。作者 [xu-jin-cs](https://github.com/xu-jin-cs)。
