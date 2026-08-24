---
name: task_launch_gate
description: "会话循环熔断：每次任务发起前置记账（按会话维度），同会话同一任务累计发起>3次（第4次）禁止加入并上报用户决定；复盘动作清空当前会话任务版。"
---

# task_launch_gate — gate-switch 实证闸

## 用途与触发

会话循环熔断：每次任务发起前置记账（按会话维度），同会话同一任务累计发起>3次（第4次）禁止加入并上报用户决定；复盘动作清空当前会话任务版。计数留痕 jsonl 不凭记忆。

## 扳动命令

```bash
python3 ~/.agents/skills/task_launch_gate/scripts/gate_switch.py --spec ~/.agents/skills/task_launch_gate/scripts/specs/task_launch_gate.json --set session_id=<session_id> --set task=<task>
```

判定禁止手写：必须实跑上述命令并照抄输出结论，禁止凭印象声称通过/不通过。

## 退出码语义

| 退出码 | 含义 |
|--:|---|
| 0 | A：全部机械核验通过，放行 |
| 2 | B：有违例阻断，violations 即违例清单/修复指令 |
| 3 | CLARIFY：输入信号不足，先澄清再扳 |
| 4 | VIOLATION：spec 非法或前置条件缺失（按输出整改后重扳） |

留痕：`~/.agents/logs/gate_switch.jsonl`。
