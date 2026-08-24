---
name: clarify_gate
description: "CLARIFY-GATE 需求五要素齐备性声明填充完整性机械校验：ui-designer Phase 0 判闸。"
---

# clarify_gate — gate-switch 实证闸

## 用途与触发

CLARIFY-GATE 需求五要素齐备性声明填充完整性机械校验：ui-designer Phase 0 判闸。把「需求五要素齐备性声明」块存为文件过本门禁。A=字段齐全允许进入 Step1 internal-taste-analyze；B=缺字段打回补全，violations 即缺失清单（防跳过声明/缺斤短两）。要素内容真假留软层+复盘审计。

## 扳动命令

```bash
python3 ~/.agents/skills/clarify_gate/scripts/gate_switch.py --spec ~/.agents/skills/clarify_gate/scripts/specs/clarify_gate.json --set block=<block>
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
