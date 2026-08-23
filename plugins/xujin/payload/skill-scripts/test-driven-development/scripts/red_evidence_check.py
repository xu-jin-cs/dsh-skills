#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
red_evidence_check.py — TDD RED 阶段真实性证据门（2026-08-15 裁定）

契约：RED 阶段运行失败输出必须落盘 <dir>/<case_id>.log（含失败特征）
与 <dir>/<case_id>.exit（runner 退出码，非 0）。缺一即判 B——
"声称断言如期失败"必须出示物证。
"""
import argparse
import glob
import json
import os
import sys

FAIL_PAT = ("FAILED", "AssertionError", "Error", "failed", "FAIL")


def load_case_ids(path):
    data = json.load(open(path, encoding="utf-8"))
    cases = data if isinstance(data, list) else data.get("cases", data.get("execution_list", []))
    ids = []
    for c in cases:
        if isinstance(c, dict):
            cid = c.get("case_id") or c.get("id")
            if cid:
                ids.append(str(cid))
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--cases", required=True)
    args = ap.parse_args()

    try:
        case_ids = load_case_ids(args.cases)
    except Exception as e:
        print(json.dumps({"pass": False, "violations": [f"用例清单读取失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)
    if not case_ids:
        print(json.dumps({"pass": False, "violations": ["用例清单无 case_id"]}, ensure_ascii=False))
        sys.exit(1)

    violations = []
    for cid in case_ids:
        log = os.path.join(args.dir, f"{cid}.log")
        exitc = os.path.join(args.dir, f"{cid}.exit")
        if not os.path.isfile(log) or os.path.getsize(log) == 0:
            violations.append(f"{cid}: RED 日志缺失或为空（{log}）")
            continue
        content = open(log, encoding="utf-8", errors="ignore").read()
        if not any(p in content for p in FAIL_PAT):
            violations.append(f"{cid}: RED 日志无失败特征（FAILED/AssertionError/Error）")
        if not os.path.isfile(exitc):
            violations.append(f"{cid}: 退出码文件缺失（{exitc}）")
        else:
            raw = open(exitc).read().strip()
            if not raw.lstrip("-").isdigit() or int(raw) == 0:
                violations.append(f"{cid}: RED 退出码非 0 要求不满足（实际={raw!r}）")

    ok = not violations
    print(json.dumps({"pass": ok, "total_cases": len(case_ids), "violations": violations},
                     ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
