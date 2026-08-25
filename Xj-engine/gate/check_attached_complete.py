#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_attached_complete.py — task_complete_hook 种入核验（task_complete_plant_gate 配套）。

读取 ATTACHED_LOG（默认 ~/.agents/logs/attached_plan.jsonl），确认存在
attached_complete_hook / mode=complete 的种入记录（新建任务时已把完成 hook 埋进任务）。

退出码：0=已种入 / 1=未种入（violations 即补种指令）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ATTACHED_LOG = os.environ.get(
    "ATTACHED_LOG",
    os.path.expanduser("~/.agents/logs/attached_plan.jsonl"),
)


def main() -> int:
    ap = argparse.ArgumentParser(description="核验 task_complete_hook 是否已种入")
    ap.add_argument("--task", default="", help="任务描述（可选，用于匹配 task）")
    args = ap.parse_args()

    if not os.path.isfile(ATTACHED_LOG):
        print("VIOLATION: attached 台账不存在（task_complete_hook 从未种入）")
        return 1

    found = False
    for line in open(ATTACHED_LOG, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("hook") in ("attached_complete_hook", "attached_plan_hook") \
                and e.get("mode") == "complete":
            if not args.task or args.task in (e.get("task") or e.get("desc") or ""):
                found = True
                break

    if not found:
        print("VIOLATION: attached 台账无 mode=complete 种入记录（task_complete_hook 未种入）")
        return 1

    print("OK: task_complete_hook 已种入（attached complete 留痕在案）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
