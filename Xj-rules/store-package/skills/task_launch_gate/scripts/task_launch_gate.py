#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
task_launch_gate.py — 会话任务版·循环熔断闸（2026-08-20 裁定，REFORM-GATE 判A）

每个会话独立维护"任务版"（~/.agents/logs/task_launch/<session_id>.jsonl）：
  - record  每次任务发起前调用：同会话同任务累计发起 > max-launch(3)（即第 4 次）
            → 判 B 禁止加入并上报用户决定；否则追加本条约 A。
  - status  查看当前会话任务版（供上报/复盘）。
  - clear   用户触发"复盘"动作那一刻调用，清空当前会话任务版。
会话身份优先取环境变量 AGENT_SESSION_ID（本会话自动获知，无需手传）。
任务签名由调用方在触发点归一化传入 --task（命令/目标签名，去超时/路径差异）。

四态退出码：0=A 放行 / 2=B 熔断 / 3=CLARIFY / 4=VIOLATION。
"""
import argparse
import datetime
import json
import os
import re
import sys

LOG_ROOT = os.path.expanduser("~/.agents/logs/task_launch")


def session_id_from_env():
    return os.environ.get("AGENT_SESSION_ID", "").strip()


def normalize_task(task):
    """归一化任务签名：转小写、统一空白、去首尾，去掉 --key=value / --v 型参数差异。"""
    if not task:
        return ""
    t = task.strip().lower()
    # 去掉常见的 flag 值，保留命令+目标主体
    t = re.sub(r"--[a-z][a-z0-9-]*\s*=\s*\S+", "", t)
    t = re.sub(r"-{1,2}[a-z][a-z0-9-]*\s+\S+", "", t)
    t = re.sub(r"['\"`]", "", t)
    t = re.sub(r"\s+", ".", t.strip(" ."))
    return t


def ledger_path(session_id):
    if not re.match(r"^[A-Za-z0-9_-]+$", session_id):
        raise ValueError(f"非法的 session_id: {session_id!r}")
    return os.path.join(LOG_ROOT, session_id + ".jsonl")


def load(task, path):
    entries = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    key = normalize_task(task)
    return [e for e in entries if e.get("task_key") == key], entries


def append(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


def emit(verdict, code, **fields):
    fields["verdict"] = verdict
    print(json.dumps(fields, ensure_ascii=False, separators=(",", ":")))
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", default="")
    ap.add_argument("--task", default="")
    ap.add_argument("--action", required=True, choices=["record", "status", "clear"])
    ap.add_argument("--max-launch", type=int, default=3, help="同任务累计发起上限，超过即第4次起熔断")
    args = ap.parse_args()

    session = args.session_id or session_id_from_env()
    if not session:
        emit("CLARIFY", 3, reason="无法确定会话身份：无 AGENT_SESSION_ID 也未见 --session-id")
    try:
        path = ledger_path(session)
    except ValueError as e:
        emit("VIOLATION", 4, reason=str(e))

    ts = datetime.datetime.now().isoformat(timespec="seconds")

    if args.action == "clear":
        existed = os.path.isfile(path)
        if existed:
            os.remove(path)
        emit("A", 0, session_id=session, action="clear",
             cleared=existed, reason="复盘清空当前会话任务版")

    if args.action == "status":
        matches, all_e = load(args.task, path)
        counts = {}
        for e in all_e:
            k = e.get("task_key")
            counts[k] = counts.get(k, 0) + 1
        emit("A", 0, session_id=session, action="status",
             task=args.task, task_key=normalize_task(args.task),
             this_task_count=len(matches), all_tasks=counts)

    # record
    task_key = normalize_task(args.task)
    if not task_key:
        emit("VIOLATION", 4, reason="task 为空，无法归一化签名")
    matches, _ = load(args.task, path)
    n = len(matches)
    if n >= args.max_launch:
        emit("B", 2, session_id=session, action="record", task=args.task,
             task_key=task_key, count=n,
             reason=f"同会话任务已发起 {n} 次 >= {args.max_launch}，第 {n+1} 次触发熔断：禁止加入，上报用户决定")
    rec = {"ts": ts, "session_id": session, "task": args.task,
           "task_key": task_key, "count": n + 1}
    append(path, rec)
    emit("A", 0, session_id=session, action="record", task=args.task,
         task_key=task_key, count=n + 1, reason="记录本次发起，未触熔断")


if __name__ == "__main__":
    main()
