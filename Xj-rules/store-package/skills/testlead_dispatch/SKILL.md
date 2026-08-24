---
name: testlead_dispatch
description: "test-lead 三路下发门禁：输出三路输入齐备向量。A=三路齐全部下发；B=按 violations 识别缺口路——缺哪路搁置哪路（B 不是全停，其余路正常并行，violations 原文写入收口缺口原因）"
---

# testlead_dispatch — gate-switch 实证闸

## 用途与触发

test-lead 三路下发门禁：输出三路输入齐备向量。A=三路齐全部下发；B=按 violations 识别缺口路——缺哪路搁置哪路（B 不是全停，其余路正常并行，violations 原文写入收口缺口原因）

## 扳动命令

```bash
python3 ~/.agents/skills/testlead_dispatch/scripts/gate_switch.py --spec ~/.agents/skills/testlead_dispatch/scripts/specs/testlead_dispatch.json --set project=<project>
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
