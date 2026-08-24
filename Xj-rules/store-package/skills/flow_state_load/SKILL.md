---
name: flow_state_load
description: "流程A 步骤0-B 状态加载闸（01_workflows.md L257 区，2026-08-16 开关化）：进入步骤1之前 PM 必须创建/读取 {project}/.flow_state.json。"
---

# flow_state_load — gate-switch 实证闸

## 用途与触发

流程A 步骤0-B 状态加载闸（01_workflows.md L257 区，2026-08-16 开关化）：进入步骤1之前 PM 必须创建/读取 {project}/.flow_state.json。治「PM 口头声称已恢复断点但状态文件从未落盘/关键字段缺失」。A=文件存在且 status/step 非空，放行进入步骤1；B=缺失或空壳，violations 即补齐指令。sv-supervisor 规则读取等语义项留软层。

## 扳动命令

```bash
python3 ~/.agents/skills/flow_state_load/scripts/gate_switch.py --spec ~/.agents/skills/flow_state_load/scripts/specs/flow_state_load.json --set project=<project>
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
