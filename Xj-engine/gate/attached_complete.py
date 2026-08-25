#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attached_complete.py — 任务"完成步骤"（被附身闸追加到任务末尾）。

完成不是 hook、不是引擎调用，而是一个**执行步骤**：
  完成步骤 = `todo_write` 将该任务 `status` 置为 `"completed"`（DSH 面板打勾）。

该步骤由 `task_complete_attach_gate.py`（附身闸）在新建任务时触发追加到任务末尾；
任务执行到该步即完成。本脚本只是把"完成步骤"的定义与留痕输出出来。

用法：
  python3 attached_complete.py --task "任务描述"

留痕：默认 ~/.agents/logs/attached_plan.jsonl，可用环境变量 ATTACHED_LOG 覆盖。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

ATTACHED_LOG = os.environ.get(
    "ATTACHED_LOG",
    os.path.expanduser("~/.agents/logs/attached_plan.jsonl"),
)

COMPLETE_STEP = '完成步骤：todo_write 将该任务 status 置为 "completed"（DSH 面板打勾）'


def main() -> int:
    ap = argparse.ArgumentParser(description="任务完成步骤定义与留痕")
    ap.add_argument("--task", required=True, help="任务描述")
    ap.add_argument("--host", default="task_complete_attach_gate", help="调用方标识")
    args = ap.parse_args()

    out = {
        "attached": True,
        "gate": "task_complete_attach_gate",
        "host": args.host,
        "task": args.task,
        "step": COMPLETE_STEP,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    try:
        os.makedirs(os.path.dirname(ATTACHED_LOG), exist_ok=True)
        with open(ATTACHED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "gate": "task_complete_attach_gate",
                "host": args.host,
                "task": args.task,
                "step": COMPLETE_STEP,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0


if __name__ == "__main__":
    sys.exit(main())
