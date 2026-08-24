---
name: danger_cmd_gate
description: "危险命令事前闸（铁律7，2026-08-17 存量清算落地）：bash 执行涉 rm/cp递归/find -delete/mv 等命令前，把待执行命令原文落盘为文本文件，扳本闸 --set cmdfile=<文件>。"
---

# danger_cmd_gate — gate-switch 实证闸

## 用途与触发

危险命令事前闸（铁律7，2026-08-17 存量清算落地）：bash 执行涉 rm/cp递归/find -delete/mv 等命令前，把待执行命令原文落盘为文本文件，扳本闸 --set cmdfile=<文件>。A=未命中 S1 黑名单允许执行；B=命中即阻断，violations 即违例明细，确需执行须用户显式批准后人工执行。与事后审计 safety_cmd_guard（复盘期 S1 必查）互补：事前闸管当次判定，事后审计查漏扳，双保险非重复设防。判危逻辑单一真源 safety_cmd_guard.check_dangerous_commands。

## 扳动命令

```bash
python3 ~/.agents/skills/danger_cmd_gate/scripts/gate_switch.py --spec ~/.agents/skills/danger_cmd_gate/scripts/specs/danger_cmd_gate.json --set cmdfile=<cmdfile>
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
