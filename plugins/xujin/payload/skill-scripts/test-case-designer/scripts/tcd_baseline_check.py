#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tcd_baseline_check.py — test-case-designer 基线差异消费机械闸
（gate-switch spec: tcd_baseline.json 的 script_exit 被包装脚本，2026-08-16 D 域批量开关化）

对齐 test-case-designer/SKILL.md Step 1 L44：
  如果 test-baseline-diff.json 存在，设计前必须先读取，并在 execution-list.json 中标记受影响用例。

判定逻辑：
  - {project}/test-baseline-diff.json 不存在 → 闸不适用，PASS（N/A）。
  - 存在 → {project}/execution-list.json 必须存在、可解析、cases[] 非空，
    且每条用例必须携带受影响标记字段 `baseline_affected`（bool）；
    若 diff 中 added_endpoints/changed_endpoints/middleware_affected 任一非空，
    则至少一条用例必须 baseline_affected=true（有差异却零标记 = 没读 diff 凭记忆设计）。

退出码：0=PASS（含 N/A） / 2=违例 / 3=输入不足。纯 stdlib。
"""
import argparse
import json
import os
import sys

DIFF_KEYS = ("added_endpoints", "changed_endpoints", "middleware_affected")


def main():
    ap = argparse.ArgumentParser(description="基线差异 → 用例标记一致性机械校验")
    ap.add_argument("--project", required=True, help="项目根")
    ap.add_argument("--baseline", help="test-baseline-diff.json 路径（默认 {project}/ 下）")
    ap.add_argument("--exec", dest="exec_list",
                    help="execution-list.json 路径（默认 {project}/ 下）")
    args = ap.parse_args()

    baseline = args.baseline or os.path.join(args.project, "test-baseline-diff.json")
    exec_list = args.exec_list or os.path.join(args.project, "execution-list.json")

    if not os.path.isfile(baseline):
        print(f"[tcd_baseline] N/A 无基线差异文件 {baseline}，闸不适用，PASS")
        sys.exit(0)

    try:
        diff = json.load(open(baseline, encoding="utf-8"))
    except Exception as e:
        print(f"[tcd_baseline] CLARIFY: baseline diff 解析失败 {e}", file=sys.stderr)
        sys.exit(3)

    violations = []
    if not os.path.isfile(exec_list):
        violations.append(f"baseline diff 存在但 execution-list.json 缺失: {exec_list}")
    else:
        try:
            el = json.load(open(exec_list, encoding="utf-8"))
            cases = el.get("cases") if isinstance(el, dict) else None
            assert isinstance(cases, list) and cases, "cases[] 缺失或为空"
        except Exception as e:
            print(f"[tcd_baseline] CLARIFY: execution-list 解析失败 {e}", file=sys.stderr)
            sys.exit(3)
        no_marker = [c.get("case_id", f"#{i}") for i, c in enumerate(cases)
                     if not isinstance(c, dict) or not isinstance(c.get("baseline_affected"), bool)]
        if no_marker:
            violations.append(
                f"execution-list.json {len(no_marker)}/{len(cases)} 条用例缺"
                f" baseline_affected 标记字段: {no_marker[:5]}{'…' if len(no_marker) > 5 else ''}")
        has_diff = any(isinstance(diff.get(k), list) and diff[k] for k in DIFF_KEYS)
        if has_diff and not any(isinstance(c, dict) and c.get("baseline_affected") is True
                                for c in cases):
            violations.append("baseline diff 存在受影响端点（added/changed/middleware 非空），"
                              "但零条用例标记 baseline_affected=true（未消费 diff）")

    if violations:
        for v in violations:
            print(f"[tcd_baseline] VIOLATION {v}")
        print(f"[tcd_baseline] FAIL 违例 {len(violations)} 项")
        sys.exit(2)
    print("[tcd_baseline] PASS 基线差异已消费（受影响用例标记齐备）")
    sys.exit(0)


if __name__ == "__main__":
    main()
