---
name: test_executor_evidence
description: "测试执行证据门：接件校验+证据完整性。A=证据链完整可交付；B=拒绝执行/标记证据异常，violations 即异常清单（防假证据假通过率）"
---

# test_executor_evidence — gate-switch 实证闸

## 用途与触发

测试执行证据门：接件校验+证据完整性。A=证据链完整可交付；B=拒绝执行/标记证据异常，violations 即异常清单（防假证据假通过率）

## 扳动命令

```bash
python3 ~/.agents/skills/test_executor_evidence/scripts/gate_switch.py --spec ~/.agents/skills/test_executor_evidence/scripts/specs/test_executor_evidence.json --set evidence=<evidence>
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
