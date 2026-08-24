---
name: first_push_audit
description: "L2 开关第一推动事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板A改造）：无钩子环境下'何时该扳开关'靠自觉、不扳不留痕。"
---

# first_push_audit — gate-switch 实证闸

## 用途与触发

L2 开关第一推动事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板A改造）：无钩子环境下'何时该扳开关'靠自觉、不扳不留痕。本闸扫 旧版 会话 jsonl + 开关留痕 jsonl，检测'模式信号在、对应留痕缺'不对称：F1 ≥2 次 subagent 族扇出但无 dispatch_switch 掷点 / F2 方案特征但无 reform_gate 掷点 / F3 复盘触发词命中但无 retro_generate_token 掷点 / F4 掷点 A 但零真扇出 / F5 engine 流程特征无 health 掷点（WARNING）/ F6 retro 触发词命中但窗口内 _active_match.md 未更新（retro-match 该跑没跑，消费链第一环，2026-08-17 消费链路 REFORM-GATE 断点1 落地）/ F7 起手式缺失（2026-08-17 REFORM-GATE 判 A，规则制定者自我盲区实证：4 条问卷提交未开清单/未掷点/串行无理由对 F1-F6 全隐身）：F7a 单回合工具调用≥4 但无 todo/write → 长链任务未开清单起手式；F7b 同形命令跨≥3 回合重复且窗口内无 todo/write 无 dispatch_switch 掷点 → 批量任务零起手式。判 A=会话全部开关第一推动合规；判 B=violations 即应扳未扳清单，复盘记违规、比率进 B/A 审计。挂接点：复盘第四部分着陆检查前（01_workflows.md 复盘标准结构）+ 人工随时可扳。

## 扳动命令

```bash
python3 ~/.agents/skills/first_push_audit/scripts/gate_switch.py --spec ~/.agents/skills/first_push_audit/scripts/specs/first_push_audit.json
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
