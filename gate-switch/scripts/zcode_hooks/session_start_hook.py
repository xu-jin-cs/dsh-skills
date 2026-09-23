#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode SessionStart hook：闸族加载自检 + 引擎健康 + 状态注入（2026-08-29）。

会话启动时把闸体系在线状态注入上下文（计划闸/并行闸/收益闸/查询闸/危险
命令闸的扳手位置与当前可用性），让模型从第一条消息起就知道闸已机械在岗，
不再依赖"记得去扳"。同时扳 engine_health 闸（离线=提示先启动引擎）。
永远 exit 0（注入型 hook，故障静默留痕不阻塞会话）。
"""
import json
import os
import subprocess
import sys

GS = os.path.expanduser("~/.agents/skills/gate-switch")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _engine_verdict() -> str:
    try:
        proc = subprocess.run(
            ["python3", GS + "/scripts/gate_switch.py", "--spec",
             GS + "/specs/engine_health.json"],
            capture_output=True, timeout=30, text=True)
        data = json.loads(proc.stdout)
        throw = data.get("throw", "?")
        if throw == "A":
            return "engine 在线（engine_health 判 A）"
        return "engine 离线（engine_health 判 B）——流程启动前需先拉起"
    except Exception as e:
        log("session_start_hook engine check ERROR: %r" % e)
        return "engine 健康检查执行失败（留痕）"


def _gate_roster() -> list:
    rows = []
    checks = [
        ("声明闸（trigger_signal_scan）",
         GS + "/scripts/trigger_signal_scan.py"),
        ("计划闸（plan_select）",
         os.path.expanduser("~/.agents/skills/plan-select/scripts/plan_select.py")),
        ("并行闸（dispatch_switch）",
         os.path.expanduser("~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py")),
        ("收益闸（reform_gate spec）", GS + "/specs/reform_gate.json"),
        ("查询闸（dual_gates declare）",
         os.path.expanduser("~/.agents/skills/dual-gates/scripts/dual_gates.py")),
        ("危险命令事前闸（danger_cmd_gate spec）",
         GS + "/specs/danger_cmd_gate.json"),
        ("todo 前置闸（todo_write_precheck）",
         GS + "/scripts/todo_write_precheck.py"),
    ]
    for name, path in checks:
        rows.append((name, os.path.isfile(path)))
    return rows


def main():
    # stdin 有 payload 也无需消费；本 hook 只做状态注入
    try:
        sys.stdin.read()
    except Exception:
        pass
    roster = _gate_roster()
    missing = [n for n, ok in roster if not ok]
    lines = ["[闸体系·SessionStart 加载自检]"]
    if missing:
        lines.append("⚠️ 缺失扳手：" + "、".join(missing) + "（对应闸不可用，须先修复）")
    else:
        lines.append("✅ 全部扳手在位：声明闸 / 计划闸 / 并行闸 / 收益闸 / 查询闸 / 危险命令事前闸 / todo 前置闸")
    lines.append("本会话机械触发点：每条用户输入→声明闸扫描注入；TodoWrite→前置闸；Bash→危险命令事前闸（判B阻断）。")
    lines.append("命中信号时必须照抄扳闸（计划闸 plan_select / 并行闸 dispatch_switch / 收益闸 reform_gate / 查询闸 dual_gates），判定禁止手写。")
    lines.append(_engine_verdict())
    print(json.dumps({"additionalContext": "\n".join(lines)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
