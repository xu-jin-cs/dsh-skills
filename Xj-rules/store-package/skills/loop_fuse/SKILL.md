---
name: loop_fuse
description: "规则32 复刻循环熔断：3轮未过强制升级/同源补丁>2次熔断/超轮上限熔断，计数留痕 jsonl 不凭记忆"
---

# loop_fuse — gate-switch 实证闸

## 用途与触发

规则32 复刻循环熔断：3轮未过强制升级/同源补丁>2次熔断/超轮上限熔断，计数留痕 jsonl 不凭记忆

## 扳动命令

```bash
python3 ~/.agents/skills/loop_fuse/scripts/gate_switch.py --spec ~/.agents/skills/loop_fuse/scripts/specs/loop_fuse.json --set event=<event> --set loop_id=<loop_id> --set patch_sig=<patch_sig>
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
