---
name: ppt_extract_mode
description: "ppt 节点03 分流判定：A=executed（模板目录存在且含 page_*.png，走解析+复刻）；B=passthrough（无模板，violations 即 passthrough 理由，不是失败而是分流依据）"
---

# ppt_extract_mode — gate-switch 实证闸

## 用途与触发

ppt 节点03 分流判定：A=executed（模板目录存在且含 page_*.png，走解析+复刻）；B=passthrough（无模板，violations 即 passthrough 理由，不是失败而是分流依据）

## 扳动命令

```bash
python3 ~/.agents/skills/ppt_extract_mode/scripts/gate_switch.py --spec ~/.agents/skills/ppt_extract_mode/scripts/specs/ppt_extract_mode.json --set tpldir=<tpldir>
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
