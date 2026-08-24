---
name: rules_inflation_guard
description: "01_workflows.md 规则通胀拆分守护闸（2026-08-20 REFORM-GATE 判 A，Shard A 落地）：① 主文件瘦身 ≤300 行（强制规则全文+分片索引表+导航）；② 六个分片文件存在；③ 分片来源注记齐全（6 处）；④⑤ 章节级旧锚点断链清零——只检查可机械判模式：`"
---

# rules_inflation_guard — gate-switch 实证闸

## 用途与触发

01_workflows.md 规则通胀拆分守护闸（2026-08-20 REFORM-GATE 判 A，Shard A 落地）：① 主文件瘦身 ≤300 行（强制规则全文+分片索引表+导航）；② 六个分片文件存在；③ 分片来源注记齐全（6 处）；④⑤ 章节级旧锚点断链清零——只检查可机械判模式：`01_workflows.md` 后 4 字符内接 `###`（Markdown 章节锚点引用）或接 `技能调度总表`，rules/ 与 skills/ 下命中数必须为 0。历史溯源类引用（09 归档、pm 重建注记）不在机械可判范围，由 result 文件人工清单覆盖。

## 扳动命令

```bash
python3 ~/.agents/skills/rules_inflation_guard/scripts/gate_switch.py --spec ~/.agents/skills/rules_inflation_guard/scripts/specs/rules_inflation_guard.json
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
