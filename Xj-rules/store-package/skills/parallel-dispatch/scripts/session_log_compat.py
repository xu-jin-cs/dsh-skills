#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话日志双格式兼容层（旧版 zstd / Kimi Code wire.jsonl）。

2026-08-24 Kimi Code 迁移适配：parallel-dispatch 的 dispatch_switch.py /
fanout_seal.py 原只认 旧版 会话日志，本模块统一两种格式，上游脚本只消费
归一化事件流，不再关心底层格式。

旧版 格式（保留兼容）：
  - 路径 ~/.kimi-code/sessions/*/*/session.jsonl.zstd（zstd 压缩）
  - 事件 "type":"turn/start"（time=ms）/ "todo/write"（data.todos，status
    completed）/ "tool/call"（data.name + callId + time）/ "tool/result"
  - 扇出工具名：subagent / subagent_fork / workflow
  - 子分身 id 从 tool/result 文本 "started subagent <id>" 提取

Kimi Code 格式：
  - 路径 ~/.kimi-code/sessions/wd_*/session_*/agents/<agent>/wire.jsonl
    （纯文本 JSONL，母线固定 agents/main/wire.jsonl）
  - turn 起点 {"type":"turn.prompt","time":<ms>}
  - 工具调用/结果 {"type":"context.append_loop_event","time":<ms>,
    "event":{"type":"tool.call"|"tool.result","name":...,"toolCallId":...,
    "args":{...}}}
  - todo 工具 TodoList：args.todos=[{"title":..,"status":"pending|
    in_progress|done"}]（归一化为 content/status=completed）
  - 扇出工具名：Agent / AgentSwarm；子分身日志为同 session 目录下
    agents/<id>/wire.jsonl（目录扫描获得，无需解析结果文本）

归一化事件 dict：
  {"kind": "turn_start"|"todo_write"|"fanout_call"|"tool_result",
   "time_ms": int|None, "todos": [...], "call_id": str|None,
   "name": str|None, "child_id": str|None}
"""
import glob
import json
import os
import subprocess
import time

SESSIONS_GLOB = os.path.expanduser("~/.kimi-code/sessions/*/*/session.jsonl.zstd")
KIMI_SESSIONS_GLOB = os.path.expanduser(
    "~/.kimi-code/sessions/*/*/agents/main/wire.jsonl")

LEGACY_FANOUT_TOOLS = ("subagent", "subagent_fork", "workflow")
KIMI_FANOUT_TOOLS = ("Agent", "AgentSwarm")
KIMI_TODO_TOOL = "TodoList"


def is_kimi_log(path):
    return ".kimi-code" in (path or "")


def resolve_session_log(session_log=None, fresh_seconds=900):
    """定位当前会话日志，返回 (path, source)；无法定位返回 (None, None)。

    权威顺序：① 显式指定；② AGENT_SESSION_JSONL 环境变量；③ 旧版 + Kimi 两个
    glob 中取活跃窗口内 mtime 最新者（降级启发式，可能受并行窗口干扰）。
    """
    if session_log:
        return session_log, "arg"
    env_path = os.environ.get("AGENT_SESSION_JSONL")
    if env_path and os.path.isfile(env_path):
        return env_path, "env"
    now = time.time()
    best = None
    for pattern in (SESSIONS_GLOB, KIMI_SESSIONS_GLOB):
        for path in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if now - mtime > fresh_seconds:
                continue
            if best is None or mtime > best[1]:
                best = (path, mtime)
    return (best[0], "mtime-heuristic") if best else (None, None)


def read_session_lines(path):
    """读取会话日志为行列表；失败（解压/IO）返回 None。"""
    if path.endswith(".zstd"):
        try:
            proc = subprocess.run(["zstd", "-dc", path],
                                  capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace").splitlines()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return None


def _normalize_kimi(raw, obj):
    """Kimi Code wire.jsonl 行 → 归一化事件。"""
    t = obj.get("type")
    if t == "turn.prompt":
        return {"kind": "turn_start", "time_ms": obj.get("time")}
    if t != "context.append_loop_event":
        return None
    ev = obj.get("event") or {}
    et = ev.get("type")
    name = ev.get("name")
    time_ms = obj.get("time")
    if et == "tool.call":
        if name == KIMI_TODO_TOOL:
            todos = (ev.get("args") or {}).get("todos")
            if isinstance(todos, list):
                norm = [{"content": x.get("title", "?"),
                         "status": "completed" if x.get("status") == "done"
                         else x.get("status")}
                        for x in todos if isinstance(x, dict)]
                return {"kind": "todo_write", "time_ms": time_ms,
                        "todos": norm}
            return None
        if name in KIMI_FANOUT_TOOLS:
            return {"kind": "fanout_call", "time_ms": time_ms,
                    "call_id": ev.get("toolCallId"), "name": name}
        return None
    if et == "tool.result":
        return {"kind": "tool_result", "time_ms": time_ms,
                "call_id": ev.get("toolCallId")}
    return None


def _normalize_legacy(raw, obj):
    """旧版 session.jsonl 行 → 归一化事件。"""
    t = obj.get("type")
    if t == "turn/start":
        return {"kind": "turn_start", "time_ms": obj.get("time")}
    if t == "todo/write":
        todos = obj.get("data", {}).get("todos")
        if isinstance(todos, list):
            return {"kind": "todo_write", "time_ms": obj.get("time"),
                    "todos": todos}
        return None
    if t == "tool/call":
        data = obj.get("data", {})
        name = data.get("name")
        if name in LEGACY_FANOUT_TOOLS:
            return {"kind": "fanout_call", "time_ms": obj.get("time"),
                    "call_id": data.get("callId"), "name": name}
        return None
    if t == "tool/result":
        data = obj.get("data", {})
        ev = {"kind": "tool_result", "time_ms": obj.get("time"),
              "call_id": data.get("callId") or data_call_id(raw)}
        if "started subagent " in raw:
            i = raw.find("started subagent ") + len("started subagent ")
            j = i
            while j < len(raw) and raw[j] in "0123456789abcdef-":
                j += 1
            if j - i >= 8:
                ev["child_id"] = raw[i:j]
        return ev
    return None


def data_call_id(raw):
    i = raw.find('"callId":"')
    if i == -1:
        return None
    j = raw.find('"', i + 10)
    return raw[i + 10:j] if j != -1 else None


def iter_events(lines, kimi):
    """对行列表产出归一化事件（粗过滤先行，避免全量 json.loads）。

    预过滤用裸事件名（不带 "type": 前缀），兼容带空格/紧凑两种 JSON 序列化。
    """
    tokens = ("turn.prompt", "context.append_loop_event") if kimi else (
        "turn/start", "todo/write", "tool/call", "tool/result")
    for raw in lines:
        if not any(tok in raw for tok in tokens):
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ev = _normalize_kimi(raw, obj) if kimi else _normalize_legacy(raw, obj)
        if ev:
            yield ev


def kimi_child_wires(session_log_path, since_ms=None):
    """Kimi 模式：列出同 session 目录下除 main 外的子分身 wire.jsonl。

    返回 [(child_id, wire_path)]；since_ms 提供时按 mtime 过滤本 turn 新生。
    """
    agents_dir = os.path.dirname(os.path.dirname(session_log_path))
    out = []
    for wire in sorted(glob.glob(os.path.join(agents_dir, "*", "wire.jsonl"))):
        child = os.path.basename(os.path.dirname(wire))
        if child == "main":
            continue
        if since_ms is not None:
            try:
                if os.path.getmtime(wire) * 1000 < since_ms:
                    continue
            except OSError:
                continue
        out.append((child, wire))
    return out
