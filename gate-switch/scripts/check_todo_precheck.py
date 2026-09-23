#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_todo_precheck.py — todo_write 前置附身闸事后核验（漏跑必查）。

检查 ~/.agents/logs/todo_write_precheck.jsonl 是否留有 todo_write 前置附身闸触发记录。
todo_write 用过但此处无留痕 → 前置附身闸漏跑（B）。

退出码：0=已留痕（precheck 已触发）/ 1=无留痕（漏跑）。
"""
import json
import os
import sys

PRECHECK_LOG = os.environ.get(
    "TODO_PRECHECK_LOG",
    os.path.expanduser("~/.agents/logs/todo_write_precheck.jsonl"),
)


def main() -> int:
    if not os.path.isfile(PRECHECK_LOG):
        print("VIOLATION: todo_write_precheck.jsonl 不存在（todo_write 前置附身闸从未触发）")
        return 1
    count = 0
    for line in open(PRECHECK_LOG, encoding="utf-8"):
        if line.strip():
            count += 1
    if count == 0:
        print("VIOLATION: todo_write_precheck.jsonl 为空（前置附身闸漏跑）")
        return 1
    print(f"OK: todo_write 前置附身闸已触发留痕 {count} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
