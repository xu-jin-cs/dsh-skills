---
name: no_abs_path
description: "绝对路径硬编码零容忍 tripwire（2026-08-20 三短板根源治理 M2，REFORM-GATE v2 判A）：活体代码禁止字面量 /Users/* 路径——写死即换机即死（实证：某引擎项目 85 处存量、19 文件一次清算）。"
---

# no_abs_path — gate-switch 实证闸

## 用途与触发

绝对路径硬编码零容忍 tripwire（2026-08-20 三短板根源治理 M2，REFORM-GATE v2 判A）：活体代码禁止字面量 /Users/* 路径——写死即换机即死（实证：某引擎项目 85 处存量、19 文件一次清算）。本闸为兜底拦截非治疗方案；根治在产出点：路径引用三口径 + 共享助手（rules/04_dev_standard.md「路径引用三口径与文档真源指针原则」）。归档/备份/dist 等历史快照不在扫描面（path glob 只覆盖活体目录）。用法：gate_switch.py --spec no_abs_path.json --set src=<项目根>

## 扳动命令

```bash
python3 ~/.agents/skills/no_abs_path/scripts/gate_switch.py --spec ~/.agents/skills/no_abs_path/scripts/specs/no_abs_path.json --set src=<src>
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
