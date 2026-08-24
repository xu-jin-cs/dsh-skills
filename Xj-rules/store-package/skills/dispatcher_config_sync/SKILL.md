---
name: dispatcher_config_sync
description: "dispatcher 配置变更同步证据：配置 mtime 新于文档时，文档必须同步更新（doc 新于 config 或同时）——防'已同步'假声称"
---

# dispatcher_config_sync — gate-switch 实证闸

## 用途与触发

dispatcher 配置变更同步证据：配置 mtime 新于文档时，文档必须同步更新（doc 新于 config 或同时）——防'已同步'假声称

## 扳动命令

```bash
python3 ~/.agents/skills/dispatcher_config_sync/scripts/gate_switch.py --spec ~/.agents/skills/dispatcher_config_sync/scripts/specs/dispatcher_config_sync.json --set config=<config> --set doc=<doc>
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
