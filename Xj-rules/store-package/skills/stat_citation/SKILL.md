---
name: stat_citation
description: "统计引用口径闸（2026-08-20 问题闸+REFORM-GATE 双判A，挂 CLAIM-GATE 族）——任何统计结论（命中率/通过率/比率/占比）出口前机械三查+时效一查。"
---

# stat_citation — gate-switch 实证闸

## 用途与触发

统计引用口径闸（2026-08-20 问题闸+REFORM-GATE 双判A，挂 CLAIM-GATE 族）——任何统计结论（命中率/通过率/比率/占比）出口前机械三查+时效一查。用法：--set doc=<统计结论文档> --set source=<数据真源文件>。A=文档标注真源+声明统计区间+真源带 pipeline_hash 版本戳+文档不旧于真源；B=缺标注/真源无版本戳/真源已更新但文档未重算（跨口径混算嫌疑），violations 即理由。语义层（指标性质判断是否误读）留软层+复盘后查。真源版本戳由各写入方自盖（首例 retro-match.sh E1，2026-08-20）。

## 扳动命令

```bash
python3 ~/.agents/skills/stat_citation/scripts/gate_switch.py --spec ~/.agents/skills/stat_citation/scripts/specs/stat_citation.json --set doc=<doc> --set source=<source>
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
