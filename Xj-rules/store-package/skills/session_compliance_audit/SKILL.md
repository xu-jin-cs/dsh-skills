---
name: session_compliance_audit
description: "会话合规审计合并闸（2026-08-19 复盘闸族瘦身，REFORM-GATE 判 A 落地）：原 first_push_audit（F1-F8 该扳未扳，F8=查询闸漏扳后查 2026-08-20 任务书 D2）+ safety_cmd_audit（S1-S3 危险命令/固定区块/打断）+ tod"
---

# session_compliance_audit — gate-switch 实证闸

## 用途与触发

会话合规审计合并闸（2026-08-19 复盘闸族瘦身，REFORM-GATE 判 A 落地）：原 first_push_audit（F1-F8 该扳未扳，F8=查询闸漏扳后查 2026-08-20 任务书 D2）+ safety_cmd_audit（S1-S3 危险命令/固定区块/打断）+ todo_resend_audit（T1 todo 重发）三闸证据源同源（均扫会话 jsonl），合并为一次扳动出全维报告。A=三维全合规；B=violations 即各维违例清单，按原口径记复盘第三部分/第一部分。挂接点：复盘第四部分着陆检查前。

## 扳动命令

```bash
python3 ~/.agents/skills/session_compliance_audit/scripts/gate_switch.py --spec ~/.agents/skills/session_compliance_audit/scripts/specs/session_compliance_audit.json
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

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`dual-gates`。
