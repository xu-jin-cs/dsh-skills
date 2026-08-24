---
name: safety_cmd_audit
description: "安全铁律事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板B改造；2026-08-20 补铁律8查点）：扫 旧版 会话 jsonl 的 tool/call 记录，一门三查——S1 危险命令黑名单（rm 递归/强制 -f/多文件/cp -R/find -delete/mv "
---

# safety_cmd_audit — gate-switch 实证闸

## 用途与触发

安全铁律事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板B改造；2026-08-20 补铁律8查点）：扫 旧版 会话 jsonl 的 tool/call 记录，一门三查——S1 危险命令黑名单（rm 递归/强制 -f/多文件/cp -R/find -delete/mv 目录源，违反 00_root_safety 铁律7）/ S2 固定目录区块标记符成对性（铁律6）/ S3 打断即停手 WARNING 弱审计（只报不判）。铁律8查点：会话若发现闸绕过却未曝光/未产出 REFORM 补丁块/未改对应 spec 或脚本 → 判 B 违例进复盘（2026-08-20 用户裁定'发现绕闸即曝光+打补丁'）。判 A=会话无安全违例；判 B=violations 即危险命令/区块破坏/漏曝光证据清单。

## 扳动命令

```bash
python3 ~/.agents/skills/safety_cmd_audit/scripts/gate_switch.py --spec ~/.agents/skills/safety_cmd_audit/scripts/specs/safety_cmd_audit.json
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
