#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attached_complete.py — 任务完成 hook 种入（[ATTACHED-COMPLETE] 声明 + 留痕）。

设计（2026-08-25 用户裁定）：新建任务时把完成 hook 种入任务——任务完成时天然触发
task_complete_hook（`xj-engine complete`）→ task.complete 追加权威完成记录
（pending→completed + TASK_COMPLETE 审计），该记录即完成标记；无需完成附身闸。

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
    "[ATTACHED-COMPLETE] 本任务已种下完成 hook：任务完成时天然触发 "
    "`xj-engine complete --task-id <id> --evidence '<完成证据>'` → task.complete "
    "追加权威完成记录（pending→completed + TASK_COMPLETE 审计），该记录即完成标记；"
    "完成无需额外附身闸，hook 天然触发（不追加额外标记、无完成附身闸）"
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
