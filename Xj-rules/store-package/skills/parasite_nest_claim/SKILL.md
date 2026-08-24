---
name: parasite_nest_claim
description: "寄生巢落巢实证闸（CLAIM-GATE 族）：声称某寄生虫已落巢时扳本闸。"
---

# parasite_nest_claim — gate-switch 实证闸

## 用途与触发

寄生巢落巢实证闸（CLAIM-GATE 族）：声称某寄生虫已落巢时扳本闸。A=巢存储文件中该宿主闸的模板队列确含该任务且状态为休眠；B=落巢缺斤短两/伪造声称。--set nest=<宿主闸名> --set task=<任务名>

## 扳动命令

```bash
python3 ~/.agents/skills/parasite_nest_claim/scripts/gate_switch.py --spec ~/.agents/skills/parasite_nest_claim/scripts/specs/parasite_nest_claim.json --set nest=<nest> --set task=<task>
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
