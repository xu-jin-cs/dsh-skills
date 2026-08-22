#!/usr/bin/env python3
"""skill_value_gate_check.py — GENERATE 准入端价值闸（块H 2026-08-22 判A；块K 语义重复→需求计数→三次转化专项技能 2026-08-22 判A）。

块文件：~/.agents/logs/reform_blocks/skill_value_gate_20260822.md（块H）
        ~/.agents/logs/reform_blocks/dedup_demand_count_20260822.md（块K，含三步验证修订增补）

用户终裁硬约束（违反即设计错误）：
  ① 废止一切"率"口径——台账只计数，不设计算比率/百分比的代码路径（标定容差 ≤5% 是设计参数不是运行指标）。
  ② 合并≠排除、加载即 100% 使用、价值目标函数 = 加载面归属正确性。
  ③ 块K：语义重复 = 需求信号不是废物——重复需求计数，第三次被需要转化专项技能（反过早抽象的落地化）。

判定模型（全机械，零语义裁量），价值维度卡 → R1-R6 按序判（先先生效）：
  R1 内容为空                     → B(content_empty)
  R2 语义重复（包含度口径，块K 修订）→ DEDUP_COUNT:<skill_id>（候选不入库防膨胀不变，但记需求）
  R3 severity=low                 → B(severity_low)
  R4 加工度失败（四段式标记全缺 且 无编号步骤 且 问题段<30字）→ B(raw_dump)
  R5 针对性标记（具体文件名/一次性日期/本地路径/专有名词）→ MERGE:<role>(targeted_scope)
  R6 其余                         → A(independent)

R2 检测器（块K 前置修复，修订增补第 2 条）：
  旧口径 4-gram Jaccard |交|/|并|≥0.6 对长度不对称失效（母体实测紧贴改写 near_dup=False 放行）。
  新口径：包含度 = |候选4gram ∩ 基准条目4gram| / |基准条目4gram| ≥ 200‰（0.20）。
  标定证据（2026-08-22，NP 同口径误并≤5%）：真同义对=13 条替换/吸收归档对（全部 1000‰）+
  母体测例改写（'依赖外部服务的质量闸门'紧贴换措辞版 285‰）；真无关对=现役跨角色随机 40 对
  （max 25‰ / p95 24‰ / median 0‰）。t=200‰ 时同义命中 13/13+测例命中、误并 0/40（≤5% 达标），
  上下双向间隔 ≥8 倍。

DEDUP_COUNT 侧效应（write_ledger 时）：
  ⑴ demand_ledger.jsonl 记一笔 {matched_skill_id, candidate_snapshot, ts}
  ⑵ registry-index.json 该条目 demand_count+1（--defer-registry 时改由调用方负责：
     打印 DEMAND_TARGET:<sid>，dispatcher 在内存镜像 +1，防主流程尾声覆写闸的增量）
  ⑶ demand_count 达 DEMAND_SPECIALIZE_AT(=2，即第三次被需要：原始 1 次+重复 2 次)
     → specialize_hook：合并各次候选快照进该技能 SKILL.md（DEMAND-SPECIALIZE 标记块，
     幂等重写）、entry 打 specialized/skill_level=specialty/parent_skill（=转化前自身
     skill_id，即原领域技能身份；带 parent_skill 的专项不参与'专项攒3晋升领域'回顾——防循环，
     trigger_match_audit.py ④ 已同步豁免）、decision 台账留痕、demand_count 重置待下轮累积。

退出码：0=A / 6=MERGE:<role> / 7=DEDUP_COUNT:<skill_id> / 2=B / 3=CLARIFY / 4=VIOLATION(台账或registry写失败)
台账（计数制）：B→exclusion_registry.jsonl；A/MERGE/SPECIALIZE→value_gate_decisions.jsonl；
  DEDUP_COUNT→demand_ledger.jsonl。--no-ledger 干跑跳过一切写（含 registry）。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REGISTRY_DIR = Path.home() / ".agents" / "retro-skills-registry"
REGISTRY_PATH = REGISTRY_DIR / "registry-index.json"
SKILLS_DIR = REGISTRY_DIR / "skills"
EXCLUSION_LEDGER = REGISTRY_DIR / "runtime" / "exclusion_registry.jsonl"
DECISION_LEDGER = REGISTRY_DIR / "runtime" / "value_gate_decisions.jsonl"
DEMAND_LEDGER = REGISTRY_DIR / "runtime" / "demand_ledger.jsonl"

# 块K 标定值（见 docstring 标定证据段）：包含度阈值 200‰，误并 0/40 ≤5%，同义 13/13+母体测例命中
NEAR_DUP_CONTAINMENT_MILLI = 200
DEMAND_SPECIALIZE_AT = 2  # 第三次被需要（原始 1 次 + 重复 2 次）转化专项——块K 用户原话
MIN_PROBLEM_LEN = 30

EXIT_A, EXIT_B, EXIT_CLARIFY, EXIT_VIOLATION, EXIT_MERGE, EXIT_DEDUP = 0, 2, 3, 4, 6, 7


# ── 推断原语（与 dispatcher_generate.py 同口径的轻量镜像，单一真源注释留锚）──
def _infer_severity(content: str) -> str:
    """镜像 dispatcher_generate.py:43-54。"""
    c = content.lower()
    if any(k in c for k in ["严重", "critical", "崩溃", "冻结", "数据丢失", "不可恢复", "0分", "开除"]):
        return "critical"
    if any(k in c for k in ["重要", "high", "安全", "关键", "门禁", "阻断", "跳过校验", "静默跳过", "静默失败", "覆盖用户"]):
        return "high"
    if any(k in c for k in ["优化", "改进", "建议", "low", "次要", "美化"]):
        return "low"
    return "medium"


def _infer_bug_type(content: str) -> list:
    """镜像 dispatcher_generate.py:57-68（process 类为调查报告实证富集特征，7 倍富集于命中组）。"""
    c = content.lower()
    types = []
    if any(k in c for k in ["数据", "脏数据", "覆盖", "删除", "db", "数据库", "sql", "写入", "注册", "哈希"]):
        types.append("data")
    if any(k in c for k in ["设计", "architecture", "架构", "静默", "审计", "逐层", "扩面", "模式", "规范"]):
        types.append("design")
    if any(k in c for k in ["配置", "config", "settings", "规则", "yml", "yaml", "registry"]):
        types.append("config")
    if any(k in c for k in ["流程", "门禁", "闸", "签发", "验收", "派发", "调度", "编排", "闭环"]):
        types.append("process")
    if any(k in c for k in ["代码", "实现", "修复", "bug", "报错", "异常", "except", "pass", "return", "函数", "参数"]):
        types.append("code")
    return types if types else ["code"]


def _infer_role(content: str) -> str:
    """镜像 dispatcher_generate.py:71-79。"""
    c = content.lower()
    if any(k in c for k in ["前端", "fe", "ui", "组件", "html", "css", "样式", "渲染"]):
        return "fe"
    if any(k in c for k in ["pm", "流程", "复盘", "调度", "指派", "门禁"]):
        return "pm"
    if any(k in c for k in ["后端", "be", "api", "引擎", "engine", "数据库", "接口", "服务"]):
        return "be"
    return "be"


# 针对性标记（镜像 dispatcher_generate.py:653-658 _TARGETED_PATTERNS/_TARGETED_NOUNS）
_TARGETED_PATTERNS = [
    re.compile(r"[\w./~-]+\.(?:py|md|json|ya?ml|pptx?|tsx?|jsx?|css|sql|sh|txt|csv)(?::\d+)?"),
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"(?:/Users/|/home/|~/Desktop|桌面|[A-Z]:\\)", re.IGNORECASE),
]
_TARGETED_NOUNS = ("百度", "baidu", "google", "谷歌", "appium", "kafka", "都江堰", "舌脉", "红妆", "unicom", "站酷", "花瓣")


def _is_targeted(content: str) -> bool:
    c = content.lower()
    return any(p.search(content) for p in _TARGETED_PATTERNS) or any(n in c for n in _TARGETED_NOUNS)


def _craft_card(content: str) -> dict:
    """加工度卡（机械）：四段式标记完备度 / 编号步骤 / 问题段长度。
    四段式标记与 dispatcher_generate.parse_sections(:526-544) 同口径。"""
    marks = {}
    for m in ("触发信号", "问题模式", "根因类别", "处置规则"):
        marks[m] = bool(re.search(m + r"[：:]", content))
    four_section_complete = all(marks.values())
    numbered_steps = len([s for s in content.splitlines() if re.match(r"^\s*\d+[.、]", s)])
    m = re.search(r"问题模式[：:](.+?)(?=触发信号|根因类别|处置规则|$)", content, re.S)
    problem = (m.group(1).strip() if m else content.strip())
    raw_dump = (not four_section_complete) and numbered_steps == 0 and len(problem) < MIN_PROBLEM_LEN
    return {
        "four_section_marks": marks,
        "four_section_complete": four_section_complete,
        "numbered_steps": numbered_steps,
        "problem_len": len(problem),
        "raw_dump": raw_dump,
    }


def _grams(text: str) -> set:
    t = re.sub(r"[^一-鿿a-zA-Z0-9]", "", (text or "").lower())
    return {t[i:i + 4] for i in range(len(t) - 3)} if len(t) >= 4 else ({t} if t else set())


def _near_duplicate(content: str, registry_path: Path) -> tuple:
    """块K 前置修复：包含度口径 |候选∩基准| / |基准条目4gram|（基准=现役条目 description）。
    旧 Jaccard |交|/|并| 对长度不对称失效（长候选 vs 短基准，并集稀释交集）——母体实测
    紧贴改写放行为证。返回 (is_dup, max_containment_milli, peer_id)。"""
    g = _grams(content)
    if not g:
        return False, 0, None
    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return False, 0, None  # registry 不可读不算重复（CLARIFY 由调用方判）
    best_milli, best_id = 0, None
    for e in entries:
        if e.get("status") == "archived":
            continue
        ge = _grams(e.get("description") or "")
        if not ge:
            continue
        c_milli = 1000 * len(g & ge) // len(ge)  # 包含度：基准条目为分母（长度不对称修复核心）
        if c_milli > best_milli:
            best_milli, best_id = c_milli, e.get("skill_id")
    return best_milli >= NEAR_DUP_CONTAINMENT_MILLI, best_milli, best_id


def build_value_card(content: str, role: str, project: str, registry_path: Path) -> dict:
    """价值维度卡（块H 必填项：bug_type/severity/加工度/归属角色判定）。"""
    bug_type = _infer_bug_type(content)
    severity = _infer_severity(content)
    craft = _craft_card(content)
    targeted = _is_targeted(content)
    is_dup, dup_milli, dup_peer = _near_duplicate(content, registry_path)
    inferred_role = role if role not in ("", "unknown") else _infer_role(content)
    return {
        "bug_type": bug_type,
        "severity": severity,
        "craft": craft,
        "targeted": targeted,
        "near_duplicate": {"is_dup": is_dup, "containment_milli": dup_milli, "peer": dup_peer},
        "inferred_role": inferred_role,
        "project": project,
        "content_len": len(content),
    }


def judge(card: dict) -> tuple:
    """硬规则链 R1-R6 → (verdict, reason)。verdict ∈ A / MERGE:<role> / DEDUP_COUNT:<sid> / B。"""
    if card["content_len"] == 0:
        return "B", "content_empty"
    nd = card["near_duplicate"]
    if nd["is_dup"]:
        # 块K：语义重复=需求信号，不再判 B 丢弃证据，改判 DEDUP_COUNT（候选仍不入库防膨胀）
        return f"DEDUP_COUNT:{nd['peer']}", f"semantic_duplicate(containment_milli={nd['containment_milli']},matched={nd['peer']})"
    if card["severity"] == "low":
        return "B", "severity_low"
    if card["craft"]["raw_dump"]:
        return "B", "raw_dump(四段式标记缺失+无编号步骤+问题段<30字)"
    if card["targeted"]:
        return f"MERGE:{card['inferred_role']}", "targeted_scope(具体文件/日期/本地路径/专有名词→合并入角色加载面)"
    return "A", "independent"


def _append_ledger(path: Path, record: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"⚠️⚠️ 台账写失败 {path}: {e}", file=sys.stderr)
        return False


def log_decision(card: dict, verdict: str, reason: str, write_ledger: bool = True,
                 exclusion_ledger: Path = EXCLUSION_LEDGER, decision_ledger: Path = DECISION_LEDGER) -> bool:
    """计数台账落盘：B→排除台账；A/MERGE→归属判定台账。DEDUP_COUNT 走 demand_remember 专账。"""
    rec = {
        "ts": datetime.now().isoformat(),
        "gate": "skill_value_gate",
        "verdict": verdict,
        "reason": reason,
        "feature_snapshot": card,
    }
    if not write_ledger:
        return True
    if verdict == "B":
        return _append_ledger(exclusion_ledger, rec)
    if verdict.startswith("DEDUP_COUNT"):
        return True  # demand 台账由 demand_remember 落（含完整候选快照）
    return _append_ledger(decision_ledger, rec)


# ── 块K：需求计数 + 专项转化 ────────────────────────────────────────────────

def _parse_case(content: str) -> dict:
    """候选 case 结构化快照（块K 口径补充①：每一笔必须存足——触发层面/场景/内容全文）。
    触发层面=触发信号段；场景=问题模式段（回退适用场景段）；全文不截断。"""
    def grab(marker, stops):
        m = re.search(marker + r"[：:](.+?)(?=" + stops + "|$)", content, re.S)
        return m.group(1).strip(" 。；\n") if m else ""
    trigger = grab("触发信号", "问题模式|根因类别|处置规则")
    scenario = grab("问题模式", "触发信号|根因类别|处置规则") or grab("适用场景", "触发信号|根因类别|处置规则")
    return {"trigger_layer": trigger, "scenario": scenario, "content_full": content}


def demand_remember(card: dict, content: str, matched_skill_id: str, entry: dict | None,
                    demand_ledger: Path = DEMAND_LEDGER) -> int:
    """DEDUP_COUNT 侧效应⑴+⑵：demand_ledger 记一笔（case 快照=触发层面/场景/内容全文+价值卡）；
    entry demand_count+1（就地改 dict，entry=None 时仅落账不计数——defer 场景）。
    返回计数后的新 demand_count（entry 为 None 时返回 -1 表示未计数）。"""
    case = _parse_case(content)
    rec = {
        "ts": datetime.now().isoformat(),
        "event": "DEMAND_COUNT",
        "gate": "skill_value_gate",
        "matched_skill_id": matched_skill_id,
        "candidate_snapshot": {
            "trigger_layer": case["trigger_layer"],
            "scenario": case["scenario"],
            "content_full": case["content_full"],
            "value_card": card,
        },
    }
    _append_ledger(demand_ledger, rec)
    if entry is None:
        return -1
    entry["demand_count"] = (entry.get("demand_count") or 0) + 1
    return entry["demand_count"]


def _load_demand_snapshots(matched_skill_id: str, demand_ledger: Path) -> list:
    """取该技能全部历史需求快照（追加式台账全量即历史，转化块幂等重写故无需窗口）。
    兼容两代格式：新格式 content_full/trigger_layer/scenario；旧格式 content_excerpt。"""
    out = []
    if not demand_ledger.exists():
        return out
    for line in open(demand_ledger, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("matched_skill_id") == matched_skill_id:
            snap = rec.get("candidate_snapshot", {})
            full = snap.get("content_full") or snap.get("content_excerpt", "")
            out.append({"ts": rec.get("ts", ""), "full": full,
                        "trigger_layer": snap.get("trigger_layer", ""),
                        "scenario": snap.get("scenario", "")})
    return out


# ── 块K 口径补充②③：三案结构化提炼的机械初切原语 ──
def _norm_lines(text: str) -> list:
    """行级规范化：去空白/标点差异，滤 <6 字噪声行，保序去重。"""
    out, seen = [], set()
    for ln in (text or "").splitlines():
        n = re.sub(r"\s+", "", ln).strip("，。；、：:—…·*-#> ")
        if len(n) < 6 or n in seen:
            continue
        seen.add(n)
        out.append((ln.strip(), n))  # (原文, 规范化)
    return out


def _three_case_diff(case_texts: list) -> dict:
    """共有行/差异行机械初切（块K 口径补充③）：
    共同点=三案规范化行交集（编号步骤行优先，保序）→ 主线步骤候选；
    差异=仅一案独有行 → 参数/坑位/分支候选（按案分组）。"""
    norm = [_norm_lines(t) for t in case_texts]
    sets = [{n for _, n in nl} for nl in norm]
    common_norm = set.intersection(*sets) if sets else set()
    common, diffs = [], []
    for i, nl in enumerate(norm):
        diff_i = [orig for orig, n in nl if n not in common_norm and all(n not in sets[j] for j in range(len(sets)) if j != i)]
        diffs.append(diff_i)
    for orig, n in norm[0] if norm else []:
        if n in common_norm:
            common.append(orig)
    # 编号步骤行提前（主线步骤骨架优先用可执行步骤）
    common.sort(key=lambda l: (0 if re.match(r"^\s*\d+[.、]", l) else 1))
    return {"common": common, "diffs": diffs}


SPEC_BLOCK_START = "<!-- DEMAND-SPECIALIZE:START -->"
SPEC_BLOCK_END = "<!-- DEMAND-SPECIALIZE:END -->"


def _specialty_card(entry: dict, case_texts: list, snapshots: list, ts: str) -> str:
    """专项技能卡骨架（块K 口径补充②：窄而深，对齐 slots-protocol 专项定义=场景族+步骤+参数+坑位）。
    机械初切生成齐全骨架与字段；语义成文标 TODO，由 agent 复盘着陆时补完（机械可扫 TODO 计数）。"""
    sid = entry.get("skill_id", "")
    diff = _three_case_diff(case_texts)
    scenarios = [s["scenario"] for s in snapshots if s.get("scenario")]
    triggers = [s["trigger_layer"] for s in snapshots if s.get("trigger_layer")]
    lines = [
        SPEC_BLOCK_START, "",
        f"## 🎯 专项技能卡（需求计数转化 · 块K · {ts}）",
        "",
        f"> specialized_from: `{sid}`（原领域技能，parent_skill 挂载）｜需求证据：三次被需要（原始 1 次 + 重复 {len(snapshots)} 次）",
        "> 骨架与字段机械生成齐全（三案共有行/差异行 diff 初切）；`TODO` 处由 agent 复盘着陆时语义补完，补完前不得视为定稿。",
        "",
        "### 场景族",
        "",
        f"- 主场景（机械取首案场景段）: {scenarios[0] if scenarios else 'TODO: 从三案问题模式段语义归纳主场景'}",
        f"- 场景变体（各案场景段罗列，TODO 语义归并）: {' ｜ '.join(s.replace(chr(10), ' ')[:80] for s in scenarios) if len(scenarios) > 1 else 'TODO: 差异案场景段不足，待下轮累积'}",
        f"- 触发层面（各案触发信号段）: {' ｜ '.join(t.replace(chr(10), ' ')[:60] for t in triggers) if triggers else 'TODO: 补触发层面'}",
        "",
        "### 主线步骤（三案共同点机械初切，TODO 复核成文）",
        "",
    ]
    if diff["common"]:
        for i, c in enumerate(diff["common"][:8], 1):
            step_text = re.sub(r"^\s*\d+[.、]\s*", "", c)[:120]
            lines.append(f"{i}. {step_text}")
    else:
        lines.append("1. TODO: 三案无规范化共有行，共同点需 agent 语义提炼（差异过大的信号，复核是否真同族）")
    lines += ["", "### 参数与分支（三案差异机械初切，按案分组，TODO 语义命名参数位）", ""]
    for i, d in enumerate(diff["diffs"]):
        case_label = "原技能本体" if i == 0 else f"需求案 #{i}"
        if d:
            for item in d[:6]:
                lines.append(f"- [{case_label} 特有] {item[:120]}")
        else:
            lines.append(f"- [{case_label}] 无独有差异行")
    lines += [
        "",
        "### 坑位",
        "",
        "- TODO: agent 复盘着陆时从上方差异行提炼坑位（机械初切候选已列，禁止留空骨架定稿）",
        "",
        "### 需求证据快照（原始留痕，计数制）",
        "",
    ]
    for i, s in enumerate(snapshots, 1):
        lines.append(f"#### 需求案 #{i}（{s['ts'][:19]}）")
        lines.append("")
        excerpt = s["full"].replace("\n", " ").strip()
        lines.append(f"> {excerpt[:400]}")
        lines.append("")
    lines += [SPEC_BLOCK_END]
    return "\n".join(lines)


# ── 块K 修订增补2（2026-08-22 用户终裁）：晋升=替代非并存 ──
# ETL 引擎无 update（CONTRACT.md:14-15）→ 走删除+新增：同一事务边界 deletes(旧领域)+writes(新专项)，
# 即 CONTRACT.md 第三节钦定晋升改写流程（archive_skill 墓碑+supersedes 链+引擎 batch+BM25 单次重建），
# 禁止手工编辑源文件修平台状态（CONTRACT.md:36）。数据源剔除链路实证落点（用户口径
# "_purge_skill_from_datasources" 的体系实名）：archive_skill（dispatcher_generate.py:1011）
# + _prune_role_links + retro_etl batch delete（LanceDB/legacy SQL/BM25）+ inject 全量派生。

ARCHIVE_DIR = REGISTRY_DIR / "archive"
ROLE_LINKS_PATH = REGISTRY_DIR / "role-retro-links.json"


def allocate_specialty_id(old_entry: dict) -> tuple:
    """专项 skill_id 派生：<旧领域skill_id>-sp<轮次>；轮次计数挂墓碑（_sp_cycle），
    同一领域技能多轮转化 id 不撞车。返回 (new_sid, cycle)。"""
    old_sid = old_entry.get("skill_id", "")
    cycle = (old_entry.get("_sp_cycle") or 0) + 1
    return f"{old_sid}-sp{cycle}", cycle


def build_specialty_entry(old_entry: dict, new_sid: str, ts: str, description: str) -> dict:
    """新专项 entry：继承旧领域条目的角色/类型/严重度/来源，打 specialized/parent_skill/supersedes。"""
    old_sid = old_entry.get("skill_id", "")
    e = {k: old_entry.get(k) for k in (
        "affected_role", "bug_type", "severity", "generality", "source_project",
        "original_author_role", "placement", "trigger_phrases", "trigger_keywords")}
    e.update({
        "skill_id": new_sid,
        "skill_dir": new_sid,
        "created": ts[:10],
        "description": description,
        "skill_level": "specialty",
        "specialized": True,
        "specialized_at": ts,
        "parent_skill": old_sid,          # 防循环标记不变：带 parent_skill 的专项不参与晋升回顾
        "supersedes": [old_sid],          # 修订增补2③：新专项 entry 带 supersedes 指回旧领域
        "demand_count": 0,                # 计数重置待下轮累积
        "match_count": 0,
        "last_matched": None,
        "frequency": 0,
    })
    return {k: v for k, v in e.items() if v is not None}


def _move_to_archive(skills_dir: Path, archive_dir: Path, skill_dir_name: str):
    """旧技能目录移入 archive/（与 dispatcher_generate.archive_skill 同语义，:1028-1036）。"""
    src = skills_dir / skill_dir_name
    if src.exists():
        archive_dir.mkdir(parents=True, exist_ok=True)
        dst = archive_dir / skill_dir_name
        if dst.exists():
            import shutil
            shutil.rmtree(dst)
        src.rename(dst)


def _role_links_replace(role_links_path: Path, old_sid: str, new_entry: dict, ts: str):
    """role-retro-links 同步：剔除旧领域绑定 + 绑定新专项（roles 信封 schema，与 dispatcher 同构）。"""
    try:
        links = json.loads(role_links_path.read_text(encoding="utf-8")) if role_links_path.exists() \
            else {"schema_version": "1.0.0", "roles": {}}
        roles = links.setdefault("roles", {})
        for r, es in list(roles.items()):
            if isinstance(es, list):
                roles[r] = [x for x in es if x.get("skill_id") != old_sid]
        ar = new_entry.get("affected_role") or ["be"]
        role = ar[0] if isinstance(ar, list) else ar
        roles.setdefault(role, []).append({
            "skill_id": new_entry["skill_id"],
            "chunkId": None,
            "description": (new_entry.get("description") or "")[:200],
            "trigger_phrases": new_entry.get("trigger_phrases") or [],
            "bug_type": (new_entry.get("bug_type") or ["code"])[0],
            "severity": new_entry.get("severity", "medium"),
            "source_project": new_entry.get("source_project", ""),
            "match_count": 0,
            "created_at": ts,
        })
        links["last_updated"] = ts
        role_links_path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"  ⚠️ role-retro-links 替换异常: {e}", file=sys.stderr)
        return False


def specialize_replace(old_entry: dict, registry: dict, skills_dir: Path = SKILLS_DIR,
                       archive_dir: Path = ARCHIVE_DIR, demand_ledger: Path = DEMAND_LEDGER,
                       decision_ledger: Path = DECISION_LEDGER,
                       role_links_path: Path | None = ROLE_LINKS_PATH) -> tuple:
    """块K ⑶ 专项转化（修订增补2 替代版）：晋升=替代非并存。
    动作链（registry dict 就地改，持久化与引擎事务由调用方负责）：
      1. 三案结构化提炼 → 专项技能卡（_specialty_card，场景族/步骤/参数/坑位骨架机械齐全）
      2. 新专项源文件：skills/<new_sid>/SKILL.md（真源追加原则，CONTRACT.md 2.1）
      3. 旧领域墓碑：status=archived + superseded_by=new_sid + _sp_cycle 轮次留痕
      4. 旧目录移 archive/；registry append 新专项 entry（supersedes:[旧领域]）
      5. role-retro-links 剔除旧绑定+绑定新专项
      6. decision 台账留痕 SPECIALIZE（计数制）
    返回 (new_entry, new_skill_md_text, ledger_ok)；引擎 batch deletes+writes 由调用方同事务执行。"""
    sid = old_entry.get("skill_id", "")
    snapshots = _load_demand_snapshots(sid, demand_ledger)
    ts = datetime.now().isoformat()
    new_sid, cycle = allocate_specialty_id(old_entry)
    # 案0=原技能本体（剥 frontmatter 防字段名行污染差异池）
    old_md_path = skills_dir / old_entry.get("skill_dir", sid) / "SKILL.md"
    base_text = ""
    if old_md_path.exists():
        base_text = old_md_path.read_text(encoding="utf-8")
        base_text = re.sub(r"\A---\n.*?\n---\n", "", base_text, flags=re.S)
    if not base_text.strip():
        base_text = old_entry.get("description", "")
    case_texts = [base_text] + [s["full"] for s in snapshots]
    card = _specialty_card(old_entry, case_texts, snapshots, ts)
    desc_seed = snapshots[0]["scenario"] if snapshots and snapshots[0].get("scenario") else (old_entry.get("description") or "")
    new_desc = f"专项技能（三次被需要·块K转化，parent={sid[:40]}）: {desc_seed[:100]}"
    new_md_text = (
        f"---\nname: {new_sid}\ndescription: \"{new_desc.replace(chr(34), chr(39))}\"\n"
        f"type: retro-derived-specialized\n---\n\n"
        f"# 专项技能: {desc_seed[:80]}\n\n> 由 {sid} 经需求计数转化（三次被需要），原领域技能已归档（晋升=替代）。\n\n{card}\n"
    )
    new_dir = skills_dir / new_sid
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "SKILL.md").write_text(new_md_text, encoding="utf-8")
    # 3+4. 墓碑 + 归档 + append 新 entry
    new_entry = build_specialty_entry(old_entry, new_sid, ts, new_desc)
    triggered_at_count = old_entry.get("demand_count", 0)
    old_entry["status"] = "archived"
    old_entry["archived_at"] = ts
    old_entry["archive_reason"] = f"被 {new_sid} 专项转化替代（块K 修订增补2：晋升=替代非并存）"
    old_entry["superseded_by"] = new_sid
    old_entry["_sp_cycle"] = cycle
    _move_to_archive(skills_dir, archive_dir, old_entry.get("skill_dir", sid))
    registry.setdefault("entries", []).append(new_entry)
    # 5. role-retro-links 同步
    if role_links_path is not None:
        _role_links_replace(role_links_path, sid, new_entry, ts)
    # 6. 台账
    ok = _append_ledger(decision_ledger, {
        "ts": ts,
        "gate": "skill_value_gate",
        "verdict": "SPECIALIZE",
        "reason": f"demand_count 达 {triggered_at_count}（≥{DEMAND_SPECIALIZE_AT}，第三次被需要）→ 替代式专项转化",
        "matched_skill_id": sid,
        "new_specialty_id": new_sid,
        "parent_skill": sid,
        "supersedes": [sid],
        "cases_total": len(case_texts),
        "snapshots_merged": len(snapshots),
    })
    print(f"  🎯 SPECIALIZE(替代): {sid[:50]} → {new_sid[:60]}（旧领域已墓碑+移档，三案 {len(case_texts)} 案提炼）")
    return new_entry, new_md_text, ok


def specialize_hook(*args, **kwargs):
    """已废止别名防误调：修订增补2 起转化为替代式，统一走 specialize_replace。"""
    raise RuntimeError("specialize_hook 已废止（块K 修订增补2：晋升=替代非并存），改用 specialize_replace")


# ── 块K 口径补充3（2026-08-22 用户终裁）：晋升后的吸收期语义 ──
# 专项已存在的领域再命中同语义候选：①不再 demand_count 计数 ②机械提取候选有用 case 内容
# （与专项卡 diff 出的新坑位/参数/分支行）追加到该专项技能卡 ③候选本体直接丢弃（不入库不计数）
# ④吸收动作记台账（decision 台账 verdict=ABSORB：候选快照+抽取了哪些内容行）。
# 判定路径：R2 命中后看 matched 条目 specialized——是→吸收期（本函数）；否→计数期（demand_remember）。

ABSORB_BLOCK_START = "<!-- DEMAND-ABSORB:START -->"
ABSORB_BLOCK_END = "<!-- DEMAND-ABSORB:END -->"


def _absorb_extract_lines(content: str, skill_md_text: str) -> list:
    """机械初切：候选规范化行中未出现在专项卡（全文规范化）的行 = 新坑位/参数/分支候选。"""
    hay = re.sub(r"\s+", "", skill_md_text or "")
    return [orig for orig, n in _norm_lines(content) if n not in hay][:10]


def _load_absorb_records(matched_skill_id: str, decision_ledger: Path) -> list:
    out = []
    if not decision_ledger.exists():
        return out
    for line in open(decision_ledger, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("verdict") == "ABSORB" and rec.get("matched_skill_id") == matched_skill_id:
            out.append(rec)
    return out


def absorb_into_specialty(entry: dict, content: str, card: dict,
                          skills_dir: Path = SKILLS_DIR,
                          decision_ledger: Path = DECISION_LEDGER) -> tuple:
    """吸收期动作：抽取候选新内容行 → 台账留痕 → 专项卡 DEMAND-ABSORB 块幂等重写（由台账全量派生）。
    registry 零触碰（不计数、不改字段）。返回 (new_line_count, ledger_ok)。"""
    sid = entry.get("skill_id", "")
    ts = datetime.now().isoformat()
    md = skills_dir / entry.get("skill_dir", sid) / "SKILL.md"
    text = md.read_text(encoding="utf-8") if md.exists() else ""
    new_lines = _absorb_extract_lines(content, text)
    case = _parse_case(content)
    # ④ 台账先行（台账不断供硬约束：写失败即 VIOLATION 熔断，不动卡片）
    ok = _append_ledger(decision_ledger, {
        "ts": ts,
        "gate": "skill_value_gate",
        "verdict": "ABSORB",
        "reason": "吸收期：专项已存在，候选丢弃不入库不计数，有用内容行追加专项卡（块K 口径补充3）",
        "matched_skill_id": sid,
        "extracted_lines": new_lines,
        "extracted_count": len(new_lines),
        "candidate_snapshot": {"trigger_layer": case["trigger_layer"], "scenario": case["scenario"],
                               "content_full": case["content_full"], "value_card": card},
    })
    if not ok:
        return 0, False
    # ② 卡片追加（台账全量派生，幂等）
    if md.exists():
        records = _load_absorb_records(sid, decision_ledger)
        lines = [ABSORB_BLOCK_START, "",
                 f"## 📥 吸收期追加（块K 口径补充3 · 由 decision 台账 ABSORB 记录全量派生，勿手改）", ""]
        for i, rec in enumerate(records, 1):
            lines.append(f"### 吸收 #{i}（{rec.get('ts', '')[:19]}）· 新增内容行 {rec.get('extracted_count', 0)} 条")
            lines.append("")
            for ln in rec.get("extracted_lines", []):
                lines.append(f"- {ln[:160]}")
            if not rec.get("extracted_lines"):
                lines.append("- （本案无新增内容行，全部已在卡内）")
            lines.append("")
        lines.append(ABSORB_BLOCK_END)
        block = "\n".join(lines)
        if ABSORB_BLOCK_START in text and ABSORB_BLOCK_END in text:
            pre = text.split(ABSORB_BLOCK_START)[0].rstrip() + "\n"
            post = text.split(ABSORB_BLOCK_END, 1)[1]
            text = pre + block + post
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
        md.write_text(text, encoding="utf-8")
    else:
        print(f"  ⚠️ 吸收期：专项 SKILL.md 不存在（{md}），仅台账留痕", file=sys.stderr)
    print(f"  📥 ABSORB: {sid[:60]} 吸收候选新内容行 {len(new_lines)} 条（候选丢弃，不计数）")
    return len(new_lines), True



def main() -> int:
    ap = argparse.ArgumentParser(description="skill_value_gate 准入闸（A=独立成技 / MERGE=合并入角色加载面 / DEDUP_COUNT=需求计数 / B=拒绝）")
    ap.add_argument("--content", default=None)
    ap.add_argument("--content-file", default=None)
    ap.add_argument("--role", default="")
    ap.add_argument("--project", default="")
    ap.add_argument("--registry", default=str(REGISTRY_PATH))
    ap.add_argument("--demand-ledger", default=str(DEMAND_LEDGER))
    ap.add_argument("--decision-ledger", default=str(DECISION_LEDGER))
    ap.add_argument("--exclusion-ledger", default=str(EXCLUSION_LEDGER))
    ap.add_argument("--skills-dir", default=str(SKILLS_DIR))
    ap.add_argument("--archive-dir", default=str(ARCHIVE_DIR))
    ap.add_argument("--role-links", default=str(ROLE_LINKS_PATH))
    ap.add_argument("--defer-registry", action="store_true",
                    help="registry 计数/转化字段改由调用方负责（dispatcher 内存镜像场景，防尾声覆写）；打印 DEMAND_TARGET")
    ap.add_argument("--no-ledger", action="store_true", help="干跑跳过一切写（台账+registry）")
    ap.add_argument("--no-engine", action="store_true", help="跳过引擎晋升事务（测试/离线演练用；生产禁带）")
    ap.add_argument("--json", action="store_true", help="输出完整价值卡 JSON")
    args = ap.parse_args()

    if args.content_file:
        try:
            content = Path(args.content_file).read_text(encoding="utf-8")
        except Exception as e:
            print(f"CLARIFY: content-file 读取失败: {e}")
            return EXIT_CLARIFY
    elif args.content is not None:
        content = args.content
    else:
        print("CLARIFY: 缺 --content 或 --content-file")
        return EXIT_CLARIFY

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"CLARIFY: registry 不存在: {registry_path}")
        return EXIT_CLARIFY

    card = build_value_card(content, args.role, args.project, registry_path)
    verdict, reason = judge(card)
    write_ledger = not args.no_ledger
    ok = log_decision(card, verdict, reason, write_ledger=write_ledger,
                      exclusion_ledger=Path(args.exclusion_ledger),
                      decision_ledger=Path(args.decision_ledger))
    if not ok:
        print("VIOLATION: 台账写失败，判 B 熔断（台账不断供是块H硬约束）")
        return EXIT_VIOLATION

    # 块K：DEDUP_COUNT 侧效应（口径补充3 分流：matched 已 specialized → 吸收期；否 → 计数期）
    if verdict.startswith("DEDUP_COUNT:"):
        matched_sid = verdict.split(":", 1)[1]
        if write_ledger:
            try:
                reg = json.loads(registry_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"VIOLATION: registry 读取失败: {e}")
                return EXIT_VIOLATION
            entry = next((e for e in reg.get("entries", []) if e.get("skill_id") == matched_sid), None)
            if entry is not None and entry.get("specialized"):
                # ── 吸收期（补充3 ①②③④）：不计数、候选丢弃、有用行抽追加、ABSORB 台账 ──
                n_new, ok_abs = absorb_into_specialty(entry, content, card,
                                                      skills_dir=Path(args.skills_dir),
                                                      decision_ledger=Path(args.decision_ledger))
                if not ok_abs:
                    print("VIOLATION: 吸收台账写失败")
                    return EXIT_VIOLATION
                print(f"ABSORB_TARGET: {matched_sid} | new_lines={n_new}")
            elif args.defer_registry:
                # registry 由调用方持有内存镜像：本闸只落需求台账 + 打印目标，计数/转化调用方执行
                demand_remember(card, content, matched_sid, None, demand_ledger=Path(args.demand_ledger))
                print(f"DEMAND_TARGET: {matched_sid}")
            else:
                new_count = demand_remember(card, content, matched_sid, entry, demand_ledger=Path(args.demand_ledger))
                print(f"DEMAND_TARGET: {matched_sid} | demand_count={new_count}")
                if entry is not None and new_count >= DEMAND_SPECIALIZE_AT:
                    # 修订增补2：替代式转化——新专项 entry + 旧领域墓碑/移档/角色绑定替换
                    new_entry, new_md, ok_sp = specialize_replace(
                        entry, reg, skills_dir=Path(args.skills_dir),
                        archive_dir=Path(args.archive_dir),
                        demand_ledger=Path(args.demand_ledger),
                        decision_ledger=Path(args.decision_ledger),
                        role_links_path=Path(args.role_links) if args.role_links else ROLE_LINKS_PATH)
                    if not ok_sp:
                        print("VIOLATION: 转化留痕写失败")
                        return EXIT_VIOLATION
                    reg["total_entries"] = len([e for e in reg.get("entries", []) if e.get("status") != "archived"])
                    # 修订增补2②：ETL 无 update → 同一事务边界 deletes(旧领域)+writes(新专项)
                    # （CONTRACT.md 第三节晋升改写流程）；引擎离线/异常仅告警不阻断——
                    # 派生态可从源文件重建（CONTRACT.md 2.1），import_from_source.py 兜底
                    if args.no_engine:
                        print("  ⏭ --no-engine：跳过引擎晋升事务（仅测试/演练）")
                    else:
                        try:
                            reg_root = str(REGISTRY_DIR)
                            if reg_root not in sys.path:
                                sys.path.insert(0, reg_root)
                            from engine.kernel import retro_etl
                            ar = new_entry.get("affected_role") or ["be"]
                            r = retro_etl({"op": "batch", "trace_id": f"specialize-{new_entry['skill_id']}",
                                           "artifact": {"writes": [{
                                               "skill_id": new_entry["skill_id"], "content": new_md,
                                               "role": ar[0] if isinstance(ar, list) else ar,
                                               "project": new_entry.get("source_project", ""),
                                               "severity": new_entry.get("severity", "medium"),
                                               "bug_type": new_entry.get("bug_type") or ["code"],
                                               "keywords": [], "timing": "流程B Phase 1.5 — Bug诊断后 retro-skill-dispatcher MATCH 自动匹配",
                                               "sid": new_entry["skill_id"]}],
                                               "deletes": [matched_sid]}})
                            print(f"  🔁 引擎晋升事务（删旧增新同事务）: code={r.get('code')}")
                        except Exception as e:
                            print(f"  ⚠️ 引擎晋升事务异常（派生态可重建，不阻断）: {type(e).__name__}: {e}")
                # registry 写回仅计数期（吸收期零 registry 触碰；defer 期由调用方内存镜像负责）
                if entry is not None and not entry.get("specialized") and not args.defer_registry:
                    reg["last_updated"] = datetime.now().isoformat()
                    try:
                        registry_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception as e:
                        print(f"VIOLATION: registry 写回失败: {e}")
                        return EXIT_VIOLATION

    if args.json:
        print(json.dumps({"value_card": card, "verdict": verdict, "reason": reason}, ensure_ascii=False, indent=1))
    nd = card["near_duplicate"]
    print(f"VALUE-CARD: bug_type={card['bug_type']} severity={card['severity']} "
          f"craft(四段式={card['craft']['four_section_complete']},编号步骤={card['craft']['numbered_steps']},问题段={card['craft']['problem_len']}字) "
          f"targeted={card['targeted']} dup_containment={nd['containment_milli']}‰ peer={nd['peer']}")
    print(f"VERDICT: {verdict} | {reason}")
    if verdict == "B":
        return EXIT_B
    if verdict.startswith("MERGE:"):
        return EXIT_MERGE
    if verdict.startswith("DEDUP_COUNT:"):
        return EXIT_DEDUP
    return EXIT_A


if __name__ == "__main__":
    sys.exit(main())
