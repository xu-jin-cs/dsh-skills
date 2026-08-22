#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
loop_fuse_switch.py — 规则34 复刻循环熔断计数开关（2026-08-15 裁定）

轮次与同源补丁计数从"凭记忆"改为 jsonl 留痕：
  3 轮未过 → 强制升级（B）；同源补丁 >2 次 → 熔断（B）；超轮上限 → 熔断（B）。
四态退出码：0=A 继续 / 2=B 熔断 / 3=CLARIFY / 4=VIOLATION。
"""
import argparse
import datetime
import json
import os
import sys

HISTORY = os.path.expanduser("~/.agents/logs/loop_fuse_history.jsonl")


def load_history(loop_id):
    entries = []
    if os.path.isfile(HISTORY):
        for line in open(HISTORY, encoding="utf-8"):
            try:
                e = json.loads(line)
                if e.get("loop_id") == loop_id:
                    entries.append(e)
            except json.JSONDecodeError:
                continue
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop-id", required=True)
    ap.add_argument("--event", required=True, choices=["round", "patch"])
    ap.add_argument("--patch-sig", default="")
    ap.add_argument("--max-rounds", type=int, default=10)
    ap.add_argument("--upgrade-after", type=int, default=3)
    ap.add_argument("--fuse-same-patch", type=int, default=2)
    args = ap.parse_args()

    hist = load_history(args.loop_id)
    rounds = sum(1 for e in hist if e["event"] == "round") + (1 if args.event == "round" else 0)

    streak = 1
    if args.event == "patch":
        patches = [e for e in hist if e["event"] == "patch"]
        if patches and args.patch_sig and patches[-1].get("patch_sig") == args.patch_sig:
            streak = patches[-1].get("same_patch_streak", 1) + 1

    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "loop_id": args.loop_id, "event": args.event,
                            "patch_sig": args.patch_sig or None,
                            "rounds": rounds, "same_patch_streak": streak},
                           ensure_ascii=False) + "\n")

    verdict, reasons, code = "A", [], 0
    if rounds > args.max_rounds:
        verdict, code = "B", 2
        reasons.append(f"超轮次上限：rounds={rounds} > {args.max_rounds}，强制熔断，禁止继续循环")
    elif args.event == "round" and rounds == args.upgrade_after + 1:
        verdict, code = "B", 2
        reasons.append(f"{args.upgrade_after} 轮未过：第 {rounds} 轮强制升级方案（换思路，禁止同法第 {rounds} 次尝试）")
    elif args.event == "patch" and streak > args.fuse_same_patch:
        verdict, code = "B", 2
        reasons.append(f"同源补丁熔断：patch_sig 连续 {streak} 次相同 > {args.fuse_same_patch}，强制换素材/换方案")

    reasons = reasons or [f"继续放行：rounds={rounds}, same_patch_streak={streak}"]
    print(json.dumps({"verdict": verdict, "loop_id": args.loop_id, "event": args.event,
                      "rounds": rounds, "same_patch_streak": streak, "reasons": reasons},
                     ensure_ascii=False, separators=(",", ":")))
    sys.exit(code)


if __name__ == "__main__":
    main()
