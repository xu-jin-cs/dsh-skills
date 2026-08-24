---
name: scope_boundary
description: "范围边界机械拦截（SV-GATE-001 重生版：git diff 变更文件集 vs 范围清单集合运算，替代旧 YAML 文本关键词桩）。"
---

# scope_boundary — gate-switch 实证闸

## 用途与触发

范围边界机械拦截（SV-GATE-001 重生版：git diff 变更文件集 vs 范围清单集合运算，替代旧 YAML 文本关键词桩）。A=无越界放行提交；B=阻断，越界清单即理由（须 PM 确认纳入或删除——即使代码已写也要删掉）

## 扳动命令

```bash
python3 ~/.agents/skills/scope_boundary/scripts/gate_switch.py --spec ~/.agents/skills/scope_boundary/scripts/specs/scope_boundary.json --set allow=<allow> --set base=<base> --set repo=<repo>
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

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`scope-boundary-gate`。
