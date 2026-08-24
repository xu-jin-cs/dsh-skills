---
name: shard_result_gate
description: "分身结果落盘核验（2026-08-17 结果落盘制落地，parallel-dispatch 三槽契约 SLOT-PRE ⑦ / SLOT-RECEIPT）：母体收编每路分身成果前扳 --set result=<任务书⑦指定的结果文件路径>。"
---

# shard_result_gate — gate-switch 实证闸

## 用途与触发

分身结果落盘核验（2026-08-17 结果落盘制落地，parallel-dispatch 三槽契约 SLOT-PRE ⑦ / SLOT-RECEIPT）：母体收编每路分身成果前扳 --set result=<任务书⑦指定的结果文件路径>。A=结果文件真实存在且非空，允许收编该路；B=成果未落盘（续派补落盘或标记该路损失，其余路不连坐）。防单屏障全有全无——workflow 取消/单片失败时已完成分身成果颗粒归仓。

## 扳动命令

```bash
python3 ~/.agents/skills/shard_result_gate/scripts/gate_switch.py --spec ~/.agents/skills/shard_result_gate/scripts/specs/shard_result_gate.json --set result=<result>
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
