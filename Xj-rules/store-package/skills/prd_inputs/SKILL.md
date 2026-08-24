---
name: prd_inputs
description: "项目前置输入准入闸（01_workflows.md 规则6，2026-08-16 开关化）：用户上传压缩包或给出项目路径时，PM 必须先校验 {project}/.prd.md + {project}/.ui-proto.json 双输入齐备再开展后续工作。"
---

# prd_inputs — gate-switch 实证闸

## 用途与触发

项目前置输入准入闸（01_workflows.md 规则6，2026-08-16 开关化）：用户上传压缩包或给出项目路径时，PM 必须先校验 {project}/.prd.md + {project}/.ui-proto.json 双输入齐备再开展后续工作。治「PM 凭用户口述需求直接开工，事后发现无 PRD 无 UI 原型」。A=双输入齐备放行 Step1；B=缺项清单即 violations，补齐后重新扳动。

## 扳动命令

```bash
python3 ~/.agents/skills/prd_inputs/scripts/gate_switch.py --spec ~/.agents/skills/prd_inputs/scripts/specs/prd_inputs.json --set project=<project>
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
