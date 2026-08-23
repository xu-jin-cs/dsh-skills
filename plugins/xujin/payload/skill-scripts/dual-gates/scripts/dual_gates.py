#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dual_gates.py — 声明闸 Declaration Gate + 查询闸 Query Gate（正式定稿版落地）
核心原则：前置意图定性 → 定向溯源查询；严格 2 字词根白名单、无黑名单；
职责强隔离：查询链路只做定位与原始数据输出，推理/有效性判断全部后置下游。

子命令：
  declare  声明闸：双意图通道——①问题意图共现正则（真源 S-PROBLEM-GATE，优先）
           → is_problem（机械路由 problem_gate，不经裁量）；②2 字词根白名单
           词语边界匹配 → is_query / not_query
  query    查询闸：会话锚点定向检索 → 四模板输出（仅 is_query 时可进）
  anchor   锚点登记工具：向会话锚点注册表写入锚点（history / sourcecode）

退出码：0=正常输出；2=B 档阻断（如无锚点分流属正常输出不算阻断，仅契约违例）；4=VIOLATION（未过声明闸强行进查询闸等契约违例）
审计留痕：~/.agents/logs/dual_gates_audit.jsonl
锚点注册表：~/.agents/logs/session_anchors.jsonl
"""
import argparse, json, os, re, sys, uuid
from datetime import datetime, timezone, timedelta

# ━━━━━━━━━━━ 声明闸｜定稿 2 字查询白名单词根库（禁止直接新增 3 字及以上词条，新增须评审） ━━━━━━━━━━━
WHITELIST_ROOTS = [
    "获取", "查询", "检索", "查找", "找到", "读取", "查看", "调出", "取出",
    "定位", "提取", "列出", "展示", "返回", "列举", "调取", "评估", "找出", "挖掘",
    "调查", "寻找",
]
for _w in WHITELIST_ROOTS:
    assert len(_w) == 2, f"白名单词根必须为 2 汉字：{_w}"

# ━━━ 1 字兜底词（2026-08-23 用户裁定）：独立列表，绝不动 2 字白名单 assert ━━━
FALLBACK_ROOTS = ["找"]

LOG_DIR = os.path.expanduser("~/.agents/logs")
AUDIT_LOG = os.path.join(LOG_DIR, "dual_gates_audit.jsonl")
ANCHOR_DB = os.path.join(LOG_DIR, "session_anchors.jsonl")
PAYLOAD_CAP = 20000  # data_payload 截断上限（字符）
TRIGGER_SIGNALS = os.path.expanduser("~/.dsh/xujin-scripts/skills/gate-switch/data/trigger_signals.json")

# 意图硬路由通道表（2026-08-20 GENERALIZE-GATE 判 A「declare-gate-signal-channel」模式泛化）：
# 机械可判信号前置声明闸，命中即输出 must_pull 机械指令，不经用户/模型裁量。
# 顺序即优先级：安全 > 问题 > 查询白名单。
# （S-TEST-WORDS 测试通道 2026-08-20 用户裁定随超时闸取消一并摘除——测试任务不再进 TIME-BUDGET-GATE）
INTENT_CHANNELS = [
    ("S-DANGER-CMD", "danger", "安全"),
    ("S-PROBLEM-GATE", "problem", "问题"),
]


def load_signal(signal_id):
    """按 id 从 trigger_signals.json 加载信号定义（唯一真源，运行时加载禁双副本漂移）。"""
    try:
        with open(TRIGGER_SIGNALS, encoding="utf-8") as f:
            data = json.load(f)
        for sig in data.get("signals", []):
            if sig.get("id") == signal_id:
                return sig
    except Exception:
        pass
    return None


def match_signal(sig, raw_prompt):
    """按信号 match_mode 机械匹配（regex=共现正则 / keyword=关键词），返回命中片段或 None。"""
    if not sig:
        return None
    if sig.get("match_mode") == "regex":
        for p in sig.get("match", []):
            m = re.search(p, raw_prompt)
            if m:
                return m.group(0)
    else:
        for w in sig.get("match", []):
            if w in raw_prompt:
                return w
    return None

# 无锚点分流通路判定的外部数据信号（查询闸分流规则，非声明闸黑名单）
EXTERNAL_SIGNALS = ["http://", "https://", "外部", "联网", "官网", "网页", "网络"]

_CJK = r"\u4e00-\u9fff"
try:
    import jieba  # 词语边界：精确 2 字 token 匹配（优先通路）
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def audit(event, trace_id, session_id, extra=None, raw_prompt=None):
    """公共固定字段：trace_id, session_id, timestamp（声明闸事件强制携带 raw_prompt_snippet）"""
    os.makedirs(LOG_DIR, exist_ok=True)
    rec = {"event": event, "trace_id": trace_id, "session_id": session_id, "timestamp": now_iso()}
    if raw_prompt is not None:
        rec["raw_prompt_snippet"] = raw_prompt[:50]
    if extra:
        rec.update(extra)
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def tokenize(text):
    if _HAS_JIEBA:
        return [t for t in jieba.cut(text) if t.strip()]
    # 退化通路（无 jieba）：按非中日韩字符切分，词语边界语义降级为子串，见 SKILL.md 说明
    return [t for t in re.split(r"[^" + _CJK + r"A-Za-z0-9_]+", text) if t]


def match_whitelist(raw_prompt):
    """词语边界匹配：jieba 分词后精确等于某 2 字词根才命中（杜绝粗暴子串误伤）。
    无 jieba 退化：词根两侧不允许紧邻 ASCII 词字符的子串匹配。"""
    hits = []
    if _HAS_JIEBA:
        # 按 token 在原文中的出现顺序收集命中（match_keyword = 最先出现的词根）
        seen = set()
        for t in tokenize(raw_prompt):
            if t in WHITELIST_ROOTS and t not in seen:
                seen.add(t)
                hits.append(t)
    else:
        for w in WHITELIST_ROOTS:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(w) + r"(?![A-Za-z0-9_])", raw_prompt):
                hits.append(w)
    # 1 字兜底词（FALLBACK_ROOTS）：白名单未命中时才降级尝试；命中归 white_list 且标注「(兜底)」
    if not hits:
        if _HAS_JIEBA:
            for t in tokenize(raw_prompt):  # jieba 单字 token 精确命中
                if t in FALLBACK_ROOTS:
                    hits.append(t + "(兜底)")
                    break
        else:
            for w in FALLBACK_ROOTS:  # 无 jieba 退化为词边界子串命中
                if re.search(r"(?<![A-Za-z0-9_])" + re.escape(w) + r"(?![A-Za-z0-9_])", raw_prompt):
                    hits.append(w + "(兜底)")
                    break
    return hits


def load_input(args):
    """入参来源优先级：--input JSON 串 / @文件 > --raw 文本"""
    if args.input:
        s = args.input
        if s.startswith("@"):
            with open(s[1:], encoding="utf-8") as f:
                s = f.read()
        return json.loads(s)
    return {"raw_prompt": args.raw or ""}


# ━━━━━━━━━━━ 声明闸 Declaration Gate ━━━━━━━━━━━
def cmd_declare(args):
    inp = load_input(args)
    trace_id = inp.get("trace_id") or args.trace_id or uuid.uuid4().hex[:16]
    session_id = inp.get("session_id") or args.session_id or ""
    raw_prompt = inp.get("raw_prompt", "")

    audit("declaration_gate_start", trace_id, session_id, raw_prompt=raw_prompt)

    # 通道①（优先）：意图硬路由——按 INTENT_CHANNELS 顺序机械匹配信号真源，
    # 命中即输出 is_<intent> + must_pull（真源 must_pull 原文透传），不经裁量
    for sig_id, name, label in INTENT_CHANNELS:
        sig = load_signal(sig_id)
        hit = match_signal(sig, raw_prompt)
        if not hit:
            continue
        audit(f"declaration_gate_{name}_hit", trace_id, session_id,
              {"signal_id": sig_id, "match_snippet": hit}, raw_prompt)
        out = {
            "trace_id": trace_id,
            "declaration_result": f"is_{name}",
            "intent_label": label,
            "match_type": f"signal:{sig_id}",
            "match_keyword": hit,
            "reason": f"命中信号 {sig_id}（{sig.get('name', '')}，真源 trigger_signals.json）→ 机械路由",
            "must_pull": sig.get("must_pull", []),
        }
        audit(f"declaration_gate_is_{name}", trace_id, session_id,
              {"match_type": f"signal:{sig_id}", "intent_label": label}, raw_prompt)
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    # 通道②：2 字词根白名单 → is_query / not_query
    hits = match_whitelist(raw_prompt)

    if hits:
        for h in hits:
            audit("declaration_gate_white_hit", trace_id, session_id, {"match_keyword": h}, raw_prompt)
        out = {
            "trace_id": trace_id,
            "declaration_result": "is_query",
            "intent_label": "查询",
            "match_type": "white_list",
            "match_keyword": hits[0],
            "reason": "命中白名单词根",
        }
        audit("declaration_gate_is_query", trace_id, session_id,
              {"match_type": "white_list", "intent_label": "查询"}, raw_prompt)
    else:
        audit("declaration_gate_no_match", trace_id, session_id, raw_prompt=raw_prompt)
        out = {
            "trace_id": trace_id,
            "declaration_result": "not_query",
            "intent_label": "非查询",
            "match_type": "no_match",
            "match_keyword": "",
            "reason": "未匹配查询白名单，判定为非查询任务",
        }
        audit("declaration_gate_not_query", trace_id, session_id,
              {"match_type": "no_match", "intent_label": "非查询"}, raw_prompt)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


# ━━━━━━━━━━━ 查询闸 Query Gate ━━━━━━━━━━━
def load_anchors(session_id):
    if not os.path.exists(ANCHOR_DB):
        return []
    out = []
    with open(ANCHOR_DB, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("session_id") == session_id:
                out.append(rec)
    return out


def relevance(prompt_tokens, anchor):
    """定向相关性：prompt 的 2 字及以上中文 token 与锚点 title/source_path 的交集计数（机械可判，无语义推理）"""
    hay = (anchor.get("title", "") + " " + anchor.get("source_path", ""))
    return sum(1 for t in prompt_tokens if len(t) >= 2 and re.search(r"[" + _CJK + r"]", t) and t in hay)


def read_payload(anchor):
    """原始数据输出：优先读 source_path 文件原文，其次 data_ref 内联内容；不做任何解读"""
    sp = anchor.get("source_path", "")
    if sp and os.path.isfile(os.path.expanduser(sp)):
        with open(os.path.expanduser(sp), encoding="utf-8", errors="replace") as f:
            data = f.read()
        truncated = len(data) > PAYLOAD_CAP
        return (data[:PAYLOAD_CAP], truncated)
    return (anchor.get("data_ref", ""), False)


def cmd_query(args):
    inp = load_input(args)
    trace_id = inp.get("trace_id") or args.trace_id or uuid.uuid4().hex[:16]
    session_id = inp.get("session_id") or args.session_id or ""
    raw_prompt = inp.get("raw_prompt", "")

    # 契约硬约束：仅当声明闸输出 is_query 才允许执行查询闸
    if inp.get("declaration_result") != "is_query":
        json.dump({"trace_id": trace_id, "error": "VIOLATION: 查询闸仅允许 declaration_result=is_query 时进入",
                   "received": inp.get("declaration_result")}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 4

    audit("query_gate_start", trace_id, session_id)
    anchors = load_anchors(session_id)
    ptoks = tokenize(raw_prompt)
    scored = [(relevance(ptoks, a), a) for a in anchors]
    hits = [a for s, a in scored if s > 0]

    out = None
    if hits:
        audit("query_gate_anchor_found", trace_id, session_id, {"anchor_count": len(hits)})
        hist = [a for a in hits if a.get("anchor_type") == "history"]
        srcs = [a for a in hits if a.get("anchor_type") == "sourcecode"]
        if hist:
            # 时序规则：多条历史记录仅按 record_time 取最新一条，不做内容相似度择优
            latest = max(hist, key=lambda a: a.get("record_time", ""))
            payload, truncated = read_payload(latest)
            out = {
                "trace_id": trace_id,
                "gate_result": "hit_history",
                "data_payload": payload,
                "source_path": latest.get("source_path", ""),  # 强制溯源：缺失即不合规
                "record_time": latest.get("record_time", ""),
            }
            if truncated:
                out["truncated"] = True
            if not out["source_path"]:
                out["compliance_error"] = "历史记录类结果缺失 source_path，查询闸输出不合规"
                json.dump(out, sys.stdout, ensure_ascii=False, indent=2); print()
                return 2
            audit("query_gate_hit_history", trace_id, session_id,
                  {"source_path": out["source_path"], "record_time": out["record_time"]})
        elif len(srcs) == 1:
            payload, truncated = read_payload(srcs[0])
            out = {"trace_id": trace_id, "gate_result": "hit_sourcecode", "data_payload": payload}
            if truncated:
                out["truncated"] = True
            audit("query_gate_hit_source", trace_id, session_id)
        else:
            # 多条源码锚点：取相关性最高者（机械择优，仍不做内容判断）
            best = max(((relevance(ptoks, a), a) for a in srcs), key=lambda x: x[0])[1]
            payload, truncated = read_payload(best)
            out = {"trace_id": trace_id, "gate_result": "hit_sourcecode", "data_payload": payload}
            if truncated:
                out["truncated"] = True
            audit("query_gate_hit_source", trace_id, session_id)

    if out is None:
        audit("query_gate_anchor_notfound", trace_id, session_id)
        if any(sig in raw_prompt for sig in EXTERNAL_SIGNALS):
            out = {"trace_id": trace_id, "gate_result": "no_anchor_external",
                   "forward": "external_query_channel"}
            audit("query_gate_forward_external", trace_id, session_id)
        else:
            out = {"trace_id": trace_id, "gate_result": "no_anchor_internal",
                   "forward": "read_raw_source"}
            audit("query_gate_forward_internal_source", trace_id, session_id)

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


# ━━━━━━━━━━━ 锚点登记工具（幂等：内容哈希判定，同键更新不追加） ━━━━━━━━━━━
def _content_hash(anchor_type, source_path, data_ref):
    """产物内容 sha1：文件优先，data_ref 兜底；都无则为空串"""
    import hashlib
    sp = os.path.expanduser(source_path) if source_path else ""
    if sp and os.path.isfile(sp):
        with open(sp, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    if data_ref:
        return hashlib.sha1(data_ref.encode("utf-8")).hexdigest()
    return ""


def cmd_anchor(args):
    os.makedirs(LOG_DIR, exist_ok=True)
    chash = _content_hash(args.type, args.path, args.data_ref)
    rec = {
        "session_id": args.session_id,
        "anchor_type": args.type,           # history | sourcecode
        "title": args.title or "",
        "source_path": args.path or "",
        "record_time": args.record_time or now_iso(),
        "content_hash": chash,
        "data_ref": args.data_ref or "",
        "registered_at": now_iso(),
    }
    if rec["anchor_type"] == "history" and not rec["source_path"]:
        print("VIOLATION: history 锚点必须携带 source_path（溯源强制要求）", file=sys.stderr)
        return 4

    # 幂等键 = (session_id, source_path)：同键同哈希→空操作；同键不同哈希→原位更新时间/哈希；无同键→追加
    rows = []
    if os.path.exists(ANCHOR_DB):
        with open(ANCHOR_DB, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    idx = next((i for i, r in enumerate(rows)
                if r.get("session_id") == rec["session_id"]
                and r.get("source_path") == rec["source_path"]
                and rec["source_path"]), None)
    tid = uuid.uuid4().hex[:16]

    if idx is not None and rows[idx].get("content_hash") == chash:
        audit("anchor_idempotent_noop", tid, rec["session_id"], {"source_path": rec["source_path"]})
        json.dump({"status": "idempotent_noop", "reason": "同键同内容哈希，幂等空操作未写盘",
                   "anchor": rows[idx]}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    if idx is not None:
        rows[idx].update({k: v for k, v in rec.items() if k != "registered_at" or not rows[idx].get(k)})
        rows[idx]["record_time"] = rec["record_time"]
        rows[idx]["content_hash"] = chash
        if rec["title"]:
            rows[idx]["title"] = rec["title"]
        with open(ANCHOR_DB, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        audit("anchor_updated", tid, rec["session_id"],
              {"source_path": rec["source_path"], "record_time": rec["record_time"]})
        json.dump({"status": "updated", "reason": "同键不同内容哈希，原位更新 record_time/content_hash，未追加新行",
                   "anchor": rows[idx]}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    with open(ANCHOR_DB, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    audit("anchor_registered", tid, rec["session_id"], {"source_path": rec["source_path"]})
    json.dump({"status": "registered", "anchor": rec}, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


def main():
    p = argparse.ArgumentParser(description="声明闸+查询闸 双闸落地脚本")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("declare", cmd_declare), ("query", cmd_query)]:
        sp = sub.add_parser(name)
        sp.add_argument("--input", help="入参 JSON 串或 @文件路径")
        sp.add_argument("--raw", help="原始请求文本（无 --input 时）")
        sp.add_argument("--trace-id", default="")
        sp.add_argument("--session-id", default="")
        sp.set_defaults(fn=fn)
    ap = sub.add_parser("anchor")
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--type", required=True, choices=["history", "sourcecode"])
    ap.add_argument("--title", default="")
    ap.add_argument("--path", default="")
    ap.add_argument("--record-time", default="")
    ap.add_argument("--data-ref", default="")
    ap.set_defaults(fn=cmd_anchor)
    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
