#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_case_check.py — ui-test-engineer action 白名单 + 选择器合规校验（2026-08-15 裁定）

白名单 11 action（SKILL.md L44）；禁动态 class 选择器；选择器优先级 data-testid 首选。
"""
import argparse
import json
import re
import sys

WHITELIST = {"goto", "click", "input", "select", "wait", "assert_text",
             "assert_visible", "assert_not_visible", "assert_value", "assert_url", "refresh"}
DYNAMIC_CLASS = re.compile(r"class\*=|\[class=|jss\d+|css-[a-z0-9]{4,}|[.-][\w-]*[a-f0-9]{6,}")


def load_cases(path):
    data = json.load(open(path, encoding="utf-8"))
    return data if isinstance(data, list) else data.get("cases", data.get("execution_list", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    args = ap.parse_args()

    try:
        cases = load_cases(args.cases)
    except Exception as e:
        print(json.dumps({"pass": False, "violations": [f"用例读取失败: {e}"]}, ensure_ascii=False))
        sys.exit(1)

    violations = []
    for c in cases:
        if not isinstance(c, dict):
            continue
        cid = c.get("case_id") or c.get("id") or "?"
        steps = c.get("steps") or c.get("actions") or []
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            act = st.get("action")
            if act and act not in WHITELIST:
                violations.append(f"{cid} step{i+1}: action 白名单外 {act!r}（合法 11 个）")
            sel = st.get("selector") or st.get("target") or ""
            if isinstance(sel, str) and DYNAMIC_CLASS.search(sel):
                violations.append(f"{cid} step{i+1}: 动态 class 选择器 {sel!r}（禁，优先级 data-testid>id>name>xpath）")
            if isinstance(sel, str) and sel.startswith("xpath="):
                violations.append(f"{cid} step{i+1}: 直接使用 xpath 首选定位 {sel!r}（应优先 data-testid）")

    ok = not violations
    print(json.dumps({"pass": ok, "total_cases": len(cases), "violations": violations},
                     ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
