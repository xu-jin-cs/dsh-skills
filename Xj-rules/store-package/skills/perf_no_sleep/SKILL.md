---
name: perf_no_sleep
description: "性能规范机械闸（rules/10 L155，2026-08-17 存量清算落地）：交付源码禁止固定 sleep/人为阻塞代码。"
---

# perf_no_sleep — gate-switch 实证闸

## 用途与触发

性能规范机械闸（rules/10 L155，2026-08-17 存量清算落地）：交付源码禁止固定 sleep/人为阻塞代码。代码交付或审查时扳 --set src=<源码文件或目录>。A=零命中放行；B=命中行即违例清单。确有外部SDK强制等待等例外，须用户裁定后在命中行加 # perf-exempt 注释并人工剥离该行后重扳（剥离动作留软层，豁免泛滥进复盘）。

## 扳动命令

```bash
python3 ~/.agents/skills/perf_no_sleep/scripts/gate_switch.py --spec ~/.agents/skills/perf_no_sleep/scripts/specs/perf_no_sleep.json --set src=<src>
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
