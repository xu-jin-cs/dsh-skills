# 问题闸全量复审 · 撤除执行记录（2026-08-20）

> 依据：`~/.agents/logs/problem_gate_audit/REPORT_ALL96.md`（96 闸全量过滤：86 保留 / 9 撤除 / 1 改设），用户指令「允许撤，执行」。
> 方式：只 mv 不 rm（对齐 08-19 deadgate_purge 与备份卫生铁律），归档至 `specs/archive/`。

## 归档的 9 个 spec（撤除）
| spec | 撤除理由分类 |
|---|---|
| doc_freshness.json | 一次性迁移残渣当日已根治，一次性问题不配常设 |
| trigger_signal_scan.json | 一次性交付验收无挂点（注意：撤的是验收 spec，扫描脚本 trigger_signal_scan.py 与 trigger_signals.json 数据仍在役） |
| plan_first_gate.json | 宿主 PLAN-FIRST-GATE 08-18 被 plan-select 替代废止 |
| plan_first_audit.json | 同上（审计对象已死） |
| pm_writeback.json | 08-20 技能表化后被 spm_skill_entry 接管，死配置 |
| spm_writeback.json | 08-20 已宣布退役，spm_skill_entry 接管 |
| process_audit_f.json | 结构性永久判 B（强查已删除的 provenance 字段），写入端活闸兜底 |
| process_audit_g.json | 阈值结构性永久报警失去拦截语义，retro_hitrate_floor 兜底 |
| expert_promote.json | 正式晋升脚本自身 exit 2 同源校验已兜底，重复设防零增量 |

## 同步清理的 6 处挂接引用
1. `rules/04_dev_standard.md:134` — doc_freshness 兜底句 → 撤除注记
2. `skills/pm/flow.yml:463` — F/G 维度强制跑闸句 → 留软层语义审查
3. `skills/pm/SKILL.md:200` — retro-pm-212 条目 PLAN-FIRST-GATE → 替代+撤除注记
4. `skills/expert-loop/SKILL.md:37` — expert_promote 强制预检段 → --dry-run 即可
5. `skills/process-audit/SKILL.md:83` — process_audit_f 强制段 → 撤除注记+软层
6. `skills/process-audit/SKILL.md:120` — process_audit_g 强制段 → 撤除注记+软层

## 改设 1 闸（补挂钩子）
- `rules_inflation_guard.json` 保留，补挂复盘着陆防复发闸族点位：`gate-switch/data/trigger_signals.json` S-RETRO-WORDS must_pull + `~/.dsh/AGENTS.md` 触发清单「复盘着陆/引擎代码交付」行。补挂后活体验证扳动：判 A。

## 台账与安全留痕
- `specs/INDEX.md` 重生成：85 specs，与目录 glob 一致（防漂移纪律）
- mv 命令事前过 danger_cmd_gate 判 B（命中 mv 黑名单），用户显式批准「允许撤，执行」后人工执行，全程留痕 gate_switch.jsonl
- 清理后验证：强制扳动悬空引用 0 处、trigger_signals.json JSON 有效、spec 数=INDEX 数=85
