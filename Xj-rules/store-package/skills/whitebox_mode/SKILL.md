---
name: whitebox_mode
description: "白盒模式门禁：有完整基线→A(diff 增量)；缺基线→B(full 全量，violations 即缺失理由)"
---

# whitebox_mode — gate-switch 实证闸

## 用途与触发

白盒模式门禁：有完整基线→A(diff 增量)；缺基线→B(full 全量，violations 即缺失理由)

## 扳动命令

```bash
python3 ~/.agents/skills/whitebox_mode/scripts/gate_switch.py --spec ~/.agents/skills/whitebox_mode/scripts/specs/whitebox_mode.json --set project=<project>
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
