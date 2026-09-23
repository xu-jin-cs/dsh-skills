#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PreToolUse(TodoWrite) hook：todo_write 前置附身闸机械化（2026-08-29）。

从钩子输入提取 TodoWrite 的 todos，跑 todo_write_precheck.py，提醒以
additionalContext 注入。永远 exit 0（提醒型闸，不阻塞）。

2026-09-06 用户裁定增补（problem_gate 判A，治子代理前置闸噪声）：
- 子代理运行窗口开启（~/.agents/logs/zcode_subagent_marker.json count>0 且
  expires_at>now）→ 静默放行 return 0，不注入 additionalContext，留痕
  via=marker_window；标记文件缺失/解析失败/过期一律按窗口关闭照章运行，
  不炸主流程。
- 已知取舍：窗口期内母体调用同获豁免（载荷无身份字段，系结构性上限）。
"""
import datetime
import json
import os
import subprocess
import sys

PRECHECK = os.path.expanduser(
    "~/.agents/skills/gate-switch/scripts/todo_write_precheck.py")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
MARKER = os.path.expanduser("~/.agents/logs/zcode_subagent_marker.json")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def marker_window_open():
    """子代理运行窗口：标记文件 count>0 且 expires_at>now。
    缺失/解析失败/过期一律按窗口关闭照章运行，不炸主流程。"""
    try:
        with open(MARKER, encoding="utf-8") as f:
            m = json.load(f)
        if int(m.get("count") or 0) <= 0:
            return False
        exp = datetime.datetime.fromisoformat(m.get("expires_at") or "")
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=datetime.timezone.utc)
        return exp > datetime.datetime.now(datetime.timezone.utc)
    except Exception:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    if marker_window_open():
        log("todo_precheck_hook SKIP: via=marker_window")
        return 0
    tool_input = payload.get("tool_input") or {}
    todos = tool_input.get("todos")
    if not isinstance(todos, list) or not todos:
        return 0
    lines = []
    for t in todos:
        if isinstance(t, dict):
            lines.append(str(t.get("content") or t.get("title") or ""))
        else:
            lines.append(str(t))
    tasks = "；".join(x for x in lines if x)
    if not tasks:
        return 0
    try:
        proc = subprocess.run(
            ["python3", PRECHECK, "--tasks", tasks],
            capture_output=True, timeout=20, text=True)
        out = (proc.stdout or "").strip()
    except Exception as e:
        log("todo_precheck_hook ERROR: %r" % e)
        return 0
    if not out:
        return 0
    print(json.dumps({
        "additionalContext": "[todo_write 前置闸·机械注入]\n" + out},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
