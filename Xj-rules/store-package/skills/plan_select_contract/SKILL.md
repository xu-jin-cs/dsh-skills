---
name: plan_select_contract
description: "plan_select.py 四态契约回归闸（CLAIM-GATE 族复用件，2026-08-19 落地）：闸脚本 plan_select.py 改动后「声称已还原/已修复」的实证闸。"
---

# plan_select_contract — gate-switch 实证闸

## 用途与触发

plan_select.py 四态契约回归闸（CLAIM-GATE 族复用件，2026-08-19 落地）：闸脚本 plan_select.py 改动后「声称已还原/已修复」的实证闸。script_exit 调 plan_select_contract_check.py 做四态契约全路径回归——正常 pool→A(exit 0) / 缺池文件→B(exit 2) / 空池→CLARIFY(exit 3) / --fail 无 --reason→VIOLATION(exit 4) / 裸跑→argparse(exit 2)，并保证 plan_select.jsonl 账本零污染。背景事故：有人改动 plan_select.py 只验证 happy path 就声称已还原，B 档路径被误删退化成 traceback。全路径过→A 放行声称；任一不符→B 阻断，violations 即失败明细。判定禁止手写，模型只照抄输出。

## 扳动命令

```bash
python3 ~/.agents/skills/plan_select_contract/scripts/gate_switch.py --spec ~/.agents/skills/plan_select_contract/scripts/specs/plan_select_contract.json
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

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`plan-select`。
