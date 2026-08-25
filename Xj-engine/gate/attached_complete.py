#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attached_complete.py — 任务完成步骤追加（[ATTACHED-COMPLETE] 声明 + 留痕）。

设计（2026-08-25 用户裁定）：不需要 hook——新建任务时，在任务末尾**追加一个执行步骤**：
`todo_write` 将该任务 `status` 置为 `"completed"`，任务执行到该步即完成、DSH 面板显示完成。

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

DECLARATION = (
    "[ATTACHED-COMPLETE] 任务末尾已追加完成步骤：执行到该步时，"
    "用 `todo_write` 将该任务 `status` 置为 `\"completed\"`，DSH 面板即显示完成；"
    "无需独立 hook、无需绕引擎（如需引擎权威记录可另行 `xj-engine complete`）。"
    "完成 = 追加的执行步骤 todo_write status:completed"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="任务完成 hook 种入（[ATTACHED-COMPLETE]）")
    ap.add_argument("--task", required=True, help="任务描述")
    ap.add_argument("--host", default="todo_write", help="调用方标识")
    args = ap.parse_args()

    out = {
        "attached": True,
        "hook": "attached_complete_hook",
        "mode": "complete",
        "host": args.host,
        "task": args.task,
        "declaration": DECLARATION,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    try:
        os.makedirs(os.path.dirname(ATTACHED_LOG), exist_ok=True)
        with open(ATTACHED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "hook": "attached_complete_hook",
                "mode": "complete",
                "host": args.host,
                "task": args.task,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0


if __name__ == "__main__":
    sys.exit(main())
