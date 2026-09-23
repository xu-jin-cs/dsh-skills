#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_trigger_corpus_alignment.py — GENERATE 出口闸：新条目触发词必须语料对齐（每次对接，非概率）
2026-08-17 REFORM-GATE 判 A 落地（块 2026-08-trigger-alignment-mandatory.md）。

判据（全 0/1 机械）：
  A1 语料表可用：_user_corpus_freq() 返回非空（空=生成端必已降级，INFRA 违例）
  A2 当日新入库条目（created=今天，或 --date YYYY-MM-DD 指定）的 trigger_phrases
     全部成分 df≥1（用户历史会话真说过）。
     2026-08-20 闸体对齐 3词改造（原按整短语字面查 df_map——df_map 只有 2~4 字
     n-gram，3词短语 4~15 字恒查不中=闸体漂移误判）：成分 = dg._seg_words 分词，
     判定与生成端 _df 完全同构（英文整词查 df_words；中文 2~4 字直查；
     ≥5 字长词取全部 4-gram 最小 df）。
退出码：0=A 全过 / 2=B 违例清单。
"""
import argparse
import json
import os
import re
import sys
from datetime import date

_ASCII_WORD = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{2,15}$")  # 与 dispatcher_generate 语料对齐 v2 同款

REG = os.path.expanduser("~/.agents/retro-skills-registry/registry-index.json")
sys.path.insert(0, os.path.expanduser("~/.agents/retro-skills-registry/scripts"))
import dispatcher_generate as dg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    df_map, total, df_words = dg._user_corpus_freq()
    violations = []
    if not df_map:
        violations.append({"code": "A1-CORPUS-EMPTY", "detail": "语料词频表为空——本次生成未经语料对齐（禁止静默降级）"})
        print(json.dumps({"ok": False, "violations": violations}, ensure_ascii=False, indent=2))
        print("TRIGGER_ALIGNMENT_RESULT: FAIL dims=['A1']")
        return 2

    registry = json.load(open(REG, encoding="utf-8"))
    new_entries = [e for e in registry["entries"] if e.get("created") == args.date]
    if not new_entries:
        print(json.dumps({"ok": True, "note": f"{args.date} 无新入库条目，无对接义务", "violations": []}, ensure_ascii=False))
        print("TRIGGER_ALIGNMENT_RESULT: PASS new_entries=0")
        return 0

    def _comp_df(t: str) -> int:
        """成分 df 判定（与生成端 _extract_phrases._df 同构，2026-08-20 闸体对齐）。"""
        t = str(t).lower()
        if _ASCII_WORD.match(t):
            return df_words.get(t, 0)
        n = len(t)
        if 2 <= n <= 4:
            return df_map.get(t, 0)
        if n > 4:
            return min((df_map.get(t[i:i + 4], 0) for i in range(n - 3)), default=0)
        return 0

    for e in new_entries:
        bad = []
        for p in e.get("trigger_phrases", []):
            terms = [str(t) for t in p] if isinstance(p, list) else dg._seg_words(str(p))
            for t in terms:
                if _comp_df(t) < 1:
                    bad.append(t)
        if bad:
            violations.append({"code": "A2-DEAD-TERM", "skill_id": e["skill_id"][:60],
                               "detail": f"触发词成分语料未见（df=0）: {bad}"})

    out = {"ok": not violations, "date": args.date, "new_entries": len(new_entries),
           "corpus_msgs": total, "violations": violations}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        print(f"TRIGGER_ALIGNMENT_RESULT: FAIL dims=['A2'] count={len(violations)}")
        return 2
    print(f"TRIGGER_ALIGNMENT_RESULT: PASS new_entries={len(new_entries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
