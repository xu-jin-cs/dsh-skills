---
name: retro-skill-dispatcher
description: >-
  Retro-to-Skill dispatcher. 两种模式：MATCH模式（流程B Phase 1.5）— Bug诊断时检查经验库（retro registry）匹配历史问题特征，匹配成功则lazy-load对应retro技能并入开发指派指令；
  GENERATE模式（流程C Step 2.5）— 复盘时将分类为[SKILL.md]的经验自动生成可注册、可检索、可调度的独立SKILL.md文件，写入经验库（retro registry）。
  项目经理直接使用，无需人工二次配置。
---

# retro-skill-dispatcher — 复盘经验Skill化自动调度

> **定位：** 连通复盘经验与运行时Bug修复的桥梁。复盘中的问题+解决方案自动封装为可复用Skill，后续同类问题自动匹配调用。

> **经验库目录约定：** 本技能所称「经验库」即复盘经验 registry 的通用表述，根目录可用环境变量 `RETRO_REGISTRY_DIR` 指定，默认 `~/.dsh/retro-experience-registry`；文中 `$RETRO_REGISTRY_DIR/...` 均指经验库内路径。

## 职责边界

| 负责 | 不负责 |
|:----|:-------|
| 流程B Phase 1.5：匹配历史retro技能 | Bug诊断（属于流程B Phase 1） |
| 流程C Step 2.5：自动生成retro技能 | Bug修复执行（属于流程B Phase 2） |
| 维护 registry-index.json | 复盘经验分类（属于流程C Step 2） |
| lazy-load 匹配技能内容 | 积分制结算 |

## 模式1：MATCH（流程B Phase 1.5 — Bug诊断后匹配）

> **分流/准入判定禁止手写（2026-08-15 裁定，门禁机制机械判定）：分流先跑 `scripts/dispatcher_gate.py route` 照抄 route；GENERATE 准入必须通过门禁机制（gate）判 A（准入规格：dispatcher_admission）才许生成。**
> MATCH 匹配分数同样禁止心算：跑 `scripts/dispatcher_gate.py match --context "<诊断语境>" [--role R] [--bug-type T]` 照抄 score 与 matched。

### 前置条件
- [ ] Bug诊断已完成（含根因、归属、影响范围）
- [ ] 诊断报告已输出
- [ ] 以下文件存在：`$RETRO_REGISTRY_DIR/registry-index.json`（经验库目录，见文首约定）

### 执行步骤

**Step 1 — 检查Registry状态：**
```bash
if [ -f "$RETRO_REGISTRY_DIR/registry-index.json" ]; then
  echo "registry exists"
  cat "$RETRO_REGISTRY_DIR/registry-index.json" | python3 -c "
import json,sys
data = json.load(sys.stdin)
print(f'entries: {len(data.get(\"entries\",[]))}')
for e in data.get('entries',[]):
  print(f'  - {e[\"skill_id\"]}: {e[\"description\"]}')
"
else
  echo "registry not found — first project scenario, skip matching"
fi
```
Registry为空或不存在 → 输出 `[retro-skill-dispatcher] No retro skills available`，退出匹配。

**Step 2 — 从Bug诊断报告提取问题特征：**
从Bug诊断结果中提取以下字段，输出为结构化摘要：
```
Problem Signature Extracted:
  tokens: [从Bug标题和描述中提取的关键词，去停用词]
  role: [backend-engineer | frontend-development | ...]
  bug_type: [security | ui | logic | performance | config | data | api]
  severity: [critical | high | medium | low]
  error_phrases: [错误信息中的精确短语]
```

**Step 3 — 计算匹配分数：**
对 registry-index.json 中每个 entry 执行：

| 维度 | 权重 | 计算方式 |
|:----|:----:|:---------|
| trigger_phrases 精确短语匹配（强证据层） | 30% | Bug描述中是否包含entry的trigger_phrases（子串匹配），任一匹配则1.0（2026-08-20 仲裁制裁定 50%→30%，见下） |
| trigger_phrases AND 共现匹配（弱证据层） | 15% | 字符串短语现场经 `_seg_words` 拆成 3 成分词，全部在输入出现即 1.0（不要求相邻/顺序，与强档互斥不重复计；2026-08-20 AND 通道，权重水位标定 w*=0.15，见下） |
| trigger_keywords 关键词重叠 | 40% | `|tokens ∩ keywords| / |tokens|`（去重计数） |
| affected_role 角色匹配 | 5% | 诊断角色 == entry角色 → 1.0，否则 0 |
| bug_type 类型匹配 | 5% | 诊断类型 == entry类型 → 1.0，否则 0 |

**总分 = 精确短语×0.30 + AND共现×0.15 + 关键词重叠×0.40 + 角色×0.05 + 类型×0.05**

> **AND 共现通道（2026-08-20 深夜落地，REFORM-GATE 判 A，交接任务书 HANDOFF-3word-and-channel.md 第三节）**：θ=0.25 语义质量闸后幸存的 3 词短语"有效但硬拼接"——成分词都对，但用户拆着说（"回滚完了但是还有残留"）时 substring 要求字面相邻永远漏（真实正样本基线命中仅 12.5%）。AND 弱证据层：成分全部共现即计 0.15，单通道恰好落候选带下沿入仲裁、不直接放行。实测：真实正样本命中 12.5%→25.0%（24 条口径）；三轮仿真候选召回 61.1%±0.8% / 严误触 1.2% / 宽误触 3.5%±0.0%（红线 ≤5%、方差 ≤5pt 全过）。NP 水位标定：w∈{0.15,0.18,0.20} 召回并列，取最保守 0.15。回退开关：`RETRO_MATCH_AND=0` 单关弱证据层。设计边界：触发面被 θ 闸打空的技能（37 条）无短语可拆，不受本通道影响。证据：`runtime/and_channel_report.json`。

> **仲裁制（2026-08-20 召回率提升方案落地，REFORM-GATE 判 A）**：短语命中不再直接放行——单通道短语命中最高 0.30+0.05+0.05=0.40 < 0.50，自动落入近似召回带由 Agent 语义仲裁；多通道组合证据 ≥0.50 仍可自动注入。回退开关：`RETRO_MATCH_PHRASE=0` 一键关闭短语通道。触发词双源提炼：技能正文+provenance 原文 + 生产正样本（audit_logs SKILL_AUTO_MATCH.input_snippet，≤3，脏样本成分零重叠过滤）；容量配置驱动 `generation.max_trigger_phrases`（当前 32，由 recall_maximizer.py 联合迭代寻优标定：floor 寻优→NP 标定 B→添加候选词→往复至增益<1pt 收敛，终态召回 78.8%/严误触 1.0%/宽误触 3.0%，方案全文见 registry docs/trigger_scheme_max_recall.md）。

默认阈值：**0.50**（可从 `registry-config.json` 的 `matching.threshold` 读取）

**Step 4 — 筛选最佳匹配：**
- 取分数 >= 阈值的 entry，按分数降序排列
- 最高分为匹配结果
- 平分时取 frequency 较高的（更经过验证的）
- 最高分 < 阈值 → 无匹配，输出 `[retro-skill-dispatcher] No match (best: X.XX < Y.YY)`

**Step 5 — Lazy-Load 匹配技能（匹配成功时）：**
读取匹配 entry 对应的 SKILL.md 文件：
```
$RETRO_REGISTRY_DIR/skills/{skill_dir}/SKILL.md
```

更新 registry-index.json:
- 该 entry 的 `match_count` +1
- `last_matched` 设为当前时间戳

**Step 6 — 输出匹配摘要并注入开发指令：**

匹配成功时输出：
```
━━ retro-skill-dispatcher MATCH ━━━━━━━━━━━━━━━━━━━━━━
Result: ✅ MATCH FOUND
Skill: {skill_id} (score: X.XX)
Source: {source_project} retro
Match Signals:
  ✅ Exact phrase: {匹配的短语}
  ✅ Keyword overlap: {N}/{M} tokens matched
  ✅ Role: {role}

━━ Lazy-Loaded Skill ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[以下为该retro技能的Resolution Steps，完整读取后并入开发指派指令]
{SKILL.md内容}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dispatch: PM将此技能内容连同Bug指派指令一并传递给开发工程师。
开发工程师：先阅读Resolution Steps确认问题模式匹配，再按Self-Healing Validation执行验证。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

匹配失败时输出：
```
━━ retro-skill-dispatcher MATCH ━━━━━━━━━━━━━━━━━━━━━━
Result: ❌ NO MATCH (best: X.XX < Y.YY threshold)
Action: Proceeding with standard Phase 2 fix flow
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 近似召回带（2026-08-16 新增，retro-match.sh 已内置）

打分权重与 0.50 自动命中阈值**保持不变**；无 ≥0.50 命中时不再完全静默：

- **候选带下沿 B\*=0.15（2026-08-20 召回最大化标定，原 0.20）**：legacy_total（触发词通道举证，短语0.30+AND共现0.15+关键词0.40+角色0.05+类型0.05）≥ 0.15 且融合分 < 0.50 的候选按分降序列出 **≤3 条**「🔍 近似候选」（skill_id / score / description / overlap_keywords / SKILL.md 路径），写入 `_active_match.md` 并同步打印到控制台。波段扫描三轮实证：fused 融合分任何下沿误触 >5%（混合通道技术类输入 67% 误触），legacy 通道 B=0.15 召回 56.8%/误触 1.0% 为 FP≤5% 下召回最大点；下沿可由 `registry-config.json matching.candidate_band_floor` 调整；
- 近似候选**不自动注入**：由 Agent 语义判断是否适用，适用则手动加载对应 SKILL.md（不更新 match_count、不走审计）；
- **score ≥ 0.50 才自动注入** Resolution Steps 并 POST SKILL_AUTO_MATCH 审计；全部 < 0.20 时保持原 NO MATCH 静默行为。

### 异常处理

| 场景 | 处理 |
|:----|:-----|
| registry-index.json 缺失 | 静默跳过，输出"registry不存在，首次使用场景"，继续Phase 2 |
| registry-index.json 解析错误 | 输出"Registry解析失败，请检查JSON格式"，跳过匹配 |
| SKILL.md 文件在磁盘丢失 | 输出"Entry X引用的SKILL.md不存在，从索引中移除"，继续下一个 |
| 所有匹配低于阈值 | 报告最佳分数；0.20~0.50 候选按近似召回带列出 ≤3 条供语义判断，全部 <0.20 则正常进入Phase 2 |
| 匹配成功但 entry 关联文件缺失 | 输出警告并从索引移除该 entry |

---

## 模式2：GENERATE（流程C Step 2.5 — 复盘后自动生成Retro技能）

> **架构修正：** 复盘知识库不再只保存 registry-index.json 索引。
> **强制执行顺序：先向量库入库，再脉象索引。** 向量失败则终止，不继续写索引。（索引侧机械核验 → 见「执行时序」节 registry_integrity 闸）

### 经验内容通用化标准（2026-08-10 新增，写入 _retro_experiences.json 前强制）

复盘生成器是机械模板切片（content[:80/150/200] 原文入 SKILL.md 与 trigger 字段），**不做语义泛化**——写入什么就产出什么。因此通用化必须在经验捕获时完成：

1. **通用形式强制**：content 写「问题模式 + 根因类别 + 处置规则」，剥离项目专有名词、文件路径行号、产品名、日期、一次性数值。项目细节留在复盘报告正文，不入库。
   - 正例：「外部检索类需求必须先实证目标站点的查询语法与反爬规则，禁止凭通用经验编造请求参数」
   - 反例：「百度图片检索句式标准化XX颜色的XX风格背景壁纸」（目标站点特例，匹配面为零）
2. **双要素自检**：每条 content 必须能回答——为什么好（消除什么返工/风险）+ 触发信号（下次见到什么现象该想起它）。触发信号写进 content 开头，供 _extract_phrases 提取为 trigger_phrases，匹配面才宽。
3. **入库闸门**：「换一个全新项目，这条还成立吗？」不成立 → 泛化后再写；泛化不了的纯事故档案 → 标 reuse_flag=偶发，仅留复盘报告，不进 GENERATE。
4. GENERATE 内置 lint（dispatcher_generate.py）会对含项目名/路径行号等针对性标记的条目打 `generality: "targeted"` 标记并输出告警清单；被标条目进入后续批量泛化队列，不阻断当次收尾。

### 触发字段生成规范（2026-08-12 新增，写入 registry 前强制 lint；2026-08-20 v2 用户终裁：触发词必须恰好 3 个分词）

> **⚠️ 2026-08-21 用户裁定废止（新增技能不再生成触发词）：** 复盘生成技能不再配置触发词，
> 技能描述并入「使用者/触发者」的使用者技能表（经验机制），派任务时全量载入。
> 本节及下列 MATCH 触发词规则仅对**存量带触发词技能**的运行时 MATCH 保留参考，不再约束新生成。
> 原生成端触发词逻辑已备份至 `archive/trigger_mechanism_backup_20260821/`。

MATCH 机制决定触发字段必须按通道分别设计，违反即出生即低频（183 条中 175 条 match_count=0 的实证根因）：

0. **3词硬闸（2026-08-20 v2 用户终裁，最高优先）**：触发词（trigger_phrases）必须是**恰好 3 个分词组成的短语**（jieba 分词口径，如「回滚后数据残留」=回滚后/数据/残留、「api报错超时」=api/报错/超时）。一个技能可有 1~N 个触发词，但每个都必须 3 个词——**不是 3 个词的全部打回**（生成端 3 词滑窗结构性只产 3 词候选 + round-trip 重切校验，lint 端 `_three_word_ok` 复判打回，双端同一 `_seg_words` 原语保证一致）。成分词要求：中文成分 ≥2 字、英文整词 ≥2 字符、非黑名单/虚词/纯数字；压实总长 4~15 字；全部成分必须语料见证（df≥1）且不超过泛化上限。语料来源 = 用户历史会话记录（`_user_corpus_freq`）。
1. **中文 → 只能进 trigger_phrases**：MATCH 对用户输入按 maximal-run 分词（「时间不对」是 1 个 token），trigger_keywords 是集合精确相交——中文关键词除非与用户整段输入完全相等否则永不命中。中文触发词走 substring 通道（用户会怎么说这个症状，不是规则怎么写），形态服从第 0 条 3词硬闸。
   - 正例：`时间不对了`（时间/不/对了类 3 词）`迁移后数据不对`（迁移后/数据/不对）`api报错超时`
   - 反例：`【通用】单机本地工具的落库时间若存 UTC 且序列化不带时区标记`（24字规则句，substring 永不命中）；`回滚` `utc`（不足 3 词，打回）
2. **英文/数字/技术标识 → 进 trigger_keywords**：exact token 匹配对英文有效（`utc` `docker` `heredoc`），中文长碎片（>12字）由 lint 直接剔除。关键词通道维持 3 字硬闸（中文成分恰好 3 字），不在 v2 3词终裁范围。
3. **字面量全局唯一**：短语通道单条命中占 0.30 权重（仲裁制后仍占候选池一席），同一字面量被多条技能持有 = 一次输入候选池混入多条技能（用户裁决禁止重叠触发）。lint 会将与既有条目重复的字面量丢弃并告警；语义近邻技能组必须错开措辞（如「时间不对了」归 be-068，「显示不对了」归 pm-108）。
3.1 **AND-token 数组短语已废弃（2026-08-20 用户终裁）**：数组短语一律丢弃，生成端无数组选项，lint 端拦截存量/池携残留。**但拆说场景的匹配端补偿已由 AND 共现弱证据层接管（2026-08-20 深夜用户显式复活，仅限匹配端现场拆词、存储格式不动）**——字符串短语的 3 成分词全部在输入共现即计 0.15 弱证据入仲裁带，与数组短语"存储即数组"的旧时代有本质分层区别（见 Step 3 AND 通道注）。
3.2 **月度命中审计（反馈闭环）**：每月运行经验库命中审计脚本（trigger_match_audit，位于经验库 scripts/ 目录），输出 ①match_count=0 技能清单（补同义词簇）②字面量重复校验 ③疑似过宽短语清单（收窄）。用真实命中数据调词，禁止一次性猜完不复查。
3.3 **月度 B/A 比率审计（开关留痕闭环）**：每月运行并行调度开关留痕审计（dispatch_switch_audit），输出 ①全量与近30天 A/B/CLARIFY/VIOLATION 分布与 B/A 比率 ②冒烟测试批剔除（同秒 ≥3 条）③B 档注水嫌疑清单（dep_reason <10 字符或为空）④ALERT 告警（作战 B/A >1.5 或存在 VIOLATION，须逐条复核 B 档理由）。`--strict` 时有 ALERT 则 exit 1，供复盘门禁。
4. **池条目可显式携带 `triggers` 字段**：`"triggers": {"phrases": [...], "keywords": [...]}`，复盘时由人工按本节规范拟定。**但池携触发词只是候选（2026-08-17 用户裁定，REFORM-GATE 判A落地）：生成器出口前最后一步自动过 `_user_corpus_freq()` 语料对齐过滤——任何成分 df=0（用户历史语料未说过的死词）整条剔除并大声告警，全灭则回退机械提取（本身已语料对齐）。禁止把触发词生成器当独立步骤单独执行**（提示词触发=概率执行，已实证失效）；`regenerate_trigger_phrases.py` 仅作存量清算工具保留。
5. lint 三道闸（`_lint_triggers`，非阻断但全量告警）：剥离【通用】前缀 → 剔除中文长碎片关键词 → 字面量查重丢弃。

### 前置条件
- [ ] 流程C Step 2 已完成（所有角色提交了最短路径记录 + 5问法复盘）
- [ ] 各角色经验已按 `[SKILL.md / CLAUDE.md / 经验文档]` 完成分类
- [ ] 以下文件存在：`$RETRO_REGISTRY_DIR/registry-index.json`（经验库目录，见文首约定）
- [ ] 以下文件存在：`$RETRO_REGISTRY_DIR/dispatcher_generate_config.json`
- [ ] 以下文件存在：`$RETRO_REGISTRY_DIR/retro_check_result.json`

### ID编码规范（强制，所有复盘通用）

> 2026-08-12 起废除 p 系编码（`p001`/`p001_001`）：并行会话凭记忆顺延序号导致撞号（p130 双会话重复实证）。序号/ID 属系统生成类字段，禁止手写。（机械拦截 → 见「执行时序」节 registry_integrity 闸）

1. **skill_id 由 `allocate_skill_id` 系统分配**（`retro-{role}-{NNN}-{语义后缀}`），NNN 由 registry 现存条目数递增，任何角色禁止手写。（形态与撞号机械核验 → 见「执行时序」节 registry_integrity 闸）
2. **serial_number = skill_id**：池条目不填 `id` 字段时 dispatcher 自动回退（`serial = sid or skill_id`）， serial 与技能一一对应、天然唯一。
3. 亲子关系通过 registry 条目的 `source_project` / `created_at` 溯源，不再维护 parent_sendanceId / child_ids 手填字段。

### 19字段向量库合规（LanceDB tcm_tongue_chunks）

所有写入 LanceDB 的 retro 条目必须对齐以下19字段约束：

| # | 字段 | 取值规则 |
|:-:|:-----|:---------|
| 1 | chunk_id | 系统分配整数主键（SqliteRangeIdGenerator），禁止手写（可查时整数唯一性机械核验 → 见「执行时序」节 registry_integrity 闸） |
| 2 | sendanceId | **已废除（2026-08-12）**，保留字段写空字符串 |
| 3 | content | 复盘经验的具体内容描述 |
| 4 | summary | 产出物摘要，如 "系统配置"、"调度时机" |
| 5 | source_module | 固定值：`retro-skill-dispatcher` |
| 6 | business_category | 固定值：**`佳脉`**（复盘经验统一归类于此脉象） |
| 7 | create_time | ISO 8601 时间戳 |
| 8 | parent_sendanceId | **已废除（2026-08-12）**，保留字段写空字符串 |
| 9 | child_ids | **已废除（2026-08-12）**，保留字段写空数组 |
| 10 | target_agent | 本条产出物归属 Agent 角色缩写 |
| 11 | reuse_flag | 可复用 / 偶发 |
| 12 | coating_tag | 固定值：`复盘经验` |
| 13 | doc_category | 固定值：`retro` |
| 14 | project_type | 来源项目类型 |
| 15 | agent_role | 产生本条经验的 Agent 角色 |
| 16 | project_name | 来源项目名称 |
| 17 | node_type | 固定值：`archive` |
| 18 | chunk_seq | 子条目在本次复盘中的序号（1-based） |
| 19 | embedding | 384维 all-MiniLM-L6-v2 向量（由 ETL/collect_retro 自动生成） |

### 准入控制（dispatcher_generate_config.json）

> **分流/准入判定禁止手写（2026-08-15 裁定，门禁机制机械判定）：分流先跑 `scripts/dispatcher_gate.py route` 照抄 route；GENERATE 准入必须通过门禁机制（gate）判 A（准入规格：dispatcher_admission）才许生成。**
>
> **diff 留痕判定禁止手写（2026-08-15 裁定，门禁机制机械判定，复盘前固定卡点）：GENERATE 准入过 dispatcher_admission 门禁之前，必须先过「diff 留痕新鲜度」门禁（archmap_diff_freshness，参数 --set project=<项目根路径> --set work_start=<复盘工作期起点：标记文件路径/epoch秒/ISO8601>）判 A——archmap/diff_history.jsonl 存在、非 0 字节空壳、新于工作期起点——才许继续准入流程；判 B = archmap diff 留痕空转，须先执行 archmap +diff 补留痕后重判，violations 即违例。项目无 archmap/ 目录时本闸不适用，声明理由后跳过。**

GENERATE 模式不再无条件执行。执行前先检查 `dispatcher_generate_config.json`：

```json
{
  "global_switch": true,
  "trigger_config": {
    "fixed_phrases": ["复盘", "验收通过", "项目完成", "收尾", "结项"],
    "llm_confidence_threshold": 0.72,
    "skip_reason_text": "本次复盘无经验产出",
    "skip_reason_abort_line": "当前复盘无经验产出，GENERATE 跳过"
  },
  "workflow_switch": {
    "vector_db_enabled": true,
    "generate_skill": true,
    "register_index": true,
    "role_binding": true,
    "harness_audit": true
  }
}
```

**准入判定流程（PM 执行）：**
1. 读取 `dispatcher_generate_config.json`
2. `global_switch` 为 `false` → 输出 `[retro-skill-dispatcher] GENERATE 全局开关关闭，跳过`，直接退出
3. 读取 `retro_check_result.json` 的 `generate_status`
4. `generate_status == "skipped"` 且 `skip_reason` 包含 `skip_reason_text` → 输出 `skip_reason_abort_line`，直接退出
5. 检查 `workflow_switch.vector_db_enabled` — 必须为 `true`，否则输出阻断

### 执行时序（强制执行，步骤不可调换）

> **存储顺序铁律（不可逆）：先存向量数据库（LanceDB tcm_tongue_chunks），再存脉象索引（registry-index.json）。**
> 存储顺序违反则入库时序不可追溯，视为系统缺陷。
> **do_generate() 函数为 GENERATE 模式的单一执行入口。所有步骤通过 do_generate() 调用，不单独执行子步骤。**

#### do_generate(project_name, retro_data) — 单一执行入口

```python
def do_generate(project_name: str, retro_data: dict) -> dict:
    """
    GENERATE 单一执行入口。
    向量库优先，失败则终止。
    
    返回: {"status": "success"|"failed",
           "chunks_written": N,
           "skills_generated": [...],
           "registry_updated": bool}
    """
    # ── 前置检查 ──
    config = load_dispatcher_config()
    if not config["global_switch"]:
        return {"status": "skipped", "reason": "全局开关关闭"}
    
    check_result = load_check_result()
    if check_result.get("generate_status") == "skipped":
        if config["trigger_config"]["skip_reason_text"] in \
           check_result.get("skip_reason", ""):
            return {"status": "skipped",
                    "reason": config["trigger_config"]["skip_reason_abort_line"]}
    
    # ── Step 1: 向量入库（先于脉象索引）──
    # 强制：失败则终止，不继续写索引
    try:
        from tongue_diagnosis.etl.retro_collector import collect_retro
        result = collect_retro(project_name, retro_data)
        if not result.get("chunks_written", 0) > 0:
            raise RuntimeError("向量入库返回0条写入")
    except Exception as e:
        # 向量入库失败 → 终止 GENERATE
        update_check_result(status="failed",
                            error=f"向量入库失败: {e}")
        return {"status": "failed", "error": str(e)}
    
    chunks_written = result.get("chunks_written", 0)
    
    # ── Step 2: 逐条生成 SKILL.md（provenance.json 已废止停写） ──
    skills_generated = []
    for entry in retro_data.get("entries", []):
        skill_id = allocate_skill_id(entry["role"], entry["seq"], entry["desc"])
        write_skill_md(skill_id, entry)
        # write_provenance_json 已废止（08-16 裁定，08-22 停写落地）
        skills_generated.append(skill_id)
    
    # ── Step 3: 注册脉象索引 ──
    # dataset_tag: 佳脉（所有复盘经验统一使用此标签）
    registry_ok = register_to_index(skills_generated,
                                    dataset_tag="佳脉")
    role_link_ok = update_role_retro_links(skills_generated)
    
    # ── Step 4: 引擎审计（Xj-engine）──
    audit_ok = write_harness_audit(
        skills=skills_generated,
        chunks_written=chunks_written
    )
    
    # ── Step 5: 状态写回 retro_check_result.json ──
    update_check_result(
        status="success",
        chunks_written=chunks_written,
        skills_generated=skills_generated,
        registry_updated=registry_ok,
        harness_audited=audit_ok
    )
    
    # ── Step 6: auto-memory ──
    write_auto_memory(skills_generated)
    
    return {"status": "success",
            "chunks_written": chunks_written,
            "skills_generated": skills_generated,
            "registry_updated": registry_ok}
```

**存储顺序验证：** do_generate() 返回后，PM 必须确认 Step 1（向量入库）的 `chunks_written > 0` 且 Step 3（脉象索引）的 `registry_updated == true`。任一不满足 → 报告 GENERATE 未完成。

> **注册完整性判定禁止手写（2026-08-16 裁定，门禁机制机械判定，本闸合并 p 系禁制/形态/NNN 撞号/chunk_id 四处条款为单焊点）：Step 3 注册脉象索引后、声称"已注册"前，必须过门禁机制（gate，准入规格：registry_integrity）判 A——新增条目形态 retro-{role}-{NNN}-*、无手写 p 系、NNN 无撞号、chunk_id 可查时整数唯一——才允许声称注册完成；判 B 按 violations 修复索引后重判。入库时序（向量库先于索引）由 do_generate() 写入路径保证，机械判据不存在，脚本注释标软层。**

### 系统边界说明

两个系统共享 `tcm_tongue_chunks`，各有独立索引层：

| 系统 | 写入路径 | 索引层 | 业务分类 |
|:-----|:---------|:-------|:---------|
| 系统A：rag_doc.md via ETL | docs_raw/ → etl_pipeline.py | LanceDB 向量检索 | 按目录映射（佳脉/平和脉/...） |
| 系统B：retro GENERATE | do_generate() → collect_retro() → etl_single_doc() | registry-index.json + role-retro-links.json | **全部为 佳脉** |

**查询路径（retro_query.py）：** 系统A + 系统B 的数据在查询时合并。详见 retro_query.py 的 index→vector 模式。

### 输出报告格式

每条经验生成时分别输出（2026-08-21 起不再生成触发词，技能描述并入使用者/触发者技能表）：

```
🛠 技能生成
{skill_id}
🟡 {severity}
{description}
{role}
{timestamp}
👤 使用角色: {role}
📂 问题类型: {bug_type}
🔁 调度时机: 复盘后并入技能表，派任务时全量载入
```

末尾输出 `━━ GENERATE 完成 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━` 一行。

### 配置变更同步（GENERATE 后置阶段）

技能生成后，根据技能描述**判断是否需要修改对应 agent 的实际配置/规则文件**（经验文档/SKILL.md/规则文件/CLAUDE.md），如需变更则：

1. 修改实际文件
2. 通过引擎 et 契约（Xj-engine）投递 `CONFIG_AUTO_APPLY` 审计事件记录变更
3. 将变更纳入复盘变更文件清单

**判断标准：** 技能描述涉及流程/规则/配置缺陷，且修复方式可标准化 → 必须同步修改配置文件，不能只创建 SKILL.md。

> **同步声称实证（2026-08-15 裁定，门禁机制机械判定）：声称"配置已同步"时，必须过门禁机制（gate，准入规格：dispatcher_config_sync，参数 --set config=<被改配置文件> --set doc=<应同步文档>）判 A——文档新于配置变更——才允许声称"已同步"；判 B = 同步缺失，violations 即证据。**

### 异常处理

| 场景 | 处理 |
|:----|:-----|
| dispatcher_generate_config.json 缺失 | 输出"配置文件不存在，GENERATE 跳过" |
| dispatcher_generate_config.json global_switch=false | 输出"全局开关关闭，跳过" |
| retro_check_result.json generate_status=skipped 匹配 skip_reason | 输出告警行，直接退出 |
| 向量入库失败（collect_retro 异常/0条写入） | **终止 GENERATE**，写 retro_check_result.json status=failed |
| 文件写入 SKILL.md 失败 | 输出警告，继续下一经验 |
| registry-index.json 无法写入 | 输出警告，手动追加 entry |
| 同名skill_id冲突 | SEQ递增处理，永不覆盖已有目录 |
| 引擎（Xj-engine）服务不可达 | 日志告警不阻断流程（审计降级），**但必须把未投递的审计记录（action/operator/details/generated_skills/计划时间）落盘到 `$RETRO_REGISTRY_DIR/runtime/_audit_backfill_queue.json`；引擎恢复后由下一执行方或人工按队列补录（每条技能独立 SKILL_AUTO_GENERATE，created_at 用真实生成时间），补录后清空队列。禁止只告警不留痕——2026-08-12 实证 5 条技能审计静默缺失** |
| 无技能产出的事件入库（2026-08-16 用户裁定） | **禁止**——`SKILL_AUTO_GENERATE` 必须携带非空 `details.generated_skills`，无产出连入库步骤都不走（降级补录同样适用，details 禁止用 skill_id_prefix 等替代字段）；同理 `CONFIG_AUTO_APPLY` 必须携带非空 `details.changes`（禁止用 files 等替代字段，前端只消费 changes）。引擎 et 契约（Xj-engine）已焊死机械门禁：缺字段直接拒绝。实证违例 #1265-1269 已清除、#1249 已补字段修复 |
| 技能误发为 CONFIG_AUTO_APPLY | 删除 audit_logs 中对应行，重新以 SKILL_AUTO_GENERATE 逐条 POST |
| 生成即并入使用者技能表（2026-08-21 用户裁定改版：复利不赌运行时匹配自觉；**固化是核心目的，注入先于 registry 写盘；不再配置触发词**） | GENERATE 顺序：生成技能 → `inject_into_role_skills` 将技能描述并入对应使用者角色（affected_role 映射）的使用者技能表（经验机制：registry.json + entries/*.md，幂等全量派生）+ 重写 `AUTO-RETRO-INJECT` 内联索引块（含「第零步：派任务时全量载入技能表」，无触发词列）。pm 仅在自身是使用者（affected_role 含 pm）时并入其技能表，不再全量合并各角色实现细节（2026-08-21 v2 用户裁定，避免 pm 表膨胀与无关载入）→ **单刀双掷开关 `inject_fuse.py` 增量熔断（每个新 skill_id 必须已固化进对应角色的使用者技能表，0=A 放行 / 2=B 则 registry 不写盘、审计与向量不同步，修复后重跑幂等）** → 通过才写 registry → LanceDB/审计。存量回填/重注入用 `--inject-only`（末尾自动跑全量熔断）。角色别名映射见脚本 ROLE_SKILL_MAP。原触发词机制已备份至 `archive/trigger_mechanism_backup_20260821/`。全条目归档的角色在重注入时自动清空其使用者技能表与内联块 |
| 双轨定级（2026-08-16 REFORM-GATE 判 A：复用 expert-loop 领域/专项机制） | registry entry 带 `skill_level: domain|specialty`——生成时机械定级（命中针对性标记 generality=targeted 强制 specialty，经验条目可显式 `triggers.level` 覆盖）；注入块按双轨分区渲染：🧭 领域=检查维度融入式、🎯 专项=场景触发升格执行主线；`trigger_match_audit.py` ④按 角色×问题类型 聚类 specialty，≥3 张同类输出晋升回顾清单（机械计数，抽象动作走语义）。晋升通道：`promote_internalization.py` 消费 expert-loop 内化卡 |
| 技能生命周期三操作（2026-08-16 用户裁定：防膨胀，不只追加） | **新增**=常规 GENERATE；**替换**=经验条目带 `supersedes: [旧skill_id...]`，生成成功即归档旧技能（领域晋升吸收专项走此路）；**删除**=`python3 dispatcher_generate.py --archive <skill_id> --reason "..."`。归档为墓碑式：entry 打 `status=archived`+目录移入 `archive/`；**归档传播全数据源同步删除（2026-08-16 裁定：agent 侧删了数据源必须同步删，否则前后不同步）**——注入块/MATCH/熔断/月度审计按 status 过滤，LanceDB 向量行由 `_purge_skill_from_datasources` 物理删除，role-retro-links 绑定剔除，engine retro_query（index_search/vector_search）读取层过滤归档事件 POST `EVOLUTION_AUTO_ARCHIVE` 审计留痕。搭配双轨晋升形成闭环：专项攒≥3 → 抽象领域技能（supersedes 吸收旧专项）→ 注入块自动收敛 |
| 引擎生命周期契约（2026-08-16 用户裁定：入库/删除只调引擎，一条链路走完；v2 重写为自包含 RetroETLEngine） | **唯一入口 `$RETRO_REGISTRY_DIR/engine/kernel.py::retro_etl(payload)`**（参考引擎 et 契约架构（Xj-engine）：contract 校验 → resource_control 前检 → 固定步骤链 → outbox 记账 → delivery；code=success/reject/block/error）。三操作复用同一引擎：`op=write`（稳定内容哈希 chunk_id→BGE-M3 嵌入→LanceDB 幂等覆写→BM25 三重索引→outbox ready，doc_unique_id=skill_id）、`op=delete`（doc_unique_id 精确定位→LanceDB 删行→旧版引擎库 SQL 清理→BM25 重建→outbox deleted）、`op=batch`（**晋升合并事务：同一边界内删旧增新+BM25 单次重建，逐项记账，失败项落积压幂等重试**——GENERATE 带 supersedes 时走此路，且引擎事务排在注入熔断之后，防"判 B 回滚 registry 而物理删除已执行"的前后不同步）、`op=reconcile`（registry↔LanceDB↔outbox 三向对账）。store/embed/bm25 全本地实现，零引擎代码/服务依赖——引擎改造或离线期间本链路自治。写入积压 `_lancedb_backlog`、删除积压 `_purge_backlog.jsonl` 均本地回血，仅审计投递需引擎（Xj-engine）在线。注意：BM25 全量重建分钟级，调用方耐心等勿中断（实证 2026-08-16 中断致 journal 死锁）。引擎旧版 REST 契约端点属 v1 残留，以 et 契约（Xj-engine）为准，待其引擎稳定后清理 |


## 引擎接线（Xj-engine）

本技能为通用公开版，已剥离私有宿主依赖。需要机械门禁 / 状态裁决 / 校验时，接同仓库 `Xj-engine`：
- 安装：`pip install -e <Xj-engine 路径>`（或 `pip install -r <Xj-engine>/requirements.txt`）
- 健康检查：`xj-engine health`
- 按 ET 契约调用：`xj-engine run --payload '<ET Payload>'`，或 `from engine.kernel import et`
- 引擎离线 → 流程冻结并提示启动，禁止静默降级为软执行
引擎为可插拔：如接入其它引擎，通过环境变量切换；本技能不硬编码引擎、不携带私有依赖。
