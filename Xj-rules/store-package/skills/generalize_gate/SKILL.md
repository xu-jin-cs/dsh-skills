---
name: generalize_gate
description: "GENERALIZE-GATE 填充完整性+模式库登记机械校验（2026-08-17 存量清算落地，仿 reform_gate.json 骨架，rules/11 第五节骨架化）：新机制/框架被采纳落地后，把填好的 [GENERALIZE-GATE] 块存为文件，扳 --set block=<块文件>"
---

# generalize_gate — gate-switch 实证闸

## 用途与触发

GENERALIZE-GATE 填充完整性+模式库登记机械校验（2026-08-17 存量清算落地，仿 reform_gate.json 骨架，rules/11 第五节骨架化）：新机制/框架被采纳落地后，把填好的 [GENERALIZE-GATE] 块存为文件，扳 --set block=<块文件> --set pattern=<模式名>。A=①-⑥ 六字段标记齐全且 pattern_registry.jsonl 已有该模式登记条目；B=violations 即缺失项。填得对不对（实证真假/同类是否真实存在）留软层+复盘审计。

## 扳动命令

```bash
python3 ~/.agents/skills/generalize_gate/scripts/gate_switch.py --spec ~/.agents/skills/generalize_gate/scripts/specs/generalize_gate.json --set block=<block> --set pattern=<pattern>
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
