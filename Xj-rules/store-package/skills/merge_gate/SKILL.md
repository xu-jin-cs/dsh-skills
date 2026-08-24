---
name: merge_gate
description: "parallel-dispatch SLOT-MERGE 合并槽门禁：四道校验中可机械化的两道——a) 文件级冲突（两分身改同一文件即违例）b) 产物完整性（期望清单差集为空）；契约级/语义级冲突留软层人工校验（纯语义不造门）。"
---

# merge_gate — gate-switch 实证闸

## 用途与触发

parallel-dispatch SLOT-MERGE 合并槽门禁：四道校验中可机械化的两道——a) 文件级冲突（两分身改同一文件即违例）b) 产物完整性（期望清单差集为空）；契约级/语义级冲突留软层人工校验（纯语义不造门）。判 A 照抄放行，判 B 按违例清单补派/整改

## 扳动命令

```bash
python3 ~/.agents/skills/merge_gate/scripts/gate_switch.py --spec ~/.agents/skills/merge_gate/scripts/specs/merge_gate.json --set expect=<expect> --set manifests=<manifests>
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

## 依赖

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`parallel-dispatch`。
