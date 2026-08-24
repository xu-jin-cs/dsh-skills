---
name: engine_literal_scan
description: "短板2防复发闸（2026-08-20 REFORM-GATE 判A）：「引擎零业务常量」从软规则升级为机械扫描。"
---

# engine_literal_scan — gate-switch 实证闸

## 用途与触发

短板2防复发闸（2026-08-20 REFORM-GATE 判A）：「引擎零业务常量」从软规则升级为机械扫描。词表驱动扫描引擎层目录（由 data/engine_literal_wordlist.json 的 scan_dirs 配置，按自己项目改写），命中非白名单业务字面量即判 B。词表 ~/.agents/skills/engine_literal_scan/data/engine_literal_wordlist.json 只增不删；legacy_allowlist 存量登记只减不增。挂点：复盘着陆闸族 + 引擎代码交付期。

## 扳动命令

```bash
python3 ~/.agents/skills/engine_literal_scan/scripts/gate_switch.py --spec ~/.agents/skills/engine_literal_scan/scripts/specs/engine_literal_scan.json
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
