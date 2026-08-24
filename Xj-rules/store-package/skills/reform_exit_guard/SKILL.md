---
name: reform_exit_guard
description: "请示出口闸（2026-08-17 用户裁定，扳手性质禁软提示词）：改造方案/建议出口后或复盘审计时扳本闸——E1 会话出口文本含请示句式（是否需要我/要不要执行/等你确认 等）即违例；E2 会话含改造方案特征但窗口内无 reform_gate 掷点记录即方案裸奔出口违例。"
---

# reform_exit_guard — gate-switch 实证闸

## 用途与触发

请示出口闸（2026-08-17 用户裁定，扳手性质禁软提示词）：改造方案/建议出口后或复盘审计时扳本闸——E1 会话出口文本含请示句式（是否需要我/要不要执行/等你确认 等）即违例；E2 会话含改造方案特征但窗口内无 reform_gate 掷点记录即方案裸奔出口违例。判 A=出口合规；判 B=violations 即违例证据（句式摘录/缺失窗口），复盘记违规。

## 扳动命令

```bash
python3 ~/.agents/skills/reform_exit_guard/scripts/gate_switch.py --spec ~/.agents/skills/reform_exit_guard/scripts/specs/reform_exit_guard.json
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
