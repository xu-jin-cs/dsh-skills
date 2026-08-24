---
name: anchor_registry_audit
description: "锚点登记审计闸（2026-08-18 用户裁定采纳锚点注册表补位后落地，REFORM-GATE 判A；first_push_audit 同族'产物在/锚点缺'不对称检测）。"
---

# anchor_registry_audit — gate-switch 实证闸

## 用途与触发

锚点登记审计闸（2026-08-18 用户裁定采纳锚点注册表补位后落地，REFORM-GATE 判A；first_push_audit 同族'产物在/锚点缺'不对称检测）。数据源类产出（评估基准/方案/源码/历史记录）收尾必须登记锚点；声称某产物已登记、或复盘后查漏登记时扳：--set artifact=<产物路径>。A=产物真实存在且注册表有对应 source_path 锚点行；B=violations 即缺失项——产物不存在=审计对象造假；锚点行缺=漏登记，须用 dual_gates.py anchor 补登后重扳。

## 扳动命令

```bash
python3 ~/.agents/skills/anchor_registry_audit/scripts/gate_switch.py --spec ~/.agents/skills/anchor_registry_audit/scripts/specs/anchor_registry_audit.json --set artifact=<artifact>
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
