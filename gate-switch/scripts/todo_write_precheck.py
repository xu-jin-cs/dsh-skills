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

退出码：0=提醒已输出/放行；2=阻断（fanout 判定留痕缺失——2026-10-13 升级，
REFORM-GATE 判A 块 todo_fanout_gate_20261013.md，用户裁定"并行闸放在 TodoWrite 之前，
任务分解功能移入并行闸内"：含新任务时必须先跑 task_fanout_plan.py 且判 A 留痕，
否则阻断 TodoWrite。重发/无新任务豁免 via=resend_exempt；留痕窗口 1800 秒）。
"""
from __future__ import annotations

import argparse
import datetime
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
FANOUT_MARKER_TTL = 1800  # 留痕有效窗口（秒）：跑完 fanout 到 TodoWrite 的合理间隔
FANOUT_SCRIPT = "~/.agents/skills/parallel-dispatch/scripts/task_fanout_plan.py"


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


def fanout_marker_ok(session: str) -> tuple[bool, str]:
    """fanout 留痕核验：文件存在 + verdict==A + ts 在窗口期内。
    缺失/解析失败/过期一律视为无留痕（DIM-032 读侧不炸）。返回 (是否放行, via/原因)。"""
    path = f"/tmp/fanout_plan_{session}.json"
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if rec.get("verdict") != "A":
            return False, "留痕 verdict != A（fanout 判定未通过）"
        ts = datetime.datetime.fromisoformat(rec.get("ts") or "")
        age = (datetime.datetime.now() - ts).total_seconds()
        if age > FANOUT_MARKER_TTL:
            return False, f"留痕过期（{int(age)}s > {FANOUT_MARKER_TTL}s）"
        return True, f"fresh_fanout_marker(width={rec.get('width')}, age={int(age)}s)"
    except Exception:
        return False, "无 fanout 留痕（task_fanout_plan.py 未跑或未判 A）"


def log_via(session: str, n_tasks: int, n_new: int, new_turn: bool, via: str) -> None:
    """统一留痕（DIM-033：放行/阻断带 via 通道，供事后审计回溯）。"""
    try:
        os.makedirs(os.path.dirname(PRECHECK_LOG), exist_ok=True)
        with open(PRECHECK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "session_id": session, "n_tasks": n_tasks, "n_new": n_new,
                "new_turn": new_turn, "via": via,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断


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

    fanout_via = "no_tasks"
    if new_keys:
        remind("清单含新任务 → 计划闸附身", "attached_plan 对新任务触发；重发（无新任务）豁免")
        ok, why = fanout_marker_ok(session)
        if not ok:
            print(f"  ✖ 阻断：{why}")
            print("  【fanout 前置判定缺失 · 阻断 TodoWrite】（2026-10-13 用户裁定：")
            print("   任务分解判定移入并行闸——新建任务前先判每个任务可拆性与多任务依赖并行）")
            print("  解除步骤：")
            print("  1. 构造任务清单 JSON：每任务必标 id / size(S·M·L·XL) / deps；")
            print("     无依赖显式写 deps:[] 并附 no_dep_reason")
            print(f"  2. 跑 python3 {FANOUT_SCRIPT} --tasks '<JSON>' 照抄输出（判 B 按 violations 修复）")
            print("  3. 判 A 留痕后重新 todo_write")
            log_via(session, len(tasks), len(new_keys), args.new_turn, f"blocked:{why}")
            return 2
        fanout_via = why
        print(f"  ✓ fanout 判定留痕核验通过（via={why}）——分解/并行判定已先行")
    else:
        print("  ✓ 无新任务（重发豁免，不重复附身计划闸）")
        fanout_via = "resend_exempt"

    # 并行/多任务启发：任务数>1 且含并行意图
    multi = any(k in " ".join(keys) for k in ("并行", "多任务", "扇出", "多个"))
    if len(keys) > 1 or multi:
        remind("多任务/并行 → 并行闸", "dispatch_switch（PARALLEL-GATE）+ todo_write 先登记，判定禁止手写")

    if args.new_turn:
        remind("新回合有未完成 todo → 重发", "todo_write 面板 turn 级清零，重发同步面板")

    if any(k in " ".join(keys) for k in ("改造", "重构", "机制", "规则")):
        remind("改造/机制/重构 → 收益闸", "REFORM-GATE 判 A 才动手，禁以'用户指令'跳闸")

    print("提示：照抄并执行命中项后再调用 todo_write；判定禁止手写。")

    # 留痕（事后审计闸核验"todo_write 前已触发 precheck"用；via 通道必填，DIM-033）
    log_via(session, len(tasks), len(new_keys), args.new_turn, fanout_via)
    return 0


if __name__ == "__main__":
    sys.exit(main())
