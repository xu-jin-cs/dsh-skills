#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_report_check.py — api-test-engineer 汇报照抄核验器（2026-08-15 裁定）

防汇报润色：汇报文本中的 exit code / gate_result / 通过率数字
必须与 api-summary.json 权威值一致，矛盾即判 B。
"""
import argparse
import json
import re
import sys


def dig_all(obj, keys, found, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if kl in keys and not isinstance(v, (dict, list)):
                found[kl] = v
            dig_all(v, keys, found, path + "." + k)
    elif isinstance(obj, list):
        for it in obj:
            dig_all(it, keys, found, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-text", required=True)
    ap.add_argument("--summary", required=True)
    args = ap.parse_args()

    try:
        summary = json.load(open(args.summary, encoding="utf-8"))
        text = open(args.report_text, encoding="utf-8").read()
    except Exception as e:
        print(json.dumps({"pass": False, "violations": [f"输入读取失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    auth = {}
    dig_all(summary, {"exit_code", "exit", "gate_result", "total", "passed", "failed", "pass_rate"}, auth)
    violations = []

    # gate_result 对照
    if "gate_result" in auth:
        claimed = re.findall(r"gate_result\s*[:=]\s*(\w+)", text, re.I)
        for c in claimed:
            if c.lower() != str(auth["gate_result"]).lower():
                violations.append(f"gate_result 矛盾: 权威={auth['gate_result']} 汇报={c}")
        # 权威 fail 时，文本不得出现通过结论且无 fail 字样
        if str(auth["gate_result"]).lower() == "fail" and not re.search(r"fail|不通过|打回", text, re.I):
            if re.search(r"全部通过|整体通过|验收通过|门禁通过", text):
                violations.append("权威 gate_result=fail，但汇报出现通过结论且无 fail 标注")

    # exit code 对照
    if "exit" in auth or "exit_code" in auth:
        expected = str(auth.get("exit_code", auth.get("exit")))
        claimed = re.findall(r"exit\s*(?:code)?\s*[:=]?\s*(\d+)", text, re.I)
        for c in claimed:
            if c != expected:
                violations.append(f"exit code 矛盾: 权威={expected} 汇报={c}")

    # X/Y 计数对照（汇报中形如 32/40 的通过计数）
    if "passed" in auth and "total" in auth:
        ep, et = str(auth["passed"]), str(auth["total"])
        for m in re.findall(r"(\d+)\s*/\s*(\d+)", text):
            if m[1] == et and m[0] != ep:
                violations.append(f"通过计数矛盾: 权威={ep}/{et} 汇报={m[0]}/{m[1]}")

    ok = not violations
    out = {"pass": ok, "checked_fields": sorted(auth.keys()), "violations": violations}
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
