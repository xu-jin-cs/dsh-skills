---
name: dual-gates
description: 声明闸+查询闸 双闸落地（正式定稿版）。前置意图定性路由：通道①意图硬路由（信号真源 trigger_signals.json：安全S-DANGER-CMD/问题S-PROBLEM-GATE）→ is_danger/is_problem + must_pull 机械指令不经裁量；通道②严格2字词根白名单、词语边界匹配、无黑名单 → 命中才进查询闸做会话锚点定向溯源检索，只输出原始数据+溯源元信息，推理/有效性/废弃判定/打分全部后置下游推理层。杜绝无脑全量grep扫描。触发：/dual-gates、声明闸、查询闸、数据源检索前置判定、评估基准/方案/源码/历史记录读取前置路由。
---

# dual-gates — 声明闸 Declaration Gate + 查询闸 Query Gate（正式定稿版）

> 核心原则：前置意图定性 → 定向溯源查询；严格 2 字词根白名单、无黑名单、规避技能 Prompt 冲突；职责强隔离，查询链路只做定位与原始数据输出，推理、有效性判断全部后置。
> 适用场景：Agent 内数据源检索、评估基准/方案/源码/历史记录读取，杜绝无脑全量 grep 扫描。
> 执行脚本：`scripts/dual_gates.py`（相对本技能目录），判定禁止手写，必须扳脚本照抄输出。

## 1 整体架构与串联链路

```
用户/Agent 请求
    ↓
【声明闸】dual_gates.py declare（双通道，固定顺序）
    ├─ ✅ 意图硬路由命中（通道①优先：安全/问题） → is_danger/is_problem → must_pull 机械指令（不经裁量）
    ├─ ✅ 白名单命中（通道②） → is_query → 【查询闸】dual_gates.py query
    └─ ❌ 未命中 → not_query → 直接分流推理/生成链路，不进入查询闸
        ↓
【查询闸】输出原始数据+溯源元信息 → 交付下游推理层（有效性/废弃资产/解读/打分全在下游）
```

## 2 声明闸 Declaration Gate

- ✅ 职责：任务定性路由；判定问题意图（优先）与查询意图；输出标记、命中词根、审计信息；**不检索文件、不读取源码、不做内容推理**
- ❌ 禁止：自建黑名单、内容解读、数据源拉取、有效性判断、打分、改写生成
- 硬约束：白名单**仅 2 汉字词根**；词语边界匹配（jieba 精确 2 字 token 匹配优先，无 jieba 时退化为 ASCII 词边界子串匹配并在输出中说明降级），降低与系统技能提示词重叠冲突风险

### 通道① 意图硬路由（2026-08-20 用户指令落地 + GENERALIZE-GATE 判A 泛化「declare-gate-signal-channel」模式，优先于白名单）

- 信号**不在本文件维护**：运行时按 id 加载 `~/.agents/skills/dual-gates/data/trigger_signals.json` 的信号定义（match/match_mode/must_pull），唯一真源，禁双副本
- 通道表（顺序即优先级）：**安全 S-DANGER-CMD → is_danger ｜ 问题 S-PROBLEM-GATE → is_problem**
- 命中 → `declaration_result = is_<intent>`，`must_pull` 字段透传真源 must_pull 指令列表（如 problem_gate.json 判 A / danger_cmd_gate.json 判 A），机械执行不经裁量
- 设计意图：机械可判信号不停留在「软扫描+记得扳」层，前置到任务定性唯一入口硬路由，概率空间归零；问题类输入直接进问题闸、危险命令直接进事前闸，**都不需要用户来做决定**
- S-RETRO-WORDS 已有 retro-match 独立起手式 + F6 后查兜底，不重复设防，未入通道表（登记模式库待复盘裁定）；S-TEST-WORDS 测试通道 2026-08-20 用户裁定随超时闸取消一并摘除

### 定稿 2 字白名单词根库（不可随意新增 3 字及以上词条）

```
获取、查询、检索、查找、找到、读取、查看、调出、取出、
定位、提取、列出、展示、返回、列举、调取、评估、找出、挖掘、
调查、寻找
```

### 兜底词根（2026-08-23 用户裁定新增，独立于 2 字白名单）

```
找（1 字兜底词根，走 FALLBACK_ROOTS 独立匹配通道，不计入上方白名单、不受 2 字 assert 约束）
```

### 判定规则（固定顺序，不可调整）

1. 先跑通道①意图硬路由（安全→问题，信号真源 trigger_signals.json），命中 → `is_<intent>` + must_pull
2. 再对原始请求文本做词语边界匹配，匹配上述任意 2 字词根
3. 命中 → `declaration_result = is_query`，放行进入查询闸
4. 无任何命中 → 再走兜底词根通道（找），命中 → `is_query`（match_keyword 标注「找(兜底)」）
5. 仍无命中 → `declaration_result = not_query`，切推理/生成链路
6. 白名单与兜底词根之外默认全部为非查询任务；无黑名单

### 用法

```bash
python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py declare \
  --input '{"trace_id":"t1","session_id":"s1","raw_prompt":"获取月之暗面评估方案"}'
# 或 --raw "获取月之暗面评估方案" --session-id s1
```

### 出参契约

```json
{
  "trace_id": "全局唯一链路ID",
  "declaration_result": "is_danger | is_problem | is_query | not_query",
  "intent_label": "安全 / 问题 / 查询 / 非查询",
  "match_type": "signal:<信号id> | white_list | no_match",
  "match_keyword": "命中片段/词根，无命中为空字符串",
  "reason": "命中说明",
  "must_pull": "意图命中时携带：真源 must_pull 指令列表（数组）"
}
```

### 审计埋点（公共固定字段 trace_id, session_id, timestamp, raw_prompt_snippet）

| 事件 | 触发 | 附加字段 |
|---|---|---|
| `declaration_gate_start` | 启动 | - |
| `declaration_gate_<intent>_hit` | 命中信号通道（danger/problem） | signal_id、match_snippet |
| `declaration_gate_is_<intent>` | 判定意图（danger/problem） | match_type、intent_label |
| `declaration_gate_white_hit` | 命中词根（每个命中词一条） | match_keyword |
| `declaration_gate_no_match` | 未命中 | - |
| `declaration_gate_is_query` | 判定查询 | match_type、intent_label |
| `declaration_gate_not_query` | 判定非查询 | match_type、intent_label |

## 3 查询闸 Query Gate

- ✅ 职责：会话锚点检索、多记录时序筛选、来源路径标注、通路分发；输出原始数据+溯源元信息
- ❌ 禁止：废弃/有效性判定、内容解读、逻辑校验、打分、推理；**禁止无脑全量 grep 扫描文件**
- 触发时机：**仅当声明闸输出 is_query**（脚本契约强校验，否则退出码 4 VIOLATION）

### 执行流程

1. 检索当前会话锚点注册表（`~/.agents/logs/session_anchors.jsonl`），按 prompt 中文 token 与锚点 title/source_path 的机械交集做定向相关性匹配（无语义推理）
2. ✅ 找到锚点：
   - 多条/单条 history 记录 → **仅按 record_time 取最新一条** → 模板 A，强制携带 source_path
   - sourcecode 唯一 → 直接选定 → 模板 B（多条源码取相关性最高者，机械择优，不做内容判断）
3. ❌ 无锚点：prompt 含外部信号（http(s)://、外部、联网、官网、网页、网络）→ 模板 C 外部通路；否则 → 模板 D 内部源码通读通路

### 用法

```bash
# 承接声明闸输出（declaration_result 必须为 is_query）
python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py query \
  --input '{"trace_id":"t1","session_id":"s1","raw_prompt":"找出之前的评估规则","declaration_result":"is_query","match_keyword":"找出"}'

# 锚点登记（查询链路的数据来源）
python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py anchor \
  --session-id s1 --type history --title "评估规则v3" --path xxx/record.json --record-time 2026-08-18T10:00:00
# history 锚点缺 source_path 直接 VIOLATION（溯源强制）
```

### 出参四模板

- A `hit_history`：data_payload + **source_path（强制，缺失即不合规退出码2）** + record_time
- B `hit_sourcecode`：data_payload（源码不强制路径标注）
- C `no_anchor_external`：forward=external_query_channel
- D `no_anchor_internal`：forward=read_raw_source

### 审计埋点（公共固定字段 trace_id, session_id, timestamp）

| 事件 | 触发 | 附加字段 |
|---|---|---|
| `query_gate_start` | 启动 | - |
| `query_gate_anchor_found` | 检索到锚点 | anchor_count |
| `query_gate_hit_history` | 筛出最新历史记录 | source_path、record_time |
| `query_gate_hit_source` | 命中唯一源码 | - |
| `query_gate_anchor_notfound` | 未找到锚点 | - |
| `query_gate_forward_external` | 分发外部通路 | - |
| `query_gate_forward_internal_source` | 分发内部源码通读 | - |

审计落盘：`~/.agents/logs/dual_gates_audit.jsonl`（每事件一行 JSON）。

## 4 关键规约 & 边界铁则（强制遵守）

1. 词根管控：白名单永久优先 **2 汉字词根**；新增词条必须评审，禁止直接加入 3 字及以上短语
2. 职责隔离铁律：废弃资产、有效性、内容解读、打分研判全部属于下游推理层；查询闸只输出原始数据与溯源路径
3. 检索约束：严禁脱离会话锚点执行全盘目录 grep，仅允许基于会话锚点定向溯源
4. 时序规则：多条历史记录仅按时间戳取最新一条，不做内容相似度择优
5. 溯源强制：历史记录类结果必须携带 source_path，缺失视为输出不合规；源码条目不强制路径标注
6. 产出即登记（2026-08-18 用户裁定采纳）：数据源类产出（评估基准/方案/源码/历史记录）收尾必须用 `anchor` 子命令登记锚点（路径+时间落注册表）；漏登记属"该做的没做"，事后由 `gate-switch/specs/anchor_registry_audit.json` 扳闸核验（`--set artifact=<产物路径>`，产物在/锚点缺即判 B 补登）——普通对话产出、临时中间产物豁免，防注册表膨胀成噪音源。登记幂等（2026-08-18 用户裁定）：以产物内容 sha1 判定，幂等键=(session_id, source_path)——同键同哈希幂等空操作不写盘（idempotent_noop），同键不同哈希原位更新 record_time/content_hash 不追加新行（updated），仅新键才 append（registered）；纯 data_ref 无路径锚点无文件身份，不参与幂等。
   自动触发（可选，2026-08-18 用户裁定路线A：文件写入完成时）：如平台支持文件写入钩子，可挂监听 fs 写入事件、写入完成即自动调 anchor 登记（扩展名白名单定 history/sourcecode 类型，排除 logs/tmp/node_modules 等噪音目录）；无钩子环境下靠铁则自觉+anchor_registry_audit 事后闸兜底；手工 anchor 登记与自动登记共用幂等同键，重复触发天然去重

## 5 场景样例（验收基线）

✅ `获取月之暗面评估方案` → 命中【获取】→ 进查询闸
✅ `找出之前的评估规则` → 命中【找出】→ 进查询闸
✅ `列出所有评估维度` → 命中【列出】→ 进查询闸
✅ `挖掘历史评估基准` → 命中【挖掘】→ 进查询闸
✅ `评估基准文档原文` → 命中【评估】→ 进查询闸
❌ `使用基准给代码打分` → 无命中 → 直接进推理链路，不走查询闸
