---
name: ppt_gate_a
description: "ppt 主链 Gate A（设计决策出口，2026-08-15 裁定自归档 legacy-workflow 引擎迁移 gate-switch）：主线06 质检通过后、主线07 渲染入参组装前扳动。"
---

# ppt_gate_a — gate-switch 实证闸

## 用途与触发

ppt 主链 Gate A（设计决策出口，2026-08-15 裁定自归档 legacy-workflow 引擎迁移 gate-switch）：主线06 质检通过后、主线07 渲染入参组装前扳动。机械核验 00~05 设计决策六件套产物存在性与必备字段；风格美观/复刻还原度评分等纯语义项不机考，留软层（主线06 目检）。用法：--set run=<run_dir>

## 扳动命令

```bash
python3 ~/.agents/skills/ppt_gate_a/scripts/gate_switch.py --spec ~/.agents/skills/ppt_gate_a/scripts/specs/ppt_gate_a.json --set run=<run>
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
