---
name: gate-switch
description: 通用概率执行门禁骨架（实证族 L2 引擎）。任何"声称 X 已满足/已写入/已生成/已同步/已验收"的场景，把 X 写成检查项 spec JSON，引擎逐项机械核验：全过→掷点 A 放行，任一失败→掷点 B 阻断并列出违例（B 档理由自动生成）。治 LLM 三类顽疾：该做的没做、缺斤短两、伪造声称。检查原语：file_exists/file_min_size/json_field/glob_count/grep_count/mtime_after/script_exit。四态退出码（0=A/2=B/3=CLARIFY/4=VIOLATION），全程留痕。触发：验收判定、写入实证、证据核验、模式分流、交付完整性检查、部署准入等需要"机械可判的 0/1 门禁"场景。
---

# gate-switch — 通用概率执行门禁骨架（实证族 L2 引擎）

## 用途（解决什么问题）

LLM 执行流程时有三类高频失信：**该做的没做**（声称跑了测试其实没跑）、**缺斤短两**（18 项自检扫一眼就声明通过）、**伪造声称**（没读报告就写"验收通过"）。prompt 里写"必须/禁止"拦不住——因为判定权在模型自己手里。

gate-switch 把判定权从模型手里拿走：**你只写一份 spec JSON（要核验什么），引擎逐项机械核验，模型只能照抄结论**。新场景 = 写新 spec，引擎零改动。

与单刀双掷开关（parallel-dispatch 的 dispatch_switch，路由族：A/B 路径选择）互补：本引擎管"实证族"（声称 X → 机械核验 X）。

## 安装

```bash
# 一键（无需先 clone）
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install gate-switch

# 已 clone 仓库
cd dsh-skills && ./install.sh gate-switch
```

装进 `~/.dsh/skills/`（符号链接），DSH watcher 热加载即生效。零依赖（纯 Python stdlib）。

## 用法

```bash
python3 ~/.dsh/skills/gate-switch/scripts/gate_switch.py --spec <spec.json> [--set key=value ...]
```

退出码：`0`=A 全部通过放行 / `2`=B 有违例阻断（violations 即理由）/ `3`=CLARIFY 输入信号不足 / `4`=VIOLATION spec 非法。
留痕：`~/.agents/logs/gate_switch.jsonl`（可用 --log 改路径）。

## spec 格式（填充物，骨架冻结）

```json
{
  "gate": "门禁名",
  "desc": "用途与 A/B 语义说明",
  "checks": [
    {"type": "file_exists",   "path": "...", "label": "..."},
    {"type": "file_min_size", "path": "...", "bytes": 100},
    {"type": "json_field",    "path": "...", "field": "a.b.0.c", "op": "exists|not_empty|equals|in|min_len|min|max", "value": ...},
    {"type": "glob_count",    "pattern": "...", "op": "min|max|eq", "value": 1},
    {"type": "grep_count",    "pattern": "...", "path": "...", "op": "min|max|eq", "value": 1},
    {"type": "mtime_after",   "path": "...", "ref_path": "..."},
    {"type": "script_exit",   "cmd": "...", "expect": 0}
  ]
}
```

`{key}` 占位符由 `--set key=value` 注入。新增检查原语需 ≥2 独立场景举证（骨架冻结纪律）。

## 自带 spec 实例（specs/）

**通用型（任何项目可直接用，`--set` 注入路径即可）：**

| spec | 用途 |
|---|---|
| `acceptance_verdict.json` | 验收 verdict 禁手写：报告存在+签发字段+failed=0+passed≥1 |
| `test_executor_evidence.json` | 测试证据门：批次元数据+签发 hash+截图真实落盘 |
| `whitebox_mode.json` | 白盒 diff/full 模式分流（有基线增量/无基线全量） |
| `deploy_admission.json` | 部署准入：前后端交付物+测试全过+Bug 闭环 |
| `testlead_dispatch.json` | 测试三路下发门禁（缺哪路搁置哪路） |
| `ppt_extract_mode.json` | 模板路径分流（复刻/原创） |
| `dpm_section10.json` | 交互文档字段约束表存在性 |
| `reform_gate.json` | REFORM-GATE 改造收益框架填充完整性校验 |

**生态型（需配套技能脚本，外部用户作范例参考）：** `case_selfcheck / council_gate / sv_verdict / bug_fix_gate / task_breakdown / dispatcher_admission / process_audit_f/g / retro_match_score / spm_writeback / pm_writeback / ppt_direct_scorecard / frontend_testid / scope_boundary / retro_generate_token` —— 这些 spec 通过 `script_exit` 包装各技能的校验器脚本，展示"既有工具+薄壳门禁"的接入模式；没有对应技能时不可直接运行。

## L3 框架闸模板（templates/）

`L3_FRAMEWORK_TEMPLATE.md` — 思考级门禁骨架（REFORM-GATE 收益评估框架的通用化）：触发点/强制字段/终局判定/留痕四件 + 实例化五步法。新思考框架 = 克隆模板换字段 + 复制 reform_gate.json 换标记词。

## 方法论归属

强制填充门元方法族 L2 档：触发点焊在必经之路、判定禁止手写照抄输出、B 档强制理由、全程留痕反哺复盘。与路由族开关 dispatch_switch（在 `parallel-dispatch` 技能内）同属一族。

## 闸脚本/闸 spec 本体改动收尾纪律

凡修改本技能的 scripts/specs 或任何闸开关脚本，"声称已还原/已修复/已完成"前必须扳对应契约 spec（如 `plan_select_contract.json`）做全路径回归实证，禁止只跑 happy path 声称完成（2026-08-19 plan_select.py B 档被误删事故落地）；无对应契约 spec 时先写 spec（CLAIM-GATE 族既有规则）。
