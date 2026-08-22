#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_select_contract_check.py — plan_select.py 四态契约全路径回归（CLAIM-GATE 族复用件）

用途（2026-08-19 落地）：闸脚本 plan_select.py 改动后"声称已还原/已修复"的实证闸。
背景事故：有人改动 plan_select.py 后只验证 happy path 就声称"已还原"，
B 档路径（缺池文件）被误删退化成 traceback。本脚本机械回归 5 条路径：

  1. 正常 pool 文件（真实池文件）        → exit 0 且 stdout JSON verdict=="A"
  2. 不存在池文件                        → exit 2 且 stdout JSON verdict=="B"
  3. 空池文件（无方案块，tempfile 自建） → exit 3 且 stdout JSON verdict=="CLARIFY"
  4. --fail 1 不带 --reason（真实池）    → exit 4 且 stdout JSON verdict=="VIOLATION"
  5. 裸跑无参数                          → exit 2（argparse 错误）

全部通过 → exit 0；任一不符 → 打印失败明细到 stdout 并 exit 2。

账本零污染：以上调用会向 ~/.agents/logs/plan_select.jsonl 追加测试记录，
脚本运行前快照原内容，结束后截断恢复原样。
"""
import json
import os
import subprocess
import sys
import tempfile

PLAN_SELECT = os.path.expanduser("~/.agents/skills/plan-select/scripts/plan_select.py")
REAL_POOL = "/Users/xujin/.agents/logs/plan_select/POOL-20260819-190132.md"
LEDGER = os.path.expanduser("~/.agents/logs/plan_select.jsonl")


def run_case(name, argv, expect_exit, expect_verdict=None, verdict_from="stdout"):
    """执行一条路径并机械断言。verdict_from: stdout / None（不解析 JSON）"""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    errs = []
    if proc.returncode != expect_exit:
        errs.append(f"退出码 {proc.returncode} != 期望 {expect_exit}")
    if expect_verdict is not None:
        try:
            out = json.loads(proc.stdout)
            v = out.get("verdict")
            if v != expect_verdict:
                errs.append(f'verdict "{v}" != 期望 "{expect_verdict}"')
        except (json.JSONDecodeError, ValueError):
            errs.append(f"stdout 不是合法 JSON（前200字）: {proc.stdout[:200]!r}")
    return {"case": name, "argv": argv, "exit": proc.returncode,
            "expect_exit": expect_exit, "errors": errs,
            "stdout_tail": proc.stdout[-300:], "stderr_tail": proc.stderr[-300:]}


def main():
    # ---- 账本零污染：运行前快照 ----
    ledger_backup = None
    if os.path.isfile(LEDGER):
        with open(LEDGER, "rb") as f:
            ledger_backup = f.read()

    results = []
    empty_pool = None
    try:
        # 路径3 用 tempfile 自建空池（无「## 方案」块）
        fd, empty_pool = tempfile.mkstemp(suffix=".md", prefix="empty-pool-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# 空候选池（契约回归测试自建）\n\n此处无任何方案块。\n")

        results.append(run_case(
            "路径1 正常pool→A(exit 0)",
            ["python3", PLAN_SELECT, "--pool", REAL_POOL], 0, "A"))
        results.append(run_case(
            "路径2 缺池文件→B(exit 2)",
            ["python3", PLAN_SELECT, "--pool", "/tmp/nonexistent-pool-xx.md"], 2, "B"))
        results.append(run_case(
            "路径3 空池→CLARIFY(exit 3)",
            ["python3", PLAN_SELECT, "--pool", empty_pool], 3, "CLARIFY"))
        results.append(run_case(
            "路径4 --fail无--reason→VIOLATION(exit 4)",
            ["python3", PLAN_SELECT, "--pool", REAL_POOL, "--fail", "1"], 4, "VIOLATION"))
        results.append(run_case(
            "路径5 裸跑无参数→argparse(exit 2)",
            ["python3", PLAN_SELECT], 2, None))
    finally:
        # ---- 账本零污染：截断恢复原内容 ----
        if ledger_backup is not None:
            with open(LEDGER, "wb") as f:
                f.write(ledger_backup)
        elif os.path.isfile(LEDGER):
            os.remove(LEDGER)
        if empty_pool and os.path.isfile(empty_pool):
            os.remove(empty_pool)

    failed = [r for r in results if r["errors"]]
    if failed:
        print("PLAN_SELECT_CONTRACT_CHECK: FAIL")
        for r in failed:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(2)
    print("PLAN_SELECT_CONTRACT_CHECK: PASS (5/5 路径四态契约全部符合)")
    for r in results:
        print(f"  PASS {r['case']} exit={r['exit']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
