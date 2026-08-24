---
name: resume_delivery
description: "resume-direct 节点3 交付实证闸（对齐 ppt_delivery，2026-08-17 改造）：机械核验成品已复制到 ~/Desktop/{name}.pptx——仅文字提及路径不构成有效交付。"
---

# resume_delivery — gate-switch 实证闸

## 用途与触发

resume-direct 节点3 交付实证闸（对齐 ppt_delivery，2026-08-17 改造）：机械核验成品已复制到 ~/Desktop/{name}.pptx——仅文字提及路径不构成有效交付。open -R 亮显为 Finder 交互动作、无落盘产物可机械核验，留软层自觉执行（用户明确要求不打开时除外）。扳动时机：cp 完成后、输出交付回执前。用法：--set name=<主题命名（不含 .pptx 后缀，建议 resume_姓名_岗位）>

## 扳动命令

```bash
python3 ~/.agents/skills/resume_delivery/scripts/gate_switch.py --spec ~/.agents/skills/resume_delivery/scripts/specs/resume_delivery.json --set name=<name>
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
