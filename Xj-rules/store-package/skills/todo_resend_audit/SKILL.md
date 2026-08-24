---
name: todo_resend_audit
description: "L2 TodoList 重发义务事后审计闸（2026-08 REFORM-GATE 判立即改落地）：旧版 todos 投影 turn 级清零是外部既定语义，goal 续轮与子分身通知（idle 收 followup）每开新 turn 即清清单；新回合是否重发 TodoList 原靠模型自觉。"
---

# todo_resend_audit — gate-switch 实证闸

## 用途与触发

L2 TodoList 重发义务事后审计闸（2026-08 REFORM-GATE 判立即改落地）：旧版 todos 投影 turn 级清零是外部既定语义，goal 续轮与子分身通知（idle 收 followup）每开新 turn 即清清单；新回合是否重发 TodoList 原靠模型自觉。本闸扫本会话事件日志逐 turn 核验：turn 开始时有悬置未完成清单（上一快照 pending+in_progress>0）而本 turn 未重发 → T1 违例（aborted/interrupted 机械豁免）。判 A=全部义务回合已重发；判 B=violations 即缺发回合清单，复盘记违规。挂接点：复盘着陆检查（与 first_push_audit.json 同级）+ 人工随时可扳。

## 扳动命令

```bash
python3 ~/.agents/skills/todo_resend_audit/scripts/gate_switch.py --spec ~/.agents/skills/todo_resend_audit/scripts/specs/todo_resend_audit.json
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
