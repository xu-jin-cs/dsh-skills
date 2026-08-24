#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_todo_resend_audit.py — L2 todo_write 重发义务事后审计闸
（2026-08 REFORM-GATE 判立即改落地，框架块 ~/.agents/logs/reform-gate/2026-08-todo-resend-mechanism.md）

问题：DSH todos 投影是 turn 级生命周期（turn/start 清零），而 goal 续轮与子分身
完成通知（母体 idle 走 next-turn）都会开新 turn。清零后面板是否空，取决于新回合
有没有重发 todo_write——此前无任何约束，纯模型自觉（概率空间）。

本闸扫 DSH 会话事件日志，机械核验"重发义务"逐 turn 是否履行：

  T1 重发缺失：turn 开始时存在悬置的未完成清单（上一 todo/write 快照
     pending+in_progress>0，跨 turn 悬置直到重发或全部完成），且本 turn
     结束前无 todo/write → 违例。
     豁免（机械）：turn/end reason 为 aborted/interrupted（用户打断，无履行机会）；
     无悬置清单的 turn 无义务。

  T2 状态变迁未同步（2026-08-22 REFORM-GATE 判A落地，框架块
     ~/.agents/logs/reform_blocks/todo_t2_audit_20260822.md；事故：5 路分身已扇出
     running 但 todo 面板仍 pending，用户当场抓包）：turn 内含状态变迁类工具调用
     （subagent/subagent_fork/job_kill/interrupt_agent/send_message）而本 turn 内
     无 todo/write → 违例。豁免同 T1（aborted/interrupted）。

纯语义情形（"这条清单该不该继续"）不进违例清单，只认事件流 0/1 事实；
违例内容是否情有可原留复盘软层裁决。
退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 gate_todo_resend_audit.py [--session-log <path>]
"""
import argparse
import glob
import json
import os
import subprocess
import sys

DSH_SESSIONS_GLOB = os.path.expanduser("~/.dsh/sessions/*/*/session.jsonl.zstd")
EXEMPT_END_REASONS = {"aborted", "interrupted"}
# T2：状态变迁类工具调用（出现即负有"同 turn 重发 todo/write 同步面板"义务）
STATE_CHANGE_TOOLS = {"subagent", "subagent_fork", "job_kill", "interrupt_agent", "send_message"}


def resolve_session_log(explicit=None):
    if explicit:
        return explicit, "arg"
    env = os.environ.get("DSH_SESSION_JSONL")
    if env and os.path.exists(env):
        return env, "env"
    cands = sorted(glob.glob(DSH_SESSIONS_GLOB), key=os.path.getmtime, reverse=True)
    return (cands[0], "glob") if cands else (None, None)


def read_events(path):
    try:
        proc = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=120)
        raw = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None
    events = []
    for line in raw.splitlines():
        if '"type"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        events.append((obj.get("type"), obj.get("data", {})))
    return events


def audit(events):
    """逐事件扫描，返回 (violations, stats)。"""
    outstanding = False   # 悬置的未完成清单（跨 turn 状态，重发或全完成后解除）
    obligation = False    # 本 turn 是否负有重发义务（T1）
    satisfied = False     # 本 turn 是否已重发
    state_changed = False  # 本 turn 是否含状态变迁类工具调用（T2）
    cur_turn = None
    violations = []
    stats = {"turns": 0, "obligation_turns": 0, "exempt_turns": 0, "todo_writes": 0,
             "state_change_turns": 0}
    for t, data in events:
        if t == "turn/start":
            cur_turn = data.get("turn")
            stats["turns"] += 1
            obligation = outstanding
            satisfied = False
            state_changed = False
            if obligation:
                stats["obligation_turns"] += 1
        elif t == "todo/write":
            stats["todo_writes"] += 1
            todos = data.get("todos") or []
            outstanding = any(
                isinstance(x, dict) and x.get("status") in ("pending", "in_progress")
                for x in todos
            )
            if cur_turn is not None:
                satisfied = True
        elif t == "tool/call":
            if data.get("name") in STATE_CHANGE_TOOLS and cur_turn is not None:
                if not state_changed:
                    stats["state_change_turns"] += 1
                state_changed = True
        elif t == "turn/end":
            reason = data.get("reason") or {}
            kind = reason.get("kind") if isinstance(reason, dict) else None
            exempt = kind in EXEMPT_END_REASONS
            if obligation and not satisfied:
                if exempt:
                    stats["exempt_turns"] += 1
                else:
                    violations.append({
                        "code": "T1-RESEND-MISSING",
                        "turn": cur_turn,
                        "detail": f"turn {cur_turn} 开始时有悬置未完成清单，"
                                  f"但本 turn（end kind={kind}）内未重发 todo/write → 面板本回合空置",
                    })
            if state_changed and not satisfied:
                if exempt:
                    stats["exempt_turns"] += 1
                else:
                    violations.append({
                        "code": "T2-STATE-CHANGE-NO-SYNC",
                        "turn": cur_turn,
                        "detail": f"turn {cur_turn} 含状态变迁类工具调用"
                                  f"（{'/'.join(sorted(STATE_CHANGE_TOOLS))}），"
                                  f"但本 turn 内未重发 todo/write → 面板与实况脱节",
                    })
    return violations, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-log", default=None)
    args = ap.parse_args()

    path, source = resolve_session_log(args.session_log)
    if not path:
        print(json.dumps({"ok": False, "violations": [{"code": "T0-NO-SESSION",
              "detail": "无法定位会话日志（--session-log 显式指定后重跑）"}]}, ensure_ascii=False, indent=2))
        print("TODO_RESEND_AUDIT_RESULT: FAIL dims=['INFRA']")
        return 2

    events = read_events(path)
    if events is None:
        print(json.dumps({"ok": False, "violations": [{"code": "T0-DECOMPRESS",
              "detail": f"会话日志解压失败: {path}"}]}, ensure_ascii=False, indent=2))
        print("TODO_RESEND_AUDIT_RESULT: FAIL dims=['INFRA']")
        return 2

    violations, stats = audit(events)
    out = {"ok": not violations, "session_log": path, "log_source": source,
           "stats": stats, "violations": violations}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        dims = sorted({v["code"].split("-")[0] for v in violations})
        print(f"TODO_RESEND_AUDIT_RESULT: FAIL dims={dims} count={len(violations)}")
        return 2
    print(f"TODO_RESEND_AUDIT_RESULT: PASS obligation_turns={stats['obligation_turns']} state_change_turns={stats['state_change_turns']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
