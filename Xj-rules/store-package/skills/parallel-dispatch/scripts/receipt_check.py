#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
receipt_check.py — parallel-dispatch 三槽契约 SLOT-RECEIPT 机械校验（2026-08-16 REFORM-GATE item2）

校验分身回报 JSON 五字段契约（SKILL.md 第六节 SLOT-RECEIPT）：
  1. status  ∈ {"done", "partial", "blocked"}
  2. artifacts 为数组；status=done 时非空；数组中每个路径必须真实存在
  3. deviation / blocker / todo_final 字段存在且为字符串（允许空串）

退出码：0 = 合格（母体照抄结论放行）  1 = 不合格（列出全部违例，母体 send_message 续派整改）

输入：--receipt <json文件>，或省略时从 stdin 读取。

用法：
  python3 receipt_check.py --receipt /path/to/receipt.json
  echo '{"status":"done",...}' | python3 receipt_check.py
"""
import argparse
import json
import os
import sys

VALID_STATUS = ("done", "partial", "blocked")
REQUIRED_STR_FIELDS = ("deviation", "blocker", "todo_final")


def check(receipt):
    """返回违例清单（空 = 合格）。"""
    violations = []
    if not isinstance(receipt, dict):
        return ["回报不是 JSON 对象"]

    status = receipt.get("status")
    if status not in VALID_STATUS:
        violations.append(f"status 非法: {status!r}（须 ∈ done|partial|blocked）")

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list):
        violations.append(f"artifacts 不是数组: {type(artifacts).__name__}")
    else:
        if status == "done" and not artifacts:
            violations.append("status=done 但 artifacts 为空（done 必须有产物）")
        for i, p in enumerate(artifacts):
            if not isinstance(p, str):
                violations.append(f"artifacts[{i}] 不是字符串: {p!r}")
            elif not os.path.exists(p):
                violations.append(f"artifacts[{i}] 路径不存在: {p}")

    for field in REQUIRED_STR_FIELDS:
        v = receipt.get(field)
        if field not in receipt:
            violations.append(f"缺少字段: {field}")
        elif not isinstance(v, str):
            violations.append(f"{field} 不是字符串: {type(v).__name__}")

    return violations


def main():
    ap = argparse.ArgumentParser(description="SLOT-RECEIPT 回报五字段机械校验")
    ap.add_argument("--receipt", help="分身回报 JSON 文件路径（省略则读 stdin）")
    args = ap.parse_args()

    if args.receipt:
        if not os.path.isfile(args.receipt):
            print(f"[receipt_check] FAIL: receipt 文件不存在: {args.receipt}")
            sys.exit(1)
        raw = open(args.receipt, encoding="utf-8").read()
    else:
        raw = sys.stdin.read()

    try:
        receipt = json.loads(raw)
    except Exception as e:
        print(f"[receipt_check] FAIL: JSON 解析失败: {e}")
        sys.exit(1)

    violations = check(receipt)
    if violations:
        print("[receipt_check] FAIL: RECEIPT 契约违例：")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    print("[receipt_check] PASS: RECEIPT 五字段契约全部满足")
    sys.exit(0)


if __name__ == "__main__":
    main()
