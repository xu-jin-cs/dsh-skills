---
name: archmap_diff_freshness
description: "archmap 复盘前 diff 留痕固定卡点（REFORM-GATE 激活战役 item1，2026-08-15 裁定）：校验 {project}/archmap/diff_history.jsonl 存在、非 0 字节空壳、且 mtime 晚于 {work_start}（复盘工作期起点，--se"
---

# archmap_diff_freshness — gate-switch 实证闸

## 用途与触发

archmap 复盘前 diff 留痕固定卡点（REFORM-GATE 激活战役 item1，2026-08-15 裁定）：校验 {project}/archmap/diff_history.jsonl 存在、非 0 字节空壳、且 mtime 晚于 {work_start}（复盘工作期起点，--set 绑定传入：标记文件路径/epoch秒/ISO8601）。A=本工作期 diff 留痕真实存在，放行复盘；B=留痕缺失/空壳/陈旧，violations 即违例清单，须先执行 archmap +diff 再重扳。背景：某引擎项目 diff_history.jsonl 建成至今 0 字节，prompt 约定已被实证失效（0/N 激活），故判定权收归机械门禁。

## 扳动命令

```bash
python3 ~/.agents/skills/archmap_diff_freshness/scripts/gate_switch.py --spec ~/.agents/skills/archmap_diff_freshness/scripts/specs/archmap_diff_freshness.json --set project=<project> --set work_start=<work_start>
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
