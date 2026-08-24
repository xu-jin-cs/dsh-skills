---
name: func_signature
description: "规则27 函数签名实证（半开关）：写测试调用前实证被测函数存活与真实签名，判 A 贴签名原文；判 B=已删除/重命名禁止凭记忆"
---

# func_signature — gate-switch 实证闸

## 用途与触发

规则27 函数签名实证（半开关）：写测试调用前实证被测函数存活与真实签名，判 A 贴签名原文；判 B=已删除/重命名禁止凭记忆

## 扳动命令

```bash
python3 ~/.agents/skills/func_signature/scripts/gate_switch.py --spec ~/.agents/skills/func_signature/scripts/specs/func_signature.json --set func=<func> --set src=<src>
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
