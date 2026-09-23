#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PreToolUse(Read|Grep|Glob) hook：查询闸焊点机械化
（2026-09-01 移植 dsh-trigger-auto 通道⑥ query_weld_hook，REFORM
zcode_gate_auto_align 判A）。

语义逐条对照 dsh 原版：
- 拦检索三件套（ZCode 工具名 Read/Grep/Glob）；
- 本 turn 无 dual_gates declare 留痕（dual_gates_audit.jsonl 内
  timestamp >= turnStart 的 declaration_gate_start，5s 容差）即事前硬阻断
  （exit 2）+ 扳闸指引；扳完重试穿透放行；
- turnStart 来源：prompt_scan_hook 写的 zcode_hooks_state.json
  last_prompt_ts；状态不可读时按无留痕照章阻断（与 dsh 一致）。
- 审计：阻断/放行留痕 ~/.agents/logs/zcode_query_weld.jsonl。

2026-09-06 用户裁定增补（problem_gate 判A，治子代理 Read 永拦死循环）：
- 放行依据①（最高优先，子代理运行窗口）：~/.agents/logs/zcode_subagent_marker.json
  count>0 且 expires_at>now → via="marker_window" 静默放行；标记文件缺失/
  解析失败/过期一律按窗口关闭照章运行，不炸主流程；
- 放行依据②（权威凭据）：declare 直写 state 的 last_declare_ts >= turnStart(-5s)
  即放行，不再只依赖审计日志反扫——子代理无独立 UserPromptSubmit 脉冲、
  declare 会话标识与焊接登记错位时，反扫原语永久落空；
- 审计反扫保留为兜底通道。三通道任一命中即放行，留痕带 via 标识。
- 已知取舍：窗口期内母体调用同获豁免（载荷无身份字段，系结构性上限）；
  原子代理继承分支（按 session_id 不一致穿透）已删除——子代理载荷
  session 会漂移成母体或陈旧会话，实证不可靠；run_in_background 场景降级为
  declare_stamp 兜底。
"""
import datetime
import json
import os
import sys

AUDIT = os.path.expanduser("~/.agents/logs/dual_gates_audit.jsonl")
STATE = os.path.expanduser("~/.agents/logs/zcode_hooks_state.json")
WELD_LOG = os.path.expanduser("~/.agents/logs/zcode_query_weld.jsonl")
MARKER = os.path.expanduser("~/.agents/logs/zcode_subagent_marker.json")
TAIL_BYTES = 16 * 1024
TOLERANCE_S = 5

GUIDANCE = (
    "[QUERY-WELD·事前阻断] 本 turn 首次检索（Read/Grep/Glob）前必须先扳声明闸：\n"
    "python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py declare "
    "--raw \"<用户输入原文>\" --session-id $DSH_SESSION_ID\n"
    "（is_query 续扳 query 闸——知识库优先；not_query 直接推进）"
    "扳完重试本操作即穿透放行。")


def log(event):
    try:
        event["ts"] = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        with open(WELD_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def turn_start(state):
    ts = state.get("last_prompt_ts")
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


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


def released_by_declare(state, ts):
    """权威焊放凭据：declare 直写的 last_declare_ts >= turnStart(-容差)。"""
    dts = state.get("last_declare_ts")
    if not dts:
        return False
    try:
        d = datetime.datetime.fromisoformat(dts)
    except Exception:
        return False
    if d.tzinfo is None and ts.tzinfo is not None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return (d - ts).total_seconds() >= -TOLERANCE_S


def declared_since(ts):
    """dual_gates_audit.jsonl 尾部找 timestamp>=ts 的 declaration_gate_start。"""
    if not os.path.isfile(AUDIT):
        return False
    try:
        with open(AUDIT, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            tail = f.read().decode("utf-8", "replace")
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event") != "declaration_gate_start":
                continue
            try:
                ev_ts = datetime.datetime.fromisoformat(ev.get("timestamp", ""))
            except Exception:
                continue
            if ev_ts.tzinfo is None and ts.tzinfo is not None:
                ev_ts = ev_ts.replace(tzinfo=datetime.timezone.utc)
            return (ev_ts - ts).total_seconds() >= -TOLERANCE_S
    except OSError:
        pass
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    tool = (payload.get("tool_name") or payload.get("toolName") or "")
    sid = payload.get("session_id") or payload.get("sessionId") or ""
    state = load_state()
    state_sid = state.get("session_id") or ""
    ts = turn_start(state)
    via = None
    if marker_window_open():
        via = "marker_window"  # 子代理运行窗口：纪律闸静默放行
    elif ts is not None and released_by_declare(state, ts):
        via = "declare_stamp"
    elif ts is not None and declared_since(ts):
        via = "audit_tail"
    ok = via is not None
    log({"event": "query_weld_pass" if ok else "query_weld_deny",
         "tool": tool, "turn_start": ts.isoformat() if ts else None,
         "via": via, "session_id": sid, "state_session_id": state_sid})
    if ok:
        return 0
    sys.stderr.write(GUIDANCE + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
