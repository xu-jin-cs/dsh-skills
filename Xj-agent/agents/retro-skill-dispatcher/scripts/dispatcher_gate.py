#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dispatcher_gate.py — retro-skill-dispatcher 分流/准入/匹配算分机械门禁（2026-08-15 裁定，门禁机制 L2 档：机械可判）

解决的问题：MATCH/GENERATE 分流准入五步判定原靠 PM 手工自觉，MATCH 匹配权重公式靠模型心算
（易伪造分数/偷懒声称无匹配）。本脚本把三处判定全部机械化，判定逻辑只来自：
  ① dispatcher_generate_config.json（fixed_phrases / skip_reason / workflow_switch / global_switch）
  ② registry-config.json（matching.threshold / matching.weights）
  ③ registry-index.json（entries 的 trigger_phrases / trigger_keywords / affected_role / bug_type）
  ④ 本文件头部冻结的显式规则集（BUG_SIGNALS / TOKEN 规则），禁止自由心证。

子命令：
  route  --context "<触发语境>"     机械判定 GENERATE / MATCH / NONE，输出 {"route", "reasons"}
  admission                         校验 GENERATE 准入五步（SKILL.md「准入判定流程」），
                                    输出 {"pass", "violations", "checks"}；全过 exit 0，否则 exit 1
  match  --context "<Bug诊断语境>" [--role R] [--bug-type T]
                                    按权重公式确定性算分，输出每条 entry 的分数与最佳匹配，
                                    防止模型心算伪造分数。未提供 role/bug-type 时该两维计 0（显式标注）。

MATCH 触发显式规则（冻结，改动需复盘裁定）：
  GENERATE 优先：context 命中 trigger_config.fixed_phrases 任一（substring）→ GENERATE。
  否则 context 命中 BUG_SIGNALS 任一（substring，英文大小写不敏感）→ MATCH
  （对应 SKILL.md 模式1「Bug诊断时」场景；registry 缺失仅在 reasons 标注，不改变 route）。
  都不命中 → NONE（不触发）。

分词规则（对齐 SKILL.md「maximal-run 分词」）：连续 CJK 为 1 个 token，
连续 [a-z0-9_] 为 1 个 token（小写化）。trigger_keywords 为集合精确相交。
AND-token 短语：trigger_phrases 元素为数组时，全部成分出现在 context 即命中。
"""
import argparse
import json
import os
import re
import sys

# 经验库（retro registry）根目录：可用环境变量 RETRO_REGISTRY_DIR 覆盖，默认 ~/.dsh/retro-experience-registry
REGISTRY_DIR = os.environ.get("RETRO_REGISTRY_DIR",
                              os.path.expanduser("~/.dsh/retro-experience-registry"))
GENERATE_CONFIG = os.path.join(REGISTRY_DIR, "dispatcher_generate_config.json")
REGISTRY_CONFIG = os.path.join(REGISTRY_DIR, "registry-config.json")
REGISTRY_INDEX = os.path.join(REGISTRY_DIR, "registry-index.json")
CHECK_RESULT = os.path.join(REGISTRY_DIR, "retro_check_result.json")

# MATCH 触发信号（冻结显式规则集：Bug/故障/报错语境特征词，中英双语，substring 命中即算）
BUG_SIGNALS = [
    "bug", "error", "exception", "traceback", "fail", "crash", "404", "500", "502", "503",
    "报错", "错误", "异常", "失败", "崩溃", "故障", "白屏", "黑屏", "卡死", "闪退",
    "不生效", "没反应", "不响应", "打不开", "加载不出", "显示不对", "时间不对", "数据不对",
    "修复", "诊断", "排查", "定位问题", "缺陷",
]

TOKEN_RE = re.compile(r"[一-鿿]+|[a-zA-Z0-9_]+")


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tokenize(text):
    """maximal-run 分词：CJK 连续段 / 英数连续段，英文小写化，去重保序。"""
    seen, out = set(), []
    for t in TOKEN_RE.findall(text):
        t = t.lower() if t.isascii() else t
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def phrase_hit(phrase, context):
    """字符串短语：substring；数组短语（AND-token）：全部成分出现即命中。"""
    if isinstance(phrase, list):
        return len(phrase) >= 2 and all(str(p) in context for p in phrase)
    return str(phrase) in context


# ───────────────────────── route ─────────────────────────

def cmd_route(context):
    reasons = []
    gen_hits, bug_hits = [], []

    if os.path.isfile(GENERATE_CONFIG):
        try:
            cfg = _load_json(GENERATE_CONFIG)
            phrases = cfg.get("trigger_config", {}).get("fixed_phrases", [])
            gen_hits = [p for p in phrases if p in context]
        except Exception as e:
            reasons.append(f"dispatcher_generate_config.json 解析失败: {e}（fixed_phrases 不可用）")
    else:
        reasons.append(f"dispatcher_generate_config.json 不存在: {GENERATE_CONFIG}")

    low = context.lower()
    bug_hits = [s for s in BUG_SIGNALS if (s in low if s.isascii() else s in context)]

    if gen_hits:
        route = "GENERATE"
        reasons.insert(0, f"命中 fixed_phrases（GENERATE 触发词）: {gen_hits}")
        if bug_hits:
            reasons.append(f"同时命中 Bug 信号 {bug_hits}，按裁定 GENERATE 触发词优先")
    elif bug_hits:
        route = "MATCH"
        reasons.append(f"命中 Bug 特征信号: {bug_hits}（对应 SKILL.md 模式1 Bug诊断场景）")
        if not os.path.isfile(REGISTRY_INDEX):
            reasons.append("registry-index.json 不存在 → 按 SKILL.md 输出 No retro skills available，跳过匹配走标准 Phase 2")
    else:
        route = "NONE"
        reasons.append("未命中 GENERATE fixed_phrases，未命中 Bug 特征信号 → dispatcher 不触发")

    print(json.dumps({"route": route, "reasons": reasons}, ensure_ascii=False, indent=2))
    return 0


# ───────────────────────── admission ─────────────────────────

def cmd_admission():
    """SKILL.md「准入判定流程」五步 + 准入字段有效性机械校验。"""
    checks = []  # (step, ok, detail)

    # Step 1: 配置文件存在且可解析
    cfg = None
    if not os.path.isfile(GENERATE_CONFIG):
        checks.append(("1-配置文件存在", False, f"{GENERATE_CONFIG} 不存在"))
    else:
        try:
            cfg = _load_json(GENERATE_CONFIG)
            checks.append(("1-配置文件存在且可解析", True, GENERATE_CONFIG))
        except Exception as e:
            checks.append(("1-配置文件可解析", False, f"JSON 解析失败: {e}"))

    if cfg is not None:
        # Step 2: global_switch 必须为 true
        gs = cfg.get("global_switch")
        checks.append(("2-global_switch==true", gs is True,
                       f"global_switch={gs!r}" + ("" if gs is True else " → 全局开关关闭/缺失，GENERATE 禁止")))

        # trigger_config 必备字段有效性
        tc = cfg.get("trigger_config", {})
        fp = tc.get("fixed_phrases")
        checks.append(("2a-fixed_phrases 非空列表", isinstance(fp, list) and len(fp) > 0,
                       f"fixed_phrases={fp!r}"))
        th = tc.get("llm_confidence_threshold")
        checks.append(("2b-llm_confidence_threshold∈[0,1]",
                       isinstance(th, (int, float)) and 0 <= th <= 1, f"threshold={th!r}"))
        for k in ("skip_reason_text", "skip_reason_abort_line"):
            v = tc.get(k)
            checks.append((f"2c-{k} 非空", isinstance(v, str) and bool(v.strip()), f"{k}={v!r}"))

        # Step 5（提前校验字段）：workflow_switch.vector_db_enabled 必须为 true
        ws = cfg.get("workflow_switch", {})
        vdb = ws.get("vector_db_enabled")
        checks.append(("5-vector_db_enabled==true", vdb is True,
                       f"vector_db_enabled={vdb!r}" + ("" if vdb is True else " → 向量库未启用，阻断")))
        for k in ("generate_skill", "register_index", "role_binding", "harness_audit"):
            v = ws.get(k)
            checks.append((f"5a-workflow_switch.{k} 为布尔", isinstance(v, bool), f"{k}={v!r}"))

        # Step 3+4: retro_check_result.json 的 generate_status / skip_reason
        if not os.path.isfile(CHECK_RESULT):
            checks.append(("3-retro_check_result.json 存在", False, f"{CHECK_RESULT} 不存在"))
        else:
            try:
                cr = _load_json(CHECK_RESULT)
                checks.append(("3-retro_check_result.json 存在且可解析", True, CHECK_RESULT))
                status = cr.get("generate_status")
                skip_text = tc.get("skip_reason_text", "")
                skip_reason = cr.get("skip_reason") or ""
                aborted = (status == "skipped" and isinstance(skip_text, str)
                           and skip_text and skip_text in skip_reason)
                checks.append(("4-非跳过态（skipped+skip_reason 匹配则阻断）", not aborted,
                               f"generate_status={status!r} skip_reason={skip_reason!r}"
                               + (" → 命中 skip_reason_text，输出 abort_line 直接退出" if aborted else "")))
            except Exception as e:
                checks.append(("3-retro_check_result.json 可解析", False, f"JSON 解析失败: {e}"))

    violations = [f"[{step}] {detail}" for step, ok, detail in checks if not ok]
    result = {
        "pass": not violations,
        "violations": violations,
        "checks": [{"step": s, "ok": ok, "detail": d} for s, ok, d in checks],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not violations else 1


# ───────────────────────── match ─────────────────────────

def cmd_match(context, role, bug_type):
    if not os.path.isfile(REGISTRY_INDEX):
        print(json.dumps({"matched": False,
                          "reason": f"registry-index.json 不存在: {REGISTRY_INDEX}"},
                         ensure_ascii=False, indent=2))
        return 0
    try:
        index = _load_json(REGISTRY_INDEX)
    except Exception as e:
        print(json.dumps({"matched": False, "reason": f"Registry解析失败: {e}"},
                         ensure_ascii=False, indent=2))
        return 0

    # 阈值与权重来自 registry-config.json，缺失回退 SKILL.md 默认值
    threshold, weights = 0.50, {"exact_phrase": 0.50, "keyword_overlap": 0.40,
                                "role_match": 0.05, "bug_type_match": 0.05}
    if os.path.isfile(REGISTRY_CONFIG):
        try:
            rc = _load_json(REGISTRY_CONFIG)
            m = rc.get("matching", {})
            threshold = m.get("threshold", threshold)
            weights.update(m.get("weights", {}))
        except Exception:
            pass

    tokens = tokenize(context)
    token_set = set(tokens)
    scored = []
    for e in index.get("entries", []):
        phrases = e.get("trigger_phrases", []) or []
        hit_phrases = [p for p in phrases if phrase_hit(p, context)]
        exact = 1.0 if hit_phrases else 0.0

        kws = {k.lower() if str(k).isascii() else str(k) for k in (e.get("trigger_keywords") or [])}
        overlap_hits = sorted(token_set & kws)
        overlap = (len(overlap_hits) / len(token_set)) if token_set else 0.0

        roles = e.get("affected_role") or []
        if isinstance(roles, str):
            roles = [roles]
        role_s = 1.0 if (role and role in roles) else 0.0

        types = e.get("bug_type") or []
        if isinstance(types, str):
            types = [types]
        type_s = 1.0 if (bug_type and bug_type in types) else 0.0

        score = (exact * weights["exact_phrase"] + overlap * weights["keyword_overlap"]
                 + role_s * weights["role_match"] + type_s * weights["bug_type_match"])
        scored.append({
            "skill_id": e.get("skill_id"),
            "score": round(score, 4),
            "breakdown": {"exact_phrase": exact, "keyword_overlap": round(overlap, 4),
                          "role_match": role_s, "bug_type_match": type_s},
            "hit_phrases": [str(p) for p in hit_phrases],
            "hit_keywords": overlap_hits,
            "frequency": e.get("frequency", 0),
        })

    # 降序；平分取 frequency 较高者（SKILL.md Step 4）
    scored.sort(key=lambda x: (-x["score"], -x["frequency"]))
    best = scored[0] if scored else None
    matched = bool(best and best["score"] >= threshold)

    out = {
        "matched": matched,
        "threshold": threshold,
        "weights": weights,
        "tokens": tokens,
        "role_input": role, "bug_type_input": bug_type,
        "note": ("role/bug_type 未提供，该两维按 0 计" if not (role and bug_type) else None),
        "best": best,
        "top": scored[:5],
        "total_entries": len(scored),
    }
    if best and not matched:
        out["action"] = f"No match (best: {best['score']:.2f} < {threshold:.2f})"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="retro-skill-dispatcher 分流/准入/算分机械门禁")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_route = sub.add_parser("route", help="MATCH/GENERATE/NONE 分流机械判定")
    p_route.add_argument("--context", required=True, help="触发语境描述")

    sub.add_parser("admission", help="GENERATE 准入五步校验（exit 0/1）")

    p_match = sub.add_parser("match", help="MATCH 匹配算分（权重公式确定性计算）")
    p_match.add_argument("--context", required=True, help="Bug 诊断语境/用户输入")
    p_match.add_argument("--role", default=None, help="诊断归属角色（可选）")
    p_match.add_argument("--bug-type", default=None, help="诊断问题类型（可选）")

    args = ap.parse_args()
    if args.cmd == "route":
        sys.exit(cmd_route(args.context))
    if args.cmd == "admission":
        sys.exit(cmd_admission())
    if args.cmd == "match":
        sys.exit(cmd_match(args.context, args.role, args.bug_type))


if __name__ == "__main__":
    main()
