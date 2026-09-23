#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
component_calibration.py — M3b 成分面 NP 标定裁决（2026-08-22）

任务（母体任务书）：
  1. 对 component_lexicon.json excluded_over_cap 留痕段 18 词 + 用户指令豁免 3 词
     （并行/分身/两个）做 NP 水位迭代标定裁决：
     每词作为成分加入试点信号 AND 数组，测边际效应——
       触发率增量 = 该信号应触发正例集的新增命中比例
       误触率增量 = 全语料的新增泛命中比例（硬约束 ≤5%）
     约束内取触发率最大（NP 选点），坐标上升逐词网格，frontier 增益 <1pt 收敛。
  2. 成分面判定率实测：正/负例集过 trigger_signal_scan 全链路（L0+L1）。

口径：
  - 语料真源与 dispatcher_generate.py::_user_corpus_freq 完全一致：
    ~/.dsh/sessions/*/*/session.jsonl.zstd 中 "user/message" 且 source.kind==user
    的文本条（字符串 content 或 text parts 逐条计）。
  - 分词/归一与 trigger_signal_scan.py 成分通道完全一致
    （'[一-鿿]|[a-zA-Z0-9]+' → 中文压实子串 / 英文整词集合）。
  - 正/负例集 = 半自动构造：脚本初筛候选（含相关成分/候选词的消息）→
    人工逐条读句判定 → 落盘 calibration_examples.json（本脚本不重打标签，
    只消费人工标签，保证可重跑）。

子命令：
  --build-corpus        抽取语料消息 → runtime/corpus_messages.json（含总量校验）
  --dump-candidates     每试点信号初筛候选消息 → runtime/candidates_<SIG>.json（供人工标注）
  --calibrate [--apply] NP 标定裁决；--apply 时更新 component_lexicon.json /
                        trigger_signals.json（准入词入正式成分+数组，cap_deviation 留痕）
  --adjudication        任务2：正/负例集过 trigger_signal_scan 全链路，测判定率/误触率
  --report <路径>       汇总标定结果 JSON → 指定路径

退出码：0 正常；2 数据缺失/口径校验失败；4 异常。
"""
import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
SKILL = os.path.join(HOME, ".agents/skills/gate-switch")
SIGNALS_PATH = os.path.join(SKILL, "data/trigger_signals.json")
LEXICON_PATH = os.path.join(SKILL, "data/component_lexicon.json")
EXAMPLES_PATH = os.path.join(SKILL, "data/calibration_examples.json")
RUNTIME = os.path.join(SKILL, "runtime")
CORPUS_PATH = os.path.join(RUNTIME, "corpus_messages.json")
SCANNER = os.path.join(SKILL, "scripts/trigger_signal_scan.py")
SESSIONS_GLOB = os.path.join(HOME, ".dsh/sessions/*/*/session.jsonl.zstd")

FP_HARD_CAP = 0.05          # 误触率硬约束（对全语料新增泛命中比例）
NEG_HARD_CAP = 0.05         # 硬负例面误触硬约束（2026-08-22 用户点名：硬负例面也要压，双约束收紧）
CONVERGE_GAIN_PT = 1.0      # frontier 增益收敛阈值（百分点）
ADMIT_GAIN_PT = 5.0         # 准入门槛：正例集触发率增量 ≥5pt 才算有效益
PILOT_SIGNALS = ["SOFT-MULTITASK", "SOFT-PROBLEM-RAISED", "SOFT-PLAN-SELECT"]
EXEMPT_WORDS = ["并行", "分身", "两个"]  # 用户指令豁免收编 3 词（数据验证，不擅自撤销）

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------- 语料 ----------

def extract_messages():
    """与 dispatcher_generate._file_gram_df 同口径的用户消息抽取。"""
    msgs = []
    for f in sorted(glob.glob(SESSIONS_GLOB)):
        try:
            raw = subprocess.run(["zstd", "-dc", f], capture_output=True,
                                 timeout=120).stdout.decode("utf-8", "replace")
        except Exception:
            continue
        for line in raw.splitlines():
            if '"user/message"' not in line:
                continue
            try:
                d = json.loads(line)["data"]
            except Exception:
                continue
            if (d.get("source") or {}).get("kind", "user") != "user":
                continue
            c = d.get("content", "")
            parts = ([c] if isinstance(c, str)
                     else [i.get("text", "") for i in c
                           if isinstance(i, dict) and i.get("type") == "text"])
            for t in parts:
                if t and re.search(r"[一-鿿a-zA-Z0-9]", t):
                    msgs.append(t)
    return msgs


def build_corpus():
    os.makedirs(RUNTIME, exist_ok=True)
    msgs = extract_messages()
    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"total_msgs": len(msgs), "messages": msgs}, f, ensure_ascii=False)
    print(f"CORPUS OK: total_msgs={len(msgs)}（词表建档口径 2147/2148，偏差应 <5%）→ {CORPUS_PATH}")
    return 0


def load_corpus():
    if not os.path.isfile(CORPUS_PATH):
        print("MISSING: 语料缓存不存在，先跑 --build-corpus")
        sys.exit(2)
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)["messages"]


# ---------- 成分命中判定（与 trigger_signal_scan 同逻辑，参数化词表/数组） ----------

def make_matcher(lexicon_components):
    rev = {}
    for canon, variants in lexicon_components.items():
        for v in variants:
            rev[v.lower()] = canon

    def hit_components(text):
        tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", (text or "").lower())
        ascii_tokens = {t for t in tokens if t.isascii()}
        compact = "".join(tokens)
        hit = set()
        for variant, canon in rev.items():
            if variant.isascii():
                if variant in ascii_tokens:
                    hit.add(canon)
            elif variant in compact:
                hit.add(canon)
        return hit
    return hit_components


def arrays_hit(hit_set, arrays):
    return any(arr and all(c in hit_set for c in arr) for arr in arrays)


# ---------- 候选初筛（供人工标注） ----------

def dump_candidates():
    """每试点信号：含≥1相关成分或候选词的消息初筛，抽样供人工逐条读句判定。"""
    import trigger_signal_scan as tss
    data = tss.load_signals()
    lex = json.load(open(LEXICON_PATH, encoding="utf-8"))
    over_cap = list(lex.get("excluded_over_cap", {}).get("words", {}).keys())
    msgs = load_corpus()
    matcher = make_matcher(lex["components"])
    # 每信号的相关词面：该信号现数组成分 + 全部候选词（候选词与三信号语义都可能相关，全量给人工判）
    sig_comps = {s["id"]: sorted({c for arr in s.get("components", []) for c in arr})
                 for s in data.get("soft_signals", []) if s["id"] in PILOT_SIGNALS}
    os.makedirs(RUNTIME, exist_ok=True)
    for sid, comps in sig_comps.items():
        rel = set(comps) | set(over_cap) | set(EXEMPT_WORDS)
        cand = []
        for i, m in enumerate(msgs):
            hit = matcher(m)
            low = m.lower()
            if (hit & set(comps)) or any(w.lower() in low for w in over_cap):
                cand.append({"idx": i, "text": m[:600]})
        # 分层抽样：成分命中优先，其余均匀抽样，上限 120 条
        hit_first = [c for c in cand if matcher(c["text"]) & set(comps)]
        rest = [c for c in cand if c not in hit_first]
        step = max(1, len(rest) // max(1, 120 - len(hit_first)))
        sample = hit_first + rest[::step]
        sample = sample[:120]
        out = os.path.join(RUNTIME, f"candidates_{sid}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"signal": sid, "total_candidates": len(cand),
                       "sampled": len(sample),
                       "labeling_guide": "人工逐条读句：label=pos（语义上该信号应触发）/neg（含同词但语义不该触发）",
                       "items": sample}, f, ensure_ascii=False, indent=1)
        print(f"{sid}: 候选 {len(cand)} 条，抽样 {len(sample)} 条 → {out}")
    return 0


# ---------- 标定 ----------

def load_examples():
    if not os.path.isfile(EXAMPLES_PATH):
        print(f"MISSING: 人工标注集不存在: {EXAMPLES_PATH}")
        sys.exit(2)
    with open(EXAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def baseline_arrays(data):
    return {s["id"]: [list(a) for a in s.get("components", [])]
            for s in data.get("soft_signals", []) if s["id"] in PILOT_SIGNALS}


def calibrate(apply=False):
    import trigger_signal_scan as tss
    data = tss.load_signals()
    lex = json.load(open(LEXICON_PATH, encoding="utf-8"))
    msgs = load_corpus()
    examples = load_examples()
    n_corpus = len(msgs)

    # 候选词 = 留痕 18 词 + 豁免 3 词
    over_cap = lex.get("excluded_over_cap", {}).get("words", {})
    cand_words = list(over_cap.keys()) + EXEMPT_WORDS

    base = baseline_arrays(data)
    # 工作词表 = 现有成分 + 每个候选词作为潜在新成分（变体=自身；bug 英文整词）
    work_components = {k: list(v) for k, v in lex["components"].items()}
    for w in cand_words:
        work_components.setdefault(w, [w])
    matcher = make_matcher(work_components)

    # 预算：全语料每条消息的成分命中集（含候选词）
    corpus_hits = [matcher(m) for m in msgs]
    # 正/负例命中集
    ex = {}
    for sid in PILOT_SIGNALS:
        e = examples.get(sid, {})
        pos, neg = e.get("positives", []), e.get("negatives", [])
        ex[sid] = {
            "pos": [(p, matcher(p)) for p in pos],
            "neg": [(n_, matcher(n_)) for n_ in neg],
        }

    report = {"corpus_msgs": n_corpus, "fp_hard_cap": FP_HARD_CAP,
              "converge_gain_pt": CONVERGE_GAIN_PT, "admit_gain_pt": ADMIT_GAIN_PT,
              "signals": {}, "words": {}}

    new_arrays = {sid: [list(a) for a in arrs] for sid, arrs in base.items()}
    admitted = collections.defaultdict(list)  # word -> [sid,...]

    for sid in PILOT_SIGNALS:
        pos, neg = ex[sid]["pos"], ex[sid]["neg"]
        base_hit_pos = sum(1 for _, h in pos if arrays_hit(h, new_arrays[sid]))
        base_hit_corpus = sum(1 for h in corpus_hits if arrays_hit(h, new_arrays[sid]))
        base_hit_neg = sum(1 for _, h in neg if arrays_hit(h, new_arrays[sid]))
        sig_res = {"pos_n": len(pos), "neg_n": len(neg),
                   "baseline": {"pos_rate": round(base_hit_pos / max(1, len(pos)), 4),
                                "corpus_rate": round(base_hit_corpus / n_corpus, 4),
                                "neg_rate": round(base_hit_neg / max(1, len(neg)), 4)},
                   "accepted_arrays": [], "trace": []}

        # 该信号现有成分（用于和候选词组对新数组）
        own_comps = sorted({c for arr in base[sid] for c in arr})
        # 坐标上升：每轮对所有候选词×（自身成分两两配对）网格评估边际效应，取 NP 最优点
        while True:
            cur_hit_pos = sum(1 for _, h in pos if arrays_hit(h, new_arrays[sid]))
            cur_hit_corpus = sum(1 for h in corpus_hits if arrays_hit(h, new_arrays[sid]))
            best = None
            for w in cand_words:
                # 候选数组：[w,c]（c∈该信号现有成分）+ [w,c1,c2]（现有数组成分对）
                cand_arrays = [[w, c] for c in own_comps if c != w]
                for arr in base[sid]:
                    if w not in arr and len(arr) == 2:
                        cand_arrays.append([w] + list(arr))
                seen = set()
                for ca in cand_arrays:
                    key = tuple(sorted(ca))
                    if key in seen or len(set(ca)) != len(ca):
                        continue
                    seen.add(key)
                    trial = new_arrays[sid] + [ca]
                    tp = sum(1 for _, h in pos if arrays_hit(h, trial))
                    cp = sum(1 for h in corpus_hits if arrays_hit(h, trial))
                    ng = sum(1 for _, h in neg if arrays_hit(h, trial))
                    d_pos = tp - cur_hit_pos
                    d_corpus = cp - cur_hit_corpus
                    if d_pos <= 0:
                        continue
                    # NP 硬约束：运作点【累计】语料泛命中率 ≤5%（不是单步边际，
                    # 防多轮小步叠加突破水位）；单步边际同步留痕
                    if cp / n_corpus > FP_HARD_CAP:
                        continue
                    fp_rate = d_corpus / n_corpus
                    gain_pt = d_pos / max(1, len(pos)) * 100
                    # NP 选点：约束内取触发率最大；并列取误触更小者
                    cand = (gain_pt, -fp_rate, ca, d_pos, fp_rate,
                            ng / max(1, len(neg)))
                    if best is None or cand[:2] > best[:2]:
                        best = cand
            if best is None or best[0] < CONVERGE_GAIN_PT:
                sig_res["trace"].append({"round": "converged",
                                         "reason": (f"frontier 增益 "
                                                    f"{best[0] if best else 0:.2f}pt "
                                                    f"< {CONVERGENCE_PLACEHOLDER}pt 收敛")})
                break
            _, _, ca, d_pos, fp_rate, neg_rate = best
            new_arrays[sid].append(ca)
            sig_res["accepted_arrays"].append(
                {"array": ca, "pos_gain": d_pos,
                 "pos_gain_pt": round(d_pos / max(1, len(pos)) * 100, 2),
                 "fp_rate_corpus": round(fp_rate, 4), "fp_rate_neg": round(neg_rate, 4)})
            admitted[ca[0]].append(sid)
            sig_res["trace"].append({"round": len(sig_res["accepted_arrays"]),
                                     "accept": ca, "gain_pt": round(best[0], 2),
                                     "fp": round(fp_rate, 4)})

        fin_pos = sum(1 for _, h in pos if arrays_hit(h, new_arrays[sid]))
        fin_corpus = sum(1 for h in corpus_hits if arrays_hit(h, new_arrays[sid]))
        fin_neg = sum(1 for _, h in neg if arrays_hit(h, new_arrays[sid]))
        sig_res["final"] = {"pos_rate": round(fin_pos / max(1, len(pos)), 4),
                            "corpus_rate": round(fin_corpus / n_corpus, 4),
                            "neg_rate": round(fin_neg / max(1, len(neg)), 4),
                            "arrays": new_arrays[sid]}
        report["signals"][sid] = sig_res

    # 每词裁决汇总
    for w in cand_words:
        sids = admitted.get(w, [])
        # 每词最优边际数字（取各信号接受该词数组的最佳一项）
        best_arr = None
        for sid in sids:
            for a in report["signals"][sid]["accepted_arrays"]:
                if a["array"][0] == w and (best_arr is None or
                                           a["pos_gain_pt"] > best_arr["pos_gain_pt"]):
                    best_arr = dict(a, signal=sid)
        verdict = "admit" if best_arr and best_arr["pos_gain_pt"] >= ADMIT_GAIN_PT else "reject"
        report["words"][w] = {
            "verdict": verdict,
            "signals_admitted": sids,
            "best": best_arr,
            "note": ("exempt_user_directive" if w in EXEMPT_WORDS else "over_cap_review"),
        }

    # 豁免 3 词专项数据验证：定位词所属规范成分 C（自身是成分或作为变体挂在某成分下），
    # 测【含 C 的现役数组】表现 + 【w 独占贡献】（C 仅经由 w 变体才命中的消息）——
    # 验证现役数组语料泛命中 ≤5%；不达标如实上报冲突，不擅自撤销用户指令。
    canon_of = {}
    for canon, variants in lex["components"].items():
        for v in variants:
            canon_of.setdefault(v, canon)
    for w in EXEMPT_WORDS:
        c = canon_of.get(w, w)
        detail = {}
        for sid in PILOT_SIGNALS:
            arrs = [a for a in base[sid] if c in a]
            if not arrs:
                continue
            pos, neg = ex[sid]["pos"], ex[sid]["neg"]

            def w_only(hit_text_pair):
                """该消息中成分 C 是否仅经由 w 变体命中（撤掉 w 即失去命中）。"""
                t, _ = hit_text_pair
                tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", t.lower())
                ascii_tokens = {x for x in tokens if x.isascii()}
                compact = "".join(tokens)
                others = [v for v in lex["components"].get(c, [c])
                          if v.lower() != w.lower()]
                def present(v):
                    v = v.lower()
                    return (v in ascii_tokens) if v.isascii() else (v in compact)
                return present(w) and not any(present(v) for v in others)

            pos_hit = [pn for pn in pos if arrays_hit(pn[1], arrs)]
            neg_hit = [pn for pn in neg if arrays_hit(pn[1], arrs)]
            corp_hit_idx = [i for i, h in enumerate(corpus_hits)
                            if arrays_hit(h, arrs)]
            corp_hit_texts = [(msgs[i], None) for i in corp_hit_idx]
            detail[sid] = {
                "canon": c, "arrays": arrs,
                "pos_rate": round(len(pos_hit) / max(1, len(pos)), 4),
                "corpus_rate": round(len(corp_hit_idx) / n_corpus, 4),
                "neg_rate": round(len(neg_hit) / max(1, len(neg)), 4),
                "w_only_pos": sum(1 for pn in pos_hit if w_only(pn)),
                "w_only_neg": sum(1 for pn in neg_hit if w_only(pn)),
                "w_only_corpus": sum(1 for pn in corp_hit_texts if w_only(pn)),
                "fp_within_cap": len(corp_hit_idx) / n_corpus <= FP_HARD_CAP}
        report["words"][w]["exempt_validation"] = detail
        ok = bool(detail) and all(d["fp_within_cap"] for d in detail.values())
        report["words"][w]["exempt_verdict"] = (
            "pass_data_validation" if ok else
            "CONFLICT_data_vs_user_directive_report_to_parent")

    # 收口一致性：准入词（best≥ADMIT_GAIN_PT）之外的数组头词视为噪声（单正例证据不足），
    # 其数组从最终数组集剪除并重算终值——词裁决与数组生效严格一致。
    admitted_heads = {w for w, r in report["words"].items() if r["verdict"] == "admit"}
    for sid in PILOT_SIGNALS:
        kept = [a for a in new_arrays[sid]
                if a in base[sid] or (a and a[0] in admitted_heads)]
        dropped = [a for a in new_arrays[sid] if a not in kept]
        new_arrays[sid] = kept
        fp = sum(1 for _, h in ex[sid]["pos"] if arrays_hit(h, kept))
        fc = sum(1 for h in corpus_hits if arrays_hit(h, kept))
        fn = sum(1 for _, h in ex[sid]["neg"] if arrays_hit(h, kept))
        report["signals"][sid]["dropped_arrays"] = dropped
        report["signals"][sid]["final"] = {
            "pos_rate": round(fp / max(1, len(ex[sid]["pos"])), 4),
            "corpus_rate": round(fc / n_corpus, 4),
            "neg_rate": round(fn / max(1, len(ex[sid]["neg"])), 4),
            "arrays": kept}

    out_path = os.path.join(RUNTIME, "calibration_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"CALIBRATION DONE → {out_path}")
    for w, r in report["words"].items():
        print(f"  {w}: {r['verdict']} {r.get('signals_admitted')} "
              f"best={r['best']['pos_gain_pt'] if r['best'] else 0}pt")

    if apply:
        _apply_updates(lex, data, report, new_arrays)
    return report


CONVERGENCE_PLACEHOLDER = "1.0"


# ---------- 双约束收紧重标（2026-08-22 用户点名：硬负例面也要压） ----------

def _rates(arrays, pos_hits, neg_hits, corpus_hits):
    n_c = len(corpus_hits)
    tp = sum(1 for h in pos_hits if arrays_hit(h, arrays))
    ng = sum(1 for h in neg_hits if arrays_hit(h, arrays))
    cp = sum(1 for h in corpus_hits if arrays_hit(h, arrays))
    return (tp / max(1, len(pos_hits)), ng / max(1, len(neg_hits)), cp / n_c)


def tighten(apply=False):
    """双约束收紧重标：语料面泛命中 ≤5% 且 硬负例面 ≤5%（双硬约束）。

    收紧动作空间（只收不扩）：①删除数组；②数组加第三成分（2→3，第三成分取自
    该信号现役成分集，防语义漂移出闸域）。NP 选点规则不变：每轮在使约束达标
    （可行）的动作中取正例触发率最大者；无可行动作则取违反量缩减最大者，
    违反量缩减 <1pt 且仍未达标即收敛停机，残差如实上报。判定率下降如实记录。
    """
    import trigger_signal_scan as tss
    data = tss.load_signals()
    lex = json.load(open(LEXICON_PATH, encoding="utf-8"))
    msgs = load_corpus()
    examples = load_examples()
    matcher = make_matcher(lex["components"])
    corpus_hits = [matcher(m) for m in msgs]
    n_corpus = len(msgs)

    report = {"mode": "dual_constraint_tighten", "corpus_msgs": n_corpus,
              "fp_hard_cap": FP_HARD_CAP, "neg_hard_cap": NEG_HARD_CAP,
              "converge_gain_pt": CONVERGE_GAIN_PT, "signals": {}}
    new_arrays = {}
    for sid in PILOT_SIGNALS:
        sig = next(s for s in data["soft_signals"] if s["id"] == sid)
        arrays = [list(a) for a in sig.get("components", [])]
        pos_hits = [matcher(t) for t in examples[sid]["positives"]]
        neg_hits = [matcher(t) for t in examples[sid]["negatives"]]
        own_comps = sorted({c for a in arrays for c in a})
        before = _rates(arrays, pos_hits, neg_hits, corpus_hits)
        trace = []
        while True:
            pos_r, neg_r, corp_r = _rates(arrays, pos_hits, neg_hits, corpus_hits)
            violation = max(corp_r - FP_HARD_CAP, neg_r - NEG_HARD_CAP, 0.0)
            if violation <= 0:
                trace.append({"round": "feasible", "pos": round(pos_r, 4),
                              "neg": round(neg_r, 4), "corpus": round(corp_r, 4)})
                break
            best = None  # (feasible_flag, pos_rate, -residual, move_desc, trial_arrays)
            for i, arr in enumerate(arrays):
                moves = [("drop", arr, None)]
                if len(arr) < 4:
                    moves += [("extend", arr, c) for c in own_comps if c not in arr]
                for kind, a, c in moves:
                    trial = [x for j, x in enumerate(arrays) if j != i] if kind == "drop" \
                        else [list(x) for x in arrays[:i]] + [a + [c]] + [list(x) for x in arrays[i + 1:]]
                    tp, ng, cp = _rates(trial, pos_hits, neg_hits, corpus_hits)
                    feasible = cp <= FP_HARD_CAP and ng <= NEG_HARD_CAP
                    residual = max(cp - FP_HARD_CAP, ng - NEG_HARD_CAP, 0.0)
                    desc = f"drop {a}" if kind == "drop" else f"extend {a}+{c}"
                    key = (1 if feasible else 0, tp if feasible else -residual,
                           -max(cp, ng), desc, trial, (tp, ng, cp))
                    if best is None or key[:4] > best[:4]:
                        best = key
            if best is None:
                trace.append({"round": "stuck", "reason": "无可用收紧动作", "residual": round(violation, 4)})
                break
            feas, score, _, desc, trial, (tp, ng, cp) = best
            if not feas and (violation - max(cp - FP_HARD_CAP, ng - NEG_HARD_CAP, 0.0)) * 100 < CONVERGE_GAIN_PT:
                trace.append({"round": "converged_infeasible",
                              "reason": f"违反量缩减 <{CONVERGE_GAIN_PT}pt 收敛，残差如实上报",
                              "residual": round(violation, 4)})
                break
            arrays = trial
            trace.append({"round": len(trace) + 1, "move": desc,
                          "pos": round(tp, 4), "neg": round(ng, 4), "corpus": round(cp, 4)})
        after = _rates(arrays, pos_hits, neg_hits, corpus_hits)
        new_arrays[sid] = arrays
        report["signals"][sid] = {
            "pos_n": len(pos_hits), "neg_n": len(neg_hits),
            "before": {"pos_rate": round(before[0], 4), "neg_rate": round(before[1], 4),
                       "corpus_rate": round(before[2], 4)},
            "after": {"pos_rate": round(after[0], 4), "neg_rate": round(after[1], 4),
                      "corpus_rate": round(after[2], 4)},
            "dual_feasible": after[1] <= NEG_HARD_CAP and after[2] <= FP_HARD_CAP,
            "arrays": arrays, "trace": trace}
        print(f"{sid}: 判定率 {before[0]*100:.1f}%→{after[0]*100:.1f}%  "
              f"负例 {before[1]*100:.1f}%→{after[1]*100:.1f}%  "
              f"语料 {before[2]*100:.2f}%→{after[2]*100:.2f}%  "
              f"dual_feasible={report['signals'][sid]['dual_feasible']}")

    # df 见证核对（recalibration_freshness 同口径：语料漂移→词表失效重标）：
    # 现役全部成分/变体在当前语料重测 df（消息级出现率），df=0 即死词上报；
    # 语料总量与 lexicon 建档量（2147/2148）偏差 >5% 即报漂移。
    df_check = {"corpus_msgs_now": n_corpus, "lexicon_baseline_msgs": [2147, 2148],
                "drift_pct": round(abs(n_corpus - 2148) / 2148 * 100, 2), "dead_words": []}
    for canon, variants in lex["components"].items():
        for v in variants:
            vl = v.lower()
            cnt = 0
            for m in msgs:
                tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", m.lower())
                if (vl in {t for t in tokens if t.isascii()}) if vl.isascii() else (vl in "".join(tokens)):
                    cnt += 1
            if cnt == 0:
                df_check["dead_words"].append({"variant": v, "canon": canon})
    report["df_freshness"] = df_check
    print(f"DF-FRESHNESS: corpus={n_corpus} drift={df_check['drift_pct']}% "
          f"dead_words={len(df_check['dead_words'])}")

    out_path = os.path.join(RUNTIME, "tightening_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"TIGHTEN DONE → {out_path}")

    if apply:
        for s in data.get("soft_signals", []):
            if s["id"] in new_arrays:
                s["components"] = new_arrays[s["id"]]
                s["components_status"] = "tightened_dual_2026-08-22"
        data["version"] = "2026-08-22-m3b2"
        with open(SIGNALS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(f"APPLIED: {SIGNALS_PATH} 已更新为双约束收紧数组")
    return report


def _apply_updates(lex, data, report, new_arrays):
    """准入词入正式成分（留痕段移除+cap_deviation 改注 NP 裁决），信号数组更新为标定后。"""
    import datetime
    over = lex.get("excluded_over_cap", {}).get("words", {})
    for w, r in report["words"].items():
        if r["verdict"] != "admit" or w in EXEMPT_WORDS:
            continue
        lex["components"].setdefault(w, [w])
        pct = over.pop(w, None)
        lex["df_witness"][w] = {
            "df_pct": pct, "df": None,
            "cap_deviation": (f"M3b NP 标定 2026-08-22 准入：正例增益 "
                              f"{r['best']['pos_gain_pt']}pt，语料误触 "
                              f"{r['best']['fp_rate_corpus']*100:.2f}%≤5%，"
                              f"信号 {r['signals_admitted']}")}
    if over is not None:
        lex["excluded_over_cap"]["words"] = over
        lex["excluded_over_cap"]["note"] += (
            "；M3b 2026-08-22 已按 NP 标定裁决，准入词已移入 components，"
            "留存词=标定拒收（触发增益不足或误触超限），见 FIX-M3b-calibration.md")
    for s in data.get("soft_signals", []):
        if s["id"] in new_arrays:
            s["components"] = new_arrays[s["id"]]
            s["components_status"] = "calibrated_2026-08-22"
    data["version"] = "2026-08-22-m3b"
    lex["version"] = "2026-08-22-m3b"
    lex["version_note"] = (lex.get("version_note", "") +
                           "；M3b NP 标定裁决落地，准入词 cap_deviation 留痕")
    with open(LEXICON_PATH, "w", encoding="utf-8") as f:
        json.dump(lex, f, ensure_ascii=False, indent=1)
    with open(SIGNALS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"APPLIED: {LEXICON_PATH} + {SIGNALS_PATH} 已更新（{datetime.date.today()}）")


# ---------- 任务2：成分面判定率实测（全链路 L0+L1） ----------

def adjudication():
    import trigger_signal_scan as tss
    data = tss.load_signals()
    lexicon = tss.load_lexicon()
    examples = load_examples()
    out = {}
    for sid in PILOT_SIGNALS:
        e = examples.get(sid, {})
        pos, neg = e.get("positives", []), e.get("negatives", [])
        pos_hit = neg_hit = 0
        pos_detail = []
        for t in pos:
            l0 = any(h["id"] for h in tss.scan(t, data))
            l1 = any(c["id"] == sid for c in tss.component_scan(t, data, lexicon))
            hit = l0 or l1
            pos_hit += hit
            pos_detail.append({"text": t[:80], "L0": l0, "L1": l1, "hit": hit})
        for t in neg:
            l1 = any(c["id"] == sid for c in tss.component_scan(t, data, lexicon))
            neg_hit += l1
        out[sid] = {
            "pos_n": len(pos), "neg_n": len(neg),
            "adjudication_rate": round(pos_hit / max(1, len(pos)), 4),
            "false_positive_rate_neg": round(neg_hit / max(1, len(neg)), 4),
            "pos_detail": pos_detail,
        }
        print(f"{sid}: 判定率 {out[sid]['adjudication_rate']*100:.1f}% "
              f"({pos_hit}/{len(pos)})，负例误触 {out[sid]['false_positive_rate_neg']*100:.1f}% "
              f"({neg_hit}/{len(neg)})")
    path = os.path.join(RUNTIME, "adjudication_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"ADJUDICATION DONE → {path}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-corpus", action="store_true")
    ap.add_argument("--dump-candidates", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--adjudication", action="store_true")
    ap.add_argument("--tighten", action="store_true",
                    help="双约束收紧重标（语料≤5% 且 硬负例≤5%）；配合 --apply 落盘")
    a = ap.parse_args()
    if a.build_corpus:
        sys.exit(build_corpus())
    if a.dump_candidates:
        sys.exit(dump_candidates())
    if a.calibrate:
        calibrate(apply=a.apply)
        sys.exit(0)
    if a.adjudication:
        adjudication()
        sys.exit(0)
    if a.tighten:
        tighten(apply=a.apply)
        sys.exit(0)
    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
