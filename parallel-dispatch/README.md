# parallel-dispatch — 并行调度与子分身机制总规则

> 功能与用途 · 安装 · 协议

## 功能

多任务场景的**唯一权威入口**：只要出现 ≥2 个子任务即强制触发并行判定并输出 `[PARALLEL-GATE]` 声明，无触发词依赖。

- **双维决策**：规模轴（≤3 文件轻分身 / >3 文件或契约耦合走 task_breakdown / M·L 档引擎级）× 数量轴（2~5 subagent 扇出 / 6~9 分组 / ≥10 workflow 编排）；
- **单刀双掷开关**：`scripts/dispatch_switch.py` 机械掷点——A 并行扇出 / B 串行（B 档必须写明依赖链理由，留空即违规），全程 jsonl 留痕；
- 掷点 A 前置三道闸：任务清单登记、统一上下文基线、探针实证——防止盲扇出。

## 用途

- 给 Agent 宿主的并行分发装上刹车与证据链：多任务不再凭感觉串并行；
- 只评估不执行视为故意串行化；任务量量纲唯一化（只数文件，不用体感）；
- 场景自动匹配表 + 最小探针 + 母体合并校验时点分层 + 禁止清单，见 `SKILL.md`。

## 快速开始

```bash
# 裸跑开关看机械判定（未登记任务清单会被拒扳——这正是门禁在工作）
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

## 协议

[CC BY-NC-SA 4.0](../LICENSE)——禁止商用；二次开发与转载须署名作者 [xu-jin-cs](https://github.com/xu-jin-cs/dsh-skills) 并保持同协议。
