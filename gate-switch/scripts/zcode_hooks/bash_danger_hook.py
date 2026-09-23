#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PreToolUse(Bash) hook：danger_cmd 事前闸机械化（2026-08-29）。

提取 Bash 命令原文落盘临时文件，扳 danger_cmd_gate.json：
- 掷点 A（exit 0 + throw=A）→ exit 0 放行；
- 掷点 B → exit 2 阻断（PreToolUse deny），原因写 stderr；
- 脚本/解析故障 → exit 0 放行并留痕（fail-open，仅对显式 B 阻断）。

2026-09-06 用户裁定增补：危险命令对子代理照判 B、不豁免；仅在 B 阻断文案后
追加一行提示——检测到子代理运行窗口（~/.agents/logs/zcode_subagent_marker.json
count>0 且 expires_at>now）时，指引回报母体经用户批准后由母体执行。
标记文件缺失/解析失败/过期一律按窗口关闭，不炸主流程；fail-open 语义不动。
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

GATE = os.path.expanduser(
    "~/.agents/skills/gate-switch/scripts/gate_switch.py")
SPEC = os.path.expanduser(
    "~/.agents/skills/gate-switch/specs/danger_cmd_gate.json")
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
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return 0
    cmdfile = None
    try:
        fd, cmdfile = tempfile.mkstemp(prefix="danger_cmd_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(command)
        proc = subprocess.run(
            ["python3", GATE, "--spec", SPEC, "--set", "cmdfile=" + cmdfile],
            capture_output=True, timeout=30, text=True)
        data = json.loads(proc.stdout)
    except Exception as e:
        log("bash_danger_hook ERROR: %r" % e)
        return 0
    finally:
        if cmdfile:
            try:
                os.unlink(cmdfile)
            except OSError:
                pass
    throw = data.get("throw")
    if throw == "A" or proc.returncode == 0:
        return 0
    reason = data.get("directive") or json.dumps(
        data.get("violations") or data, ensure_ascii=False)[:800]
    log("bash_danger_hook BLOCK: %s" % reason)
    sys.stderr.write("[danger_cmd 事前闸] 掷点 B 阻断：%s\n" % reason)
    if marker_window_open():
        sys.stderr.write(
            "（检测到子代理运行窗口：删除/危险命令一律母体执行，"
            "请回报母体、经用户批准后由母体执行）\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
