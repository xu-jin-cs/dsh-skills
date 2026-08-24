#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bug_fix_switch.py — bug-fix-strategy 优先级跳级禁令机械开关（强制填充门 L2 档，2026-08-15）

本源抽象：修复级别判定禁止 LLM 手写——"按优先级依次尝试禁止跳级"与
"同一Bug重复≥2次才允许重构"全部由本开关机械核验；重复次数从记忆改留痕，
每次扳动必追加历史，历史即计数信号来源。

四态退出码（与 gate_switch / dispatch_switch 同语义）：
  0 = A（放行，允许按该级别动手）   2 = B（阻断，reasons 即 B 档理由，照抄）
  3 = CLARIFY（输入信号不足）       4 = VIOLATION（输入本身非法）

判定规则（对齐 SKILL.md 五级优先级与禁止行为）：
  ① 跳级闸（level 1-4）：level > 该 bug 历史已实际尝试最高级 + 1 → B（禁止跳级）。
     level=5（重构）不走阶梯闸，由 ②③ 独立管控。
  ② 重构闸：level=5 且该 bug 重复次数 < 2 → B（重复次数不足）。
     重复次数 = 历史实际出手修复次数 - 1（首次出现不算重复）；
     只有判 A 的扳动算"实际出手"（判 B 被阻断，修复从未发生，不计数）。
  ③ 确认闸：level=5 且 --files-changed > 3 且无 --user-confirmed → B（>3文件需用户确认）。
  ④ 缺 --bug-id / --level → CLARIFY；level 非 1-5 整数 → VIOLATION。

留痕：~/.agents/logs/bug_fix_history.jsonl，每行 {ts, bug_id, level, verdict}，每次运行必追加。

用法：
  bug_fix_switch.py --bug-id <id> --level <1-5> [--files-changed N] [--user-confirmed]
输出：JSON {verdict, bug_id, level, history_count, reasons}
"""
import argparse
import datetime
import json
import os
import sys

DEFAULT_HISTORY = os.path.expanduser("~/.agents/logs/bug_fix_history.jsonl")
EXIT_A, EXIT_B, EXIT_CLARIFY, EXIT_VIOLATION = 0, 2, 3, 4
MIN_REPEAT_FOR_REFACTOR = 2  # 同一Bug重复≥2次才允许重构（level=5）
MAX_FILES_UNCONFIRMED = 3    # 重构改动 >3 文件需用户确认


def load_history(path, bug_id):
    """读取该 bug 的历史记录。

    返回 (history_count, repeat_count, max_attempted_level)：
      history_count       = 判 A（实际出手修复）的历史次数
      repeat_count        = history_count - 1（首次出现不算重复，下限 0）
      max_attempted_level = 判 A 记录中的最高修复级别（无则 0）
    """
    history_count, max_level = 0, 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("bug_id") != bug_id:
                    continue
                if rec.get("verdict") != "A":
                    continue  # 判 B 被阻断，修复从未发生，不计入出手次数
                history_count += 1
                try:
                    max_level = max(max_level, int(rec.get("level", 0)))
                except (TypeError, ValueError):
                    pass
    return history_count, max(0, history_count - 1), max_level


def append_history(path, bug_id, level, verdict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "bug_id": bug_id,
        "level": level,
        "verdict": verdict,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="bug-fix-strategy 优先级跳级禁令机械开关")
    ap.add_argument("--bug-id", dest="bug_id", help="Bug 标识（同一Bug复用同一id）")
    ap.add_argument("--level", type=int, help="本次拟动手的修复级别 1-5")
    ap.add_argument("--files-changed", dest="files_changed", type=int, default=None,
                    help="预计改动文件数（level=5 时用于 >3 文件确认闸）")
    ap.add_argument("--user-confirmed", dest="user_confirmed", action="store_true",
                    help="用户已确认（>3文件重构的唯一合法通道）")
    ap.add_argument("--history", default=DEFAULT_HISTORY, help="历史留痕 jsonl 路径")
    args = ap.parse_args()

    # ④ CLARIFY：输入信号不足
    missing = [k for k, v in (("--bug-id", args.bug_id), ("--level", args.level)) if v is None]
    if missing:
        json.dump({"verdict": "CLARIFY", "bug_id": args.bug_id, "level": args.level,
                   "history_count": None,
                   "reasons": [f"缺少必要参数 {' '.join(missing)}，补齐后重新扳动"]},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        sys.exit(EXIT_CLARIFY)

    # VIOLATION：输入本身非法
    if args.level not in (1, 2, 3, 4, 5):
        json.dump({"verdict": "VIOLATION", "bug_id": args.bug_id, "level": args.level,
                   "history_count": None,
                   "reasons": [f"level={args.level} 非法，仅允许 1-5（对应五级优先级）"]},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        sys.exit(EXIT_VIOLATION)

    history_count, repeat_count, max_attempted = load_history(args.history, args.bug_id)

    reasons = []
    # ① 跳级闸（level 1-4）：禁止跳级——只允许在历史实际尝试最高级基础上 +1 以内
    if args.level <= 4:
        allowed_max = max_attempted + 1
        if args.level > allowed_max:
            reasons.append(
                f"禁止跳级：level={args.level} > 历史已尝试最高级({max_attempted})+1，"
                f"当前仅允许 ≤{allowed_max}，请按优先级依次尝试")
    # ② 重构闸：同一Bug重复≥2次才允许重构（level=5 由本闸与③管控，不走阶梯）
    if args.level == 5 and repeat_count < MIN_REPEAT_FOR_REFACTOR:
        reasons.append(
            f"重复次数不足：该Bug历史实际修复 {history_count} 次（重复 {repeat_count} 次"
            f" < {MIN_REPEAT_FOR_REFACTOR} 次），单次/低频Bug禁止重构，先走低级别修复")
    # ③ 确认闸：>3文件未确认不得执行
    if (args.level == 5 and args.files_changed is not None
            and args.files_changed > MAX_FILES_UNCONFIRMED and not args.user_confirmed):
        reasons.append(
            f">3文件需用户确认：预计改动 {args.files_changed} 个文件 > {MAX_FILES_UNCONFIRMED}，"
            f"须先输出重构方案（当前问题/新结构/改动文件清单/执行顺序/验证方式）"
            f"并经用户确认（--user-confirmed）后方可执行")

    if reasons:
        verdict, code = "B", EXIT_B
        directive = "存在违例，阻断；reasons 即 B 档理由，照抄给用户，修复后重新扳动"
    else:
        verdict, code = "A", EXIT_A
        directive = "机械核验通过，照抄本结论放行，允许按该级别动手"

    append_history(args.history, args.bug_id, args.level, verdict)

    json.dump({"verdict": verdict, "bug_id": args.bug_id, "level": args.level,
               "history_count": history_count,
               "repeat_count": repeat_count,
               "max_attempted_level": max_attempted,
               "reasons": reasons,
               "directive": directive,
               "logged": args.history},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
