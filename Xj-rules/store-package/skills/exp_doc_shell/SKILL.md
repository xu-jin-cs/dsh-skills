---
name: exp_doc_shell
description: "经验文档空壳检测（P3 · 2026-08-15 REFORM-GATE 判A）：角色经验文件 <200 字节判空壳。"
---

# exp_doc_shell — gate-switch 实证闸

## 用途与触发

经验文档空壳检测（P3 · 2026-08-15 REFORM-GATE 判A）：角色经验文件 <200 字节判空壳。用法：gate_switch.py --spec exp_doc_shell.json --set expfile=<角色经验文档路径>，判B（空壳）角色须在 retro_report.json 中点名（补齐或标注「无经验」）。挂点：skills/pm/flow.yml 经验空壳审计步。2026-08-20 审计 AGT-002 误判零引用删除后按 flow.yml 挂点重建（审计 grep 漏检 flow.yml，已计入复盘）。

## 扳动命令

```bash
python3 ~/.agents/skills/exp_doc_shell/scripts/gate_switch.py --spec ~/.agents/skills/exp_doc_shell/scripts/specs/exp_doc_shell.json --set expfile=<expfile>
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
