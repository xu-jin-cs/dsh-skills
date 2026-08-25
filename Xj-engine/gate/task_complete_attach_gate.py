#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_complete_attach_gate.py — 任务完成 hook 种入触发钩子（todo_write 挂点）。

触发契约（2026-08-25，对齐 attached_plan_hook 挂点）：
  挂点  = todo_write 节点，插件通道⑤侧调用；
  触发  = 本次 todo_write 清单含【新任务】才触发（种入完成 hook）；
  豁免  = 重发（无新任务）豁免，不重复种入。

逻辑：
  - 按会话维护"已见任务 id"台账 SEAL_DIR/<session>.jsonl；
  - 入参 --tasks 为本次 todo_write 任务清单（JSON 数组或逗号分隔串）；
  - new = 本次清单 - 已见；有 new → 逐个种入完成 hook（attached_complete.py）并记账；
  - 无 new（重发）→ 豁免，不种入。

路径可配置：TODO_SEAL_DIR（台账目录）/ ATTACH_COMPLETE_SCRIPT（种入脚本）。
退出码：0=A（已种入 或 重发豁免）；非 0=异常。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SEAL_DIR = os.environ.get(
    "TODO_SEAL_DIR",
    os.path.expanduser("~/.agents/logs/todo_seal"),
)
ATTACH_SCRIPT = os.environ.get(
    "ATTACH_COMPLETE_SCRIPT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "attached_complete.py"),
)


def session_id() -> str:
    return os.environ.get("DSH_SESSION_ID", "").strip() or "default-session"


def load_seen(session: str) -> set:
    path = os.path.join(SEAL_DIR, f"{session}.jsonl")
    seen = set()
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line)["task_key"])
                except Exception:
                    continue
    return seen


def append_seen(session: str, entries: list[str]) -> None:
    os.makedirs(SEAL_DIR, exist_ok=True)
    path = os.path.join(SEAL_DIR, f"{session}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for k in entries:
            f.write(json.dumps({"task_key": k}, ensure_ascii=False) + "\n")


def normalize(t: str) -> str:
    return " ".join(t.strip().lower().split())


def parse_tasks(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return [t for t in raw.split(",") if t.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="task_complete_plant_gate 附身触发（todo_write 挂点）")
    ap.add_argument("--tasks", required=True, help="本次 todo_write 任务清单（JSON 数组或逗号分隔）")
    args = ap.parse_args()

    session = session_id()
    seen = load_seen(session)
    keys = [normalize(t) for t in parse_tasks(args.tasks)]

    new_keys = [k for k in keys if k and k not in seen]
    if not new_keys:
        print("EXEMPT: 本次 todo_write 无新任务（重发豁免），不重复种入完成 hook")
        return 0

    for k in new_keys:
        os.system(f'python3 {ATTACH_SCRIPT} --task "{k}"')

    append_seen(session, new_keys)
    print(f"A: 种入 {len(new_keys)} 个新任务的完成 hook: {', '.join(new_keys)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
