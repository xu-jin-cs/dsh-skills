#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trigger_signal_scan.py — 开关第一推动·信号扫描开关（L2，2026-08-20 REFORM-GATE 判A落地，短板二改造）

问题：无钩子环境下"何时该扳开关"靠模型记住整张触发清单（12+ 行信号→开关映射），
F1-F8 后查审计证明漏扳真实发生。本开关把映射机械化为文本扫描：
  输入当前用户消息原文 → 逐信号机械匹配 → 输出命中信号+必扳开关清单，照抄执行。

自杀开关（REFORM-GATE 块已声明）：本开关自身的调用仍无钩子托底，
概率空间从"记 N 行映射"收窄为"1 条习惯"（任何用户输入先跑本扫描），不宣称根治；
F1-F8 后查保留兜底，若审计显示本扫描漏跑率仍高则框架终止回软层。

用法：
  python3 trigger_signal_scan.py --text "<用户输入原文>"
  python3 trigger_signal_scan.py --file <含输入文本的文件>
  python3 trigger_signal_scan.py --selftest        # 内建样例自检（供 spec script_exit 核验）

退出码（四态）：
  0 = HITS>0，命中信号清单已输出，照抄执行各 must_pull
  2 = NO-HIT，无任何机械信号命中（soft 提醒段仍输出，留软层）
  3 = CLARIFY，未提供输入
  4 = VIOLATION，signals 数据文件缺失/损坏

留痕：~/.agents/logs/trigger_signal_scan.jsonl（漏跑率纳入第一推动复盘审计）

L1 成分通道（2026-08-22 M3，REFORM-GATE 块E soft_signal_ngram 判A落地）：
  SOFT 信号从"keyword 不可判留软层"升级为成分可判——每个试点 SOFT 信号配若干
  AND 成分数组（每数组 2~4 个成分，trigger_signals.json 的 components 字段），
  分词（retro-match.sh 同口径 '[一-鿿]|[a-zA-Z0-9]+'）→ 变体归一为规范成分
  （component_lexicon.json，全部成分语料 df≥1 见证且 ≤2% 泛化上限）→
  任一数组成分全命中即成分命中。
  架构口径（2026-08-22 用户裁定）：技能不被触发、由 agent 直接加载使用——
  本通道的触发对象全部是【闸】：成分数组命中 → 应扳的闸（must_pull /
  准 must_pull 投递，对象均为 gate-switch 开关）；dispatcher_generate 的
  3 词原语/成分过滤仅作技术供体参照（分词与 df 见证方法论），不移植其
  "触发词→技能召回"语义。成分命中默认进 soft_reminders 投递并标注
  "成分命中·未标定"，不接 must_pull（概率标定属 M3b 接 NP 管线）；
  既有 L0 硬命中行为与退出码零改动。
"""
import argparse
import datetime
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
SIGNALS = os.path.join(HOME, ".agents/skills/gate-switch/data/trigger_signals.json")
LEXICON = os.path.join(HOME, ".agents/skills/gate-switch/data/component_lexicon.json")
LOG = os.path.join(HOME, ".agents/logs/trigger_signal_scan.jsonl")

EXIT_HITS, EXIT_NOHIT, EXIT_CLARIFY, EXIT_VIOLATION = 0, 2, 3, 4


def load_signals():
    if not os.path.isfile(SIGNALS):
        print(f"VIOLATION: signals 数据文件缺失: {SIGNALS}")
        sys.exit(EXIT_VIOLATION)
    try:
        with open(SIGNALS, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"VIOLATION: signals 数据文件损坏: {e}")
        sys.exit(EXIT_VIOLATION)


def load_lexicon():
    """成分归一表（变体→规范成分反向映射）。缺失/损坏时成分通道静默降级关闭，
    不阻断 L0 硬命中主流程（成分通道是增量面，非既有行为的依赖）。"""
    try:
        with open(LEXICON, encoding="utf-8") as f:
            data = json.load(f)
        rev = {}
        for canon, variants in data.get("components", {}).items():
            for v in variants:
                rev[v.lower()] = canon
        return rev
    except Exception:
        return {}


def component_scan(text, data, lexicon):
    """L1 成分通道：分词 → 归一映射 → AND 成分数组全命中判定。

    分词复用 retro-match.sh 原语 '[一-鿿]|[a-zA-Z0-9]+'（中文逐字、英文整词）；
    中文成分在压实串上做子串判定（逐字分词后多字词需重组），纯英文变体走整词
    集合判定（防 'debug' 误中 'bug' 类子串误伤）。每信号任一数组全命中即记一次。
    """
    if not lexicon:
        return []
    tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", (text or "").lower())
    ascii_tokens = {t for t in tokens if t.isascii()}
    compact = "".join(tokens)
    hit_variant = {}  # 规范成分 -> 实际命中的变体（取证留痕）
    for variant, canon in lexicon.items():
        if variant.isascii():
            hit = variant in ascii_tokens
        else:
            hit = variant in compact
        if hit and canon not in hit_variant:
            hit_variant[canon] = variant
    comp_hits = []
    for sig in data.get("soft_signals", []):
        for arr in sig.get("components", []):
            if arr and all(c in hit_variant for c in arr):
                delivery = sig.get("component_delivery", "soft_reminder")
                if delivery == "quasi_must_pull":
                    note = ("成分命中·未标定·准must_pull——命中即应扳 "
                            f"{sig['must_pull']}；M3b NP 标定后升入 must_pull")
                else:
                    note = "成分命中·未标定——投递 soft_reminders，不接 must_pull（概率标定属 M3b NP 管线）"
                comp_hits.append({
                    "id": sig["id"], "name": sig["name"],
                    "array": arr,
                    "matched_variants": {c: hit_variant[c] for c in arr},
                    "delivery": delivery,
                    "must_pull_soft": sig["must_pull"],
                    "note": note,
                })
                break  # 一个信号命中一个数组即足够
    return comp_hits


def scan(text, data):
    hits = []
    for sig in data.get("signals", []):
        matched = []
        for pat in sig.get("match", []):
            if sig.get("match_mode") == "regex":
                if re.search(pat, text):
                    matched.append(pat)
            else:
                if pat in text:
                    matched.append(pat)
        if matched:
            hits.append({"id": sig["id"], "name": sig["name"],
                         "matched": matched, "must_pull": sig["must_pull"]})
    return hits


def report(text, data, hits, comp_hits=None):
    comp_hits = comp_hits or []
    comp_hit_ids = {c["id"] for c in comp_hits}
    quasi_ids = {c["id"] for c in comp_hits if c.get("delivery") == "quasi_must_pull"}
    soft_reminders = []
    for s in data.get("soft_signals", []):
        entry = {"id": s["id"], "name": s["name"], "must_pull": s["must_pull"]}
        if s["id"] in comp_hit_ids:
            entry["component_hit"] = True
            entry["note"] = ("成分命中·未标定·准must_pull（命中即应扳 must_pull 内开关）"
                             if s["id"] in quasi_ids else "成分命中·未标定")
        soft_reminders.append(entry)
    directive = (
        "命中信号的 must_pull 逐条照抄执行，判定禁止手写；"
        "soft_reminders 为 keyword 不可判信号，留软层自查"
        if hits else
        "无机械信号命中；soft_reminders 段仍为软层自查项（多任务/会话开始/采纳落地等）"
    )
    if comp_hits:
        directive += "；component_hits 成分命中已标注入 soft_reminders（成分命中·未标定，不接 must_pull，标定属 M3b；准must_pull 级命中即应扳其 must_pull 内开关）"
    out = {
        "gate": "trigger_signal_scan",
        "input_len": len(text),
        "hits": hits,
        "component_hits": comp_hits,
        "soft_reminders": soft_reminders,
        "verdict": "HITS" if hits else "NO-HIT",
        "directive": directive,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def log_hit(out):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "verdict": out["verdict"],
                "hit_ids": [h["id"] for h in out["hits"]],
                "component_hit_ids": [c["id"] for c in out.get("component_hits", [])],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断主流程


def selftest():
    data = load_signals()
    cases = [
        ("代码交付前做一下性能审查", ["S-PERF"]),  # 2026-08-22 修：原 S-TEST-WORDS 用例已随信号摘除失效
        ("复盘一下本项目，验收通过可以收尾了", ["S-RETRO-WORDS"]),
        ("执行 rm -rf /tmp/x 清理", ["S-DANGER-CMD"]),
        ("技能已发布，记得 git push", ["S-PUBLISH-CLAIM"]),
        ("今天天气怎么样", []),
    ]
    bad = []
    for text, expect in cases:
        got = [h["id"] for h in scan(text, data)]
        for e in expect:
            if e not in got:
                bad.append(f"漏检: '{text}' 期望 {e} 实得 {got}")
        if not expect and got:
            bad.append(f"误检: '{text}' 期望空 实得 {got}")
    if bad:
        print("SELFTEST FAIL:\n" + "\n".join(bad))
        sys.exit(EXIT_VIOLATION)
    # L1 成分通道自检（归一表可用时才验；缺失=通道降级关闭，不算失败）
    lexicon = load_lexicon()
    if lexicon:
        comp_cases = [
            ("多任务并行处理这批", ["SOFT-MULTITASK"]),
            ("多个任务一起扇出", ["SOFT-MULTITASK"]),
            ("这些文件扇出执行", ["SOFT-MULTITASK"]),
            ("测试出问题了怎么办", ["SOFT-PROBLEM-RAISED"]),
            ("这个需求如何调整", ["SOFT-PLAN-SELECT"]),
            ("今天天气怎么样", []),
            ("今天天气怎么样聊聊", []),  # 单成分不满 AND 数组，不得命中
        ]
        for text, expect in comp_cases:
            got = [c["id"] for c in component_scan(text, data, lexicon)]
            for e in expect:
                if e not in got:
                    bad.append(f"成分漏检: '{text}' 期望 {e} 实得 {got}")
            if not expect and got:
                bad.append(f"成分误检: '{text}' 期望空 实得 {got}")
        if bad:
            print("SELFTEST FAIL(component):\n" + "\n".join(bad))
            sys.exit(EXIT_VIOLATION)
        print(f"SELFTEST PASS: {len(cases)} 硬命中样例 + {len(comp_cases)} 成分样例全中（含正/反例）")
    else:
        print(f"SELFTEST PASS: {len(cases)} 样例全中（含正/反例）；成分归一表缺失，成分通道降级关闭")
    sys.exit(EXIT_HITS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    text = a.text
    if a.file:
        path = os.path.expanduser(a.file)
        if not os.path.isfile(path):
            print(f"VIOLATION: 输入文件不存在: {path}")
            sys.exit(EXIT_VIOLATION)
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if not text:
        print("CLARIFY: 未提供输入（--text/--file/--selftest 三选一）")
        sys.exit(EXIT_CLARIFY)
    data = load_signals()
    hits = scan(text, data)
    comp_hits = component_scan(text, data, load_lexicon())
    out = report(text, data, hits, comp_hits)
    log_hit(out)
    sys.exit(EXIT_HITS if hits else EXIT_NOHIT)


if __name__ == "__main__":
    main()
