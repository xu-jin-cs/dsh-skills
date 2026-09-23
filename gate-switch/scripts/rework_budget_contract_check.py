#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rework_budget_contract_check.py — rework_budget.py 四态契约全路径回归（CLAIM-GATE 族复用件）

用途（2026-09-10 落地，REFORM-GATE 判A，块文件 ~/.agents/logs/reform_blocks/rework_budget_20260910.md）：
闸脚本 rework_budget.py 改动后"声称已修复/已完成"的实证闸（gate-switch 收尾纪律：
修改闸脚本无对应契约 spec 时先写 spec，禁止只跑 happy path 声称完成）。机械回归 10 条路径：

  1. 新 key 首次 stamp                    → exit 0 / A / label=回炉第 1 次（上限 3）
  2. 同 key 换闸换驳回点 stamp            → exit 0 / A / round=2（跨成员跨驳回点累计不清零）
  3. 第 3 次 stamp                        → exit 0 / A / round=3 / directive 含预算警告
  4. 第 4 次回炉请求                      → exit 2 / B / ruling=【卡死裁定】/ history 非空
  5. 卡死后再 stamp                       → exit 2 / B / count 仍=3（幂等，禁复活）
  6. status 查账                          → exit 0 / count=3 / status=stuck
  7. pass 未知 key                        → exit 3 / CLARIFY
  8. pass 预算内任务 → 再 stamp           → exit 0 销账；重开后 round 归 1
  9. 空 key stamp                         → exit 3 / CLARIFY
 10. 裸跑无参数                           → exit 2（argparse 错误）

全部通过 → exit 0；任一不符 → 打印失败明细到 stdout 并 exit 2。

账本零污染：全部用例以 --state-dir/--jsonl 指向临时目录；运行前后快照比对默认
~/.agents/logs/rework_budget.jsonl 与 ~/.agents/logs/rework_budget/，
被意外改动即恢复并记失败。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REWORK_BUDGET = os.path.expanduser("~/.agents/skills/gate-switch/scripts/rework_budget.py")
DEFAULT_STATE_DIR = os.path.expanduser("~/.agents/logs/rework_budget")
DEFAULT_JSONL = os.path.expanduser("~/.agents/logs/rework_budget.jsonl")


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


def main():
    # ---- 默认账本零污染：运行前快照 ----
    jsonl_backup = None
    if os.path.isfile(DEFAULT_JSONL):
        with open(DEFAULT_JSONL, "rb") as f:
            jsonl_backup = f.read()
    state_dir_snapshot = set()
    if os.path.isdir(DEFAULT_STATE_DIR):
        state_dir_snapshot = set(os.listdir(DEFAULT_STATE_DIR))

    failures = []
    results = []

    def check(name, proc, expect_exit, expect=None):
        errs = []
        if proc.returncode != expect_exit:
            errs.append(f"退出码 {proc.returncode} != 期望 {expect_exit}")
        if expect:
            try:
                out = json.loads(proc.stdout)
            except (json.JSONDecodeError, ValueError):
                errs.append(f"stdout 非合法 JSON: {proc.stdout[:200]!r}")
                out = {}
            for key, val in expect.items():
                got = out.get(key)
                if key == "directive_contains":
                    if val not in (out.get("directive") or ""):
                        errs.append(f'directive 不含 {val!r}')
                elif got != val:
                    errs.append(f'{key}={got!r} != 期望 {val!r}')
        results.append({"case": name, "exit": proc.returncode, "errors": errs})
        if errs:
            failures.append(name)

    tmp = tempfile.mkdtemp(prefix="rework_budget_contract_")
    sd = os.path.join(tmp, "state")
    jl = os.path.join(tmp, "log.jsonl")
    try:
        def stamp(key, gate="logic_gate", point="p", reason="r"):
            return run(["python3", REWORK_BUDGET, "stamp", "--key", key,
                        "--gate", gate, "--point", point, "--reason", reason,
                        "--state-dir", sd, "--jsonl", jl])

        check("1.新key首次stamp", stamp("契约任务A", point="力二缺反向"),
              0, {"verdict": "A", "label": "回炉第 1 次（上限 3）", "rework_round": 1})
        check("2.同key换闸累计", stamp("契约任务A", gate="plan_select", point="双校验失败"),
              0, {"verdict": "A", "rework_round": 2, "remaining": 1})
        check("3.第3次stamp带警告", stamp("契约任务A", gate="reform_gate", point="缺字段"),
              0, {"verdict": "A", "rework_round": 3, "remaining": 0,
                  "directive_contains": "卡死"})
        check("4.第4次回炉判卡死", stamp("契约任务A", point="力四无红线"),
              2, {"verdict": "B", "ruling": "【卡死裁定】"})
        check("5.卡死后再stamp幂等", stamp("契约任务A", point="再次驳回"),
              2, {"verdict": "B", "ruling": "【卡死裁定】"})
        p = run(["python3", REWORK_BUDGET, "status", "--key", "契约任务A",
                 "--state-dir", sd, "--jsonl", jl])
        check("6.status查账", p, 0, {"verdict": "A", "count": 3, "status": "stuck"})
        p = run(["python3", REWORK_BUDGET, "pass", "--key", "契约任务B-不存在",
                 "--state-dir", sd, "--jsonl", jl])
        check("7.pass未知key", p, 3, {"verdict": "CLARIFY"})
        stamp("契约任务C")
        p = run(["python3", REWORK_BUDGET, "pass", "--key", "契约任务C",
                 "--state-dir", sd, "--jsonl", jl])
        check("8a.pass预算内销账", p, 0, {"verdict": "A"})
        check("8b.销账后重开归1", stamp("契约任务C"),
              0, {"verdict": "A", "rework_round": 1})
        check("9.空key", stamp("   "), 3, {"verdict": "CLARIFY"})
        p = run(["python3", REWORK_BUDGET])
        check("10.裸跑", p, 2)
    finally:
        # ---- 默认账本零污染核验与恢复 ----
        polluted = False
        if jsonl_backup is None:
            if os.path.isfile(DEFAULT_JSONL):
                polluted = True
                os.remove(DEFAULT_JSONL)
        else:
            cur = open(DEFAULT_JSONL, "rb").read() if os.path.isfile(DEFAULT_JSONL) else None
            if cur != jsonl_backup:
                polluted = True
                with open(DEFAULT_JSONL, "wb") as f:
                    f.write(jsonl_backup)
        now_state = set(os.listdir(DEFAULT_STATE_DIR)) if os.path.isdir(DEFAULT_STATE_DIR) else set()
        if now_state != state_dir_snapshot:
            polluted = True
            for extra in now_state - state_dir_snapshot:
                victim = os.path.join(DEFAULT_STATE_DIR, extra)
                os.path.isdir(victim) and shutil.rmtree(victim) or os.remove(victim)
        if polluted:
            failures.append("默认账本污染（已恢复）")
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(json.dumps({"verdict": "B", "failed": failures, "detail": results},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"verdict": "A", "cases": len(results),
                      "note": "rework_budget.py 10 条契约路径全过 + 默认账本零污染"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
