#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话日志多格式兼容层（DSH zstd / Kimi Code wire.jsonl / ZCode sqlite）。

2026-08-24 Kimi Code 迁移适配：parallel-dispatch 的 dispatch_switch.py /
fanout_seal.py 原只认 DSH 会话日志，本模块统一两种格式，上游脚本只消费
归一化事件流，不再关心底层格式。

2026-08-29 ZCode 迁移适配：ZCode 会话存于 sqlite（~/.zcode/cli/db/db.sqlite，
session/message/part/todo 四表），无 jsonl 文件。本模块按会话物化出 DSH 风格
JSONL 行缓存（~/.agents/logs/zcode_session_cache/<sess_id>.jsonl），上游零改动
复用 DSH 归一化路径。会话定位权威顺序：显式指定 > DSH_SESSION_JSONL >
ZCODE_SESSION_ID / CLAUDE_SESSION_ID（ZCode hooks 注入）> ZCode db 活跃会话 >
DSH/Kimi glob mtime 启发式。

DSH 格式（保留兼容）：
  - 路径 ~/.dsh/sessions/*/*/session.jsonl.zstd（zstd 压缩）
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
import re
import subprocess
import time

DSH_SESSIONS_GLOB = os.path.expanduser("~/.dsh/sessions/*/*/session.jsonl.zstd")
KIMI_SESSIONS_GLOB = os.path.expanduser(
    "~/.kimi-code/sessions/*/*/agents/main/wire.jsonl")

ZCODE_DB = os.path.expanduser("~/.zcode/cli/db/db.sqlite")
ZCODE_CACHE_DIR = os.path.expanduser("~/.agents/logs/zcode_session_cache")
ZCODE_FANOUT_TOOLS = ("Agent",)

DSH_FANOUT_TOOLS = ("subagent", "subagent_fork", "workflow")
KIMI_FANOUT_TOOLS = ("Agent", "AgentSwarm")
KIMI_TODO_TOOL = "TodoList"


def is_kimi_log(path):
    return ".kimi-code" in (path or "")


def _zcode_connect():
    """只读连接 ZCode 会话库；库不存在或不可读返回 None。"""
    if not os.path.isfile(ZCODE_DB):
        return None
    import sqlite3
    try:
        return sqlite3.connect("file:%s?mode=ro" % ZCODE_DB,
                               uri=True, timeout=3)
    except Exception:
        return None


def _zcode_pick_session(conn, fresh_seconds):
    """选定当前 ZCode 会话 id，返回 (session_id, source)。"""
    for var in ("ZCODE_SESSION_ID", "CLAUDE_SESSION_ID"):
        sid = os.environ.get(var)
        if sid and conn.execute(
                "select 1 from session where id=?", (sid,)).fetchone():
            return sid, "env:" + var
    row = conn.execute(
        "select id, time_updated from session where parent_id is null "
        "order by time_updated desc limit 1").fetchone()
    if row and time.time() * 1000 - row[1] <= fresh_seconds * 1000:
        return row[0], "zcode-db-active"
    return None, None


def materialize_zcode_session(fresh_seconds=900):
    """把当前 ZCode 会话从 sqlite 物化为 DSH 风格 JSONL 行缓存。

    返回 (path, source)；无法定位/物化返回 (None, None)。产出文件直接被
    read_session_lines + iter_events（DSH 归一化分支）消费，上游零改动。
    事件来源：turn/start ← user message；todo/write ← todo 表快照；
    tool/call ← part(type=tool) 且工具为 ZCODE_FANOUT_TOOLS；
    tool/result ← part(type=tool) 全部，Agent 结果行内嵌
    "started subagent <agent_uuid>"（子分身 id 权威来源：part output 的
    agentId 文本，兜底 session 表 parent_id 关联行）。
    """
    conn = _zcode_connect()
    if conn is None:
        return None, None
    try:
        sid, source = _zcode_pick_session(conn, fresh_seconds)
        if not sid:
            return None, None
        lines = []
        for (created,) in conn.execute(
                "select json_extract(data,'$.time.created') from message "
                "where session_id=? and json_extract(data,'$.role')='user' "
                "order by time_created", (sid,)):
            if created:
                lines.append(json.dumps({"type": "turn/start",
                                         "time": created}))
        todos = conn.execute(
            "select content, status, time_updated from todo "
            "where session_id=? order by position", (sid,)).fetchall()
        if todos:
            norm = [{"content": c, "status": s} for c, s, _ in todos]
            lines.append(json.dumps({
                "type": "todo/write",
                "time": max(t[2] for t in todos),
                "data": {"todos": norm}}))
        children = {}  # agent_uuid -> time_created(ms)
        for cid, tcreated in conn.execute(
                "select id, time_created from session where parent_id=?",
                (sid,)):
            m = re.search(r"(agent_[0-9a-fA-F-]{8,})", cid or "")
            if m:
                children[m.group(1)] = tcreated
        agent_re = re.compile(r"agent_[0-9a-fA-F-]{8,}")
        for pdata, tcreated, tupdated in conn.execute(
                "select data, time_created, time_updated from part "
                "where session_id=? and json_extract(data,'$.type')='tool' "
                "order by time_created", (sid,)):
            try:
                obj = json.loads(pdata)
            except json.JSONDecodeError:
                continue
            name = obj.get("tool")
            call_id = obj.get("callID")
            state = obj.get("state") or {}
            if name in ZCODE_FANOUT_TOOLS:
                lines.append(json.dumps({
                    "type": "tool/call", "time": tcreated,
                    "data": {"name": name, "callId": call_id}}))
            if state.get("status") not in ("completed", "error"):
                continue
            result = {"type": "tool/result", "time": tupdated,
                      "data": {"callId": call_id}}
            if name in ZCODE_FANOUT_TOOLS:
                out = state.get("output") or ""
                m = agent_re.search(out if isinstance(out, str) else "")
                child = m.group(0) if m else None
                if child is None and len(children) == 1:
                    child = next(iter(children))
                if child:
                    result["text"] = "started subagent " + child.replace(
                        "agent_", "")
            lines.append(json.dumps(result))
        if not lines:
            return None, None
        os.makedirs(ZCODE_CACHE_DIR, exist_ok=True)
        path = os.path.join(ZCODE_CACHE_DIR, sid + ".jsonl")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        return path, "zcode:" + source
    except Exception:
        return None, None
    finally:
        conn.close()


def resolve_session_log(session_log=None, fresh_seconds=900):
    """定位当前会话日志，返回 (path, source)；无法定位返回 (None, None)。

    权威顺序：① 显式指定；② DSH_SESSION_JSONL 环境变量；③ ZCode sqlite
    物化（env 会话 id 或活跃会话）；④ DSH + Kimi 两个 glob 中取活跃窗口
    内 mtime 最新者（降级启发式，可能受并行窗口干扰）。
    """
    if session_log:
        return session_log, "arg"
    env_path = os.environ.get("DSH_SESSION_JSONL")
    if env_path and os.path.isfile(env_path):
        return env_path, "env"
    zpath, zsource = materialize_zcode_session(fresh_seconds)
    if zpath:
        return zpath, zsource
    now = time.time()
    best = None
    for pattern in (DSH_SESSIONS_GLOB, KIMI_SESSIONS_GLOB):
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


def _normalize_dsh(raw, obj):
    """DSH session.jsonl 行 → 归一化事件。"""
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
        # ZCode 迁移适配：物化层按 ZCODE_FANOUT_TOOLS 写 Agent 的 tool/call 行，
        # 归一化侧必须同名表认领，否则 ZCode 扇出实证永远缺席（探针闸误拒）
        if name in DSH_FANOUT_TOOLS + ZCODE_FANOUT_TOOLS:
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
        ev = _normalize_kimi(raw, obj) if kimi else _normalize_dsh(raw, obj)
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
