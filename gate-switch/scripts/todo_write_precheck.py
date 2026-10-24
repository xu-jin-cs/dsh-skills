#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""todo_write_precheck.py — todo_write 前置附身闸（起始端变种，2026-08-25 用户裁定）。

对齐"todo_write 附身闸"：以前末尾追加完成步骤，本变种在【起始端】把 todo 清单可能要触发的规则扫一遍。
在调用 todo_write 前运行，机械提醒"调用前要做的事"。数据源=本次 todo 清单 + 会话已见台账。

提醒项（2026-10-14 用户终裁·双闸触发原理调换：计划闸移出 TodoWrite 链改声明式+交付闸连带，
并行闸移 PostToolUse 钩子机械扳——本闸不再承担两闸提醒）：
  ① 新回合有【未完成 todo】→ 需重发 todo_write（面板 turn 级清零）
  ② 若为【改造/机制/重构】→ 收益闸（REFORM-GATE）判 A 才动手

用法：
  python3 todo_write_precheck.py --tasks '["任务A","任务B"]' [--new-turn]

退出码：0=提醒已输出（恒放行，不阻塞不打回）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
            out = []
            for x in data:
                if isinstance(x, dict):
                    out.append(str(x.get("content") or x.get("title") or ""))
                else:
                    out.append(str(x))
            return [t for t in out if t]
    except Exception:
        pass
    # 纯文本：分号优先（hook 层以 "；" 连接 content）；无分号才按逗号切
    if "；" in raw or ";" in raw:
        parts = re.split(r"[；;]", raw)
    else:
        parts = re.split(r"[，,]", raw)
    return [t for t in parts if t.strip()]


def remind(text, task):
    print(f"  ☐ {text}")
    print(f"     ↳ {task}")


# 边②互斥（2026-10-24，hooks_wiring_impl 判A）：状态同步型更新识别——
# 引擎/工作流进度镜像类 todo（[SYNC] 前缀、instance_id=/stage_id= 标记、
# 进度回写/状态同步字样）跳过新任务审查只留痕，防"进度回写被当新任务审查"噪声。
STATE_SYNC_RE = re.compile(r"\[SYNC\]|instance_id=|stage_id=|进度回写|状态同步")


def main() -> int:
    ap = argparse.ArgumentParser(description="todo_write 前置提醒脚本")
    ap.add_argument("--tasks", required=True, help="本次 todo_write 任务清单（JSON 数组/逗号分隔）")
    ap.add_argument("--new-turn", action="store_true", help="标记为新回合（提示 todo 重发）")
    args = ap.parse_args()

    tasks = parse_tasks(args.tasks)
    session = session_id()

    # 边②互斥（2026-10-24）：全部任务均为状态同步型 → 跳过审查只留痕
    if tasks and all(STATE_SYNC_RE.search(t) for t in tasks):
        print("[前置闸·状态同步] 检测到进度镜像更新（边②互斥），跳过新任务审查，仅留痕。")
        try:
            os.makedirs(SEAL_DIR, exist_ok=True)
            with open(os.path.join(SEAL_DIR, f"{session}.jsonl"), "a", encoding="utf-8") as f:
                for t in tasks:
                    f.write(json.dumps({"task_key": normalize(t)}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(PRECHECK_LOG), exist_ok=True)
            with open(PRECHECK_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                    "session_id": session, "n_tasks": len(tasks),
                    "via": "state_sync_skip",
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return 0

    seen = load_seen(session)
    keys = [normalize(t) for t in tasks]
    new_keys = [k for k in keys if k and k not in seen]

    print(f"todo_write 前置提醒（会话 {session}，共 {len(tasks)} 项任务）:")

    if args.new_turn:
        remind("新回合有未完成 todo → 重发", "todo_write 面板 turn 级清零，重发同步面板")

    if any(k in " ".join(keys) for k in ("改造", "重构", "机制", "规则")):
        remind("改造/机制/重构 → 收益闸", "REFORM-GATE 判 A 才动手，禁以'用户指令'跳闸")

    # seal 台账闭合（2026-10-13：原实现只读不写导致 seen 永空、重发豁免失效）——本次任务 keys 落台账
    try:
        os.makedirs(SEAL_DIR, exist_ok=True)
        with open(os.path.join(SEAL_DIR, f"{session}.jsonl"), "a", encoding="utf-8") as f:
            for k in keys:
                f.write(json.dumps({"task_key": k}, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 台账写失败不阻断

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
