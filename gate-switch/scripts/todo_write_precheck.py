#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""todo_write_precheck.py — todo_write 前置附身闸（起始端变种，2026-08-25 用户裁定）。

对齐"todo_write 附身闸"：以前末尾追加完成步骤，本变种在【起始端】把 todo 清单可能要触发的规则扫一遍。
在调用 todo_write 前运行，机械提醒"调用前要做的事"。数据源=本次 todo 清单 + 会话已见台账。

提醒项：
  ① 清单含【新任务】 → 计划闸附身（attached_plan：新任务才触发、重发豁免）
  ② 出现【多任务/并行】→ 并行闸（PARALLEL-GATE：dispatch_switch + todo_write 先登记）
  ③ 新回合有【未完成 todo】→ 需重发 todo_write（面板 turn 级清零）
  ④ 若为【改造/机制/重构】→ 收益闸（REFORM-GATE）判 A 才动手

用法：
  python3 todo_write_precheck.py --tasks '["任务A","任务B"]' [--new-turn]

退出码：0=提醒已输出（非判定）。
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
PRECHECK_LOG = os.environ.get(
    "TODO_PRECHECK_LOG",
    os.path.expanduser("~/.agents/logs/todo_write_precheck.jsonl"),
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


def remind(text, task):
    print(f"  ☐ {text}")
    print(f"     ↳ {task}")


def main() -> int:
    ap = argparse.ArgumentParser(description="todo_write 前置提醒脚本")
    ap.add_argument("--tasks", required=True, help="本次 todo_write 任务清单（JSON 数组/逗号分隔）")
    ap.add_argument("--new-turn", action="store_true", help="标记为新回合（提示 todo 重发）")
    args = ap.parse_args()

    tasks = parse_tasks(args.tasks)
    session = session_id()
    seen = load_seen(session)
    keys = [normalize(t) for t in tasks]
    new_keys = [k for k in keys if k and k not in seen]

    print(f"todo_write 前置提醒（会话 {session}，共 {len(tasks)} 项任务）:")

    if new_keys:
        remind("清单含新任务 → 计划闸附身", "attached_plan 对新任务触发；重发（无新任务）豁免")
    else:
        print("  ✓ 无新任务（重发豁免，不重复附身计划闸）")

    # 并行/多任务启发：任务数>1 且含并行意图
    multi = any(k in " ".join(keys) for k in ("并行", "多任务", "扇出", "多个"))
    if len(keys) > 1 or multi:
        remind("多任务/并行 → 并行闸", "dispatch_switch（PARALLEL-GATE）+ todo_write 先登记，判定禁止手写")

    if args.new_turn:
        remind("新回合有未完成 todo → 重发", "todo_write 面板 turn 级清零，重发同步面板")

    if any(k in " ".join(keys) for k in ("改造", "重构", "机制", "规则")):
        remind("改造/机制/重构 → 收益闸", "REFORM-GATE 判 A 才动手，禁以'用户指令'跳闸")

    print("提示：照抄并执行命中项后再调用 todo_write；判定禁止手写。")

    # 留痕（事后审计闸核验"todo_write 前已触发 precheck"用）
    try:
        os.makedirs(os.path.dirname(PRECHECK_LOG), exist_ok=True)
        import datetime
        with open(PRECHECK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "session_id": session,
                "n_tasks": len(tasks),
                "n_new": len(new_keys),
                "new_turn": args.new_turn,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0


if __name__ == "__main__":
    sys.exit(main())
