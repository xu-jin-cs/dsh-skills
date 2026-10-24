#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode TodoWrite 钩子（pre/post 双模式，2026-10-24 接线激活）。

接线依据：AGENTS.md 2026-08-29 裁定——PreToolUse(TodoWrite)→前置闸、
PostToolUse(TodoWrite)→机械扳并行闸（此前仅文档声称，config.json 实测未接线）。

用法（config.json 两入口同文件不同参）：
  todo_hook.py pre   # PreToolUse：取 tool_input.todos 调 todo_write_precheck.py
  todo_hook.py post  # PostToolUse：units=新任务数、files=任务文本路径数、desc=任务文本
                     #             → 调 attached_dispatch.py（附身掷点，含编排感知+去重）

契约：恒 exit 0（两闸均为提醒/掷点非阻断）；故障 fail-open 留痕。
边②互斥（本仓 2026-10-24 裁定）：pre 模式检测到状态同步型更新时照常转 precheck，
由 precheck 自行识别跳审（识别逻辑在 todo_write_precheck.py，不在本层）。
"""
import json
import os
import re
import subprocess
import sys

PRECHECK = os.path.expanduser("~/.agents/skills/gate-switch/scripts/todo_write_precheck.py")
ATTACHED = os.path.expanduser("~/.agents/skills/gate-switch/scripts/attached_dispatch.py")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
PATH_RE = re.compile(r"(/Users/\S+|~/\S+|\./[^\s，,；;]+)")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        log(f"todo_hook ERROR spawn {cmd[1] if len(cmd) > 1 else cmd}: {e!r}")
        return None


def extract_todos(payload):
    ti = (payload.get("tool_input") or {}) if isinstance(payload, dict) else {}
    todos = ti.get("todos") or []
    contents = []
    for t in todos:
        if isinstance(t, dict):
            contents.append(str(t.get("content") or ""))
        else:
            contents.append(str(t))
    return [c for c in contents if c.strip()]


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        log(f"todo_hook[{mode}]: stdin 解析失败 {e!r}")
        return 0
    contents = extract_todos(payload if isinstance(payload, dict) else {})

    if mode == "pre" and contents:
        r = run(["python3", PRECHECK, "--tasks", json.dumps(contents, ensure_ascii=False)])
        if r and r.stdout.strip():
            print(r.stdout.strip())
    elif mode == "post" and contents:
        units = len(contents)
        paths = set()
        for c in contents:
            paths.update(m.group(0).rstrip(".,;，；）)」】") for m in PATH_RE.finditer(c))
        files = len(paths)
        desc = "；".join(contents)[:500]
        r = run(["python3", ATTACHED, "--files", str(max(files, 1)),
                 "--units", str(max(units, 1)), "--desc", desc,
                 "--host", "zcode_post_todowrite"])
        if r and r.stdout.strip():
            print(r.stdout.strip())
    else:
        log(f"todo_hook[{mode}]: 空 todos，跳过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
