#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_first_audit.py — PLAN-FIRST-GATE 事后审计闸（2026-08-17 用户裁定：触发即强制执行）

裁定原文："先列步骤等你确认，这个是规则，提示词软约束，我要扳手，触发即强制执行"。
REFORM-GATE 块：~/.agents/logs/reform_gate_block_plan_first_gate_20260817.md（判 A）。

机械核验：扫 DSH 会话 jsonl，命中"问题/需求信号词"的用户消息之后，
助手首个执行类工具调用（bash/edit/write/subagent/subagent_fork/workflow/ralph）之前，
文本中必须出现步骤清单（编号列表/步骤声明）；缺失 → T1 违例。
纯问答 turn（无执行类工具调用）不违例。无钩子环境事前无法硬拦，
采用"事后必被查倒逼事前自觉"既定范式（同 first_push_audit）。

退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 plan_first_audit.py [--session-log <path>]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

DSH_SESSIONS_GLOB = os.path.expanduser("~/.dsh/sessions/*/*/session.jsonl.zstd")

# 问题/需求信号词（窄口径先上线，误报由复盘人工复核兜住）
SIGNAL_WORDS = [
    "出问题了", "还是有问题", "bug", "Bug", "BUG", "报错", "崩溃", "修复",
    "不对", "挂了", "干挂", "卡死", "查一下", "帮我查", "排查", "看看",
    "改一下", "改造", "优化", "帮我", "我要", "我要大批量", "集成", "放到",
    "看不出", "没反应", "没有显示", "没显示", "不生效", "卡住了",
]
# 免判前缀：系统通知类用户消息（背景子代理回执/系统提醒）不算用户诉求
EXEMPT_PREFIX = ("Background subagent", "<system-reminder>", "Current runtime context")
# 执行类工具（这些调用出现前必须有步骤清单）
EXEC_TOOLS = {"bash", "edit", "write", "subagent", "subagent_fork", "workflow", "ralph"}
# 步骤清单模式：显式规划声明（普通 markdown 列表不算，防闸变摆设）
PLAN_PATTERNS = [
    re.compile(r"步骤|清单|计划如下|方案如下|流程如下|先.{0,8}再|打算|按.{0,4}顺序"),
]


def resolve_session_log(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("DSH_SESSION_JSONL")
    if env and os.path.exists(env):
        return env
    cands = sorted(glob.glob(DSH_SESSIONS_GLOB), key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None


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
        t = obj.get("type")
        if t in ("user/message", "assistant/message", "tool/call"):
            events.append((t, obj.get("data", {}), obj.get("time", 0)))
    return events


def user_text(data):
    # 兼容两种事件形态：data.message.content 与 data.content
    msg = data.get("message") or data
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(i.get("text", "") for i in content
                        if isinstance(i, dict))
    return ""


def has_step_list(text):
    return any(p.search(text) for p in PLAN_PATTERNS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-log", default=None)
    args = ap.parse_args()

    path = resolve_session_log(args.session_log)
    if not path:
        print(json.dumps({"verdict": "B", "violations": ["无法定位会话 jsonl"]},
                         ensure_ascii=False))
        sys.exit(2)

    events = read_events(path)
    if events is None:
        print(json.dumps({"verdict": "B", "violations": [f"会话日志读取失败: {path}"]},
                         ensure_ascii=False))
        sys.exit(2)

    violations = []
    i = 0
    n = len(events)
    while i < n:
        t, data, ts = events[i]
        if t != "user/message":
            i += 1
            continue
        txt = user_text(data)
        if (not txt.strip()) or txt.startswith(EXEMPT_PREFIX):
            i += 1
            continue
        if not any(w in txt for w in SIGNAL_WORDS):
            i += 1
            continue
        # 命中信号：扫描后续助手 turn 直到下一个用户消息
        plan_found = False
        exec_tool = None
        j = i + 1
        while j < n:
            t2, data2, _ = events[j]
            if t2 == "user/message":
                break
            if t2 == "assistant/message":
                msg2 = data2.get("message") or data2
                for item in (msg2.get("content") or []):
                    if isinstance(item, dict) and item.get("type") == "text":
                        if has_step_list(item.get("text", "")):
                            plan_found = True
            if t2 == "tool/call" and data2.get("name") in EXEC_TOOLS:
                exec_tool = data2.get("name")
                break  # 只关心首个执行类调用
            j += 1
        if exec_tool and not plan_found:
            violations.append(
                f"T1 问题信号命中但首执「{exec_tool}」前无步骤清单：用户消息「{txt[:40]}…」"
            )
        i += 1

    verdict = "A" if not violations else "B"
    print(json.dumps({
        "verdict": verdict,
        "gate": "plan_first_audit",
        "session_log": path,
        "violations": violations,
        "directive": "全部合规" if verdict == "A" else "问题/需求 turn 必须先列步骤等确认再执行；违例进复盘",
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if verdict == "A" else 2)


if __name__ == "__main__":
    main()
