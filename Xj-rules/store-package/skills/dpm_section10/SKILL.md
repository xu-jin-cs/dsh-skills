---
name: dpm_section10
description: "DPM 交互文档第10节字段约束表存在性：缺此节 → 测试角色退回补充，禁止凭猜测编造边界（min/max 单元格空值语义校验留待批次2脚本化）"
---

# dpm_section10 — gate-switch 实证闸

## 用途与触发

DPM 交互文档第10节字段约束表存在性：缺此节 → 测试角色退回补充，禁止凭猜测编造边界（min/max 单元格空值语义校验留待批次2脚本化）

## 扳动命令

```bash
python3 ~/.agents/skills/dpm_section10/scripts/gate_switch.py --spec ~/.agents/skills/dpm_section10/scripts/specs/dpm_section10.json --set dpmdoc=<dpmdoc>
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
