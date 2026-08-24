---
name: goal_gate
description: "长期目标创建/续轮前置闸（2026-08-20 用户裁定废弃自主修码任务并根治重复触发落地点）。"
---

# goal_gate — gate-switch 实证闸

## 用途与触发

长期目标创建/续轮前置闸（2026-08-20 用户裁定废弃自主修码任务并根治重复触发落地点）。根治本会话事故：create_goal 被无闸创建、目标自动续轮 2 次持续修码烧 token。挂点：任何 create_goal / 目标自动续轮之前必须过本闸。核心：目标须来自用户显式请求（软档）+ 必须带可接受预算 max_goal_rounds 介于 1 与 10（机械档）+ 续轮前须目标仍成立。A=objective 非空且 max_goal_rounds 在界；B=缺 objective 或 max_goal_rounds 缺失/越界；判定机械走 json_field。

## 扳动命令

```bash
python3 ~/.agents/skills/goal_gate/scripts/gate_switch.py --spec ~/.agents/skills/goal_gate/scripts/specs/goal_gate.json --set goal_block=<goal_block>
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
