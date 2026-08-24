---
name: reform_gate
description: "REFORM-GATE 填充完整性+层位一致性机械校验（2026-08-19 v4：从查填没填到查层位对不对；2026-08-20 v5 定版：问题闸核心逻辑决策树四节点必填（一次性根治/通用问题/需要闸/需要钩子），用户亲定并指正三次后定稿，替代旧五字段版）：改造方案出口前，把填好的 [REFOR"
---

# reform_gate — gate-switch 实证闸

## 用途与触发

REFORM-GATE 填充完整性+层位一致性机械校验（2026-08-19 v4：从查填没填到查层位对不对；2026-08-20 v5 定版：问题闸核心逻辑决策树四节点必填（一次性根治/通用问题/需要闸/需要钩子），用户亲定并指正三次后定稿，替代旧五字段版）：改造方案出口前，把填好的 [REFORM-GATE] 块存为文件过本门禁。A=字段齐全且方案文件层位与问题层位相交（或不相交但有非空层位偏离理由，WARNING 放行留审计）；B=缺字段或层位不相交无理由。字段内容质量留软层+复盘审计。

## 扳动命令

```bash
python3 ~/.agents/skills/reform_gate/scripts/gate_switch.py --spec ~/.agents/skills/reform_gate/scripts/specs/reform_gate.json --set block=<block>
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

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`parallel-dispatch`。
