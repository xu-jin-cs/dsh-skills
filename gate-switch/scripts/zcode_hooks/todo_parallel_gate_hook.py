#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PostToolUse(TodoWrite) hook：并行闸机械扳动（2026-10-14 用户终裁·双闸触发原理调换）。

设计锚点（终裁口径）：
  - 清单新任务数 ≥2 才启动"可否并行"判定；=1 不扳、零噪声。
  - units=新任务数（机械取）；files=任务文本路径正则提取。
  - 无路径证据 → 轻量声明直出（2026-10-14 用户二次裁定：不调闸本体、零违规注入，
    依赖判断归模型——互不依赖/依赖已完成即可并行，否则串行；判定秒级）；
    有路径证据 → 机械扳 dispatch_switch 全链（units=新任务数，files=路径数）。
  - 销号/重发不重扳（独立 flip 台账，扳过的任务键不重扳——关5 教训：销号不重算）。
  - 闸本体 dispatch_switch 零改动：清单已落账，闸1 清单登记天然满足
    （zcode sqlite → session cache 物化先于 PostToolUse）。
  - PostToolUse 不可阻断：VIOLATION/CLARIFY 同样原文注入，照抄 directive 补正后人工重扳。
  - 子代理运行窗口（marker）内静默放行，不注入。

掷点结论以 additionalContext 注入，模型照抄 PARALLEL-GATE 声明执行；
每次扳动由 dispatch_switch 自身落 dispatch_switch.jsonl 留痕。
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time

DISPATCH_SWITCH = os.path.expanduser(
    "~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
MARKER = os.path.expanduser("~/.agents/logs/zcode_subagent_marker.json")
FLIP_SEAL_DIR = os.environ.get(
    "TODO_FLIP_SEAL_DIR",
    os.path.expanduser("~/.agents/logs/todo_flip_seal"),
)
# 边③互斥（2026-10-24，hooks_wiring_impl 判A）：激活工作流实例标记。
# assemble_stage_context 每次装配自动刷新（必经链路治理点）；freshness 2h，
# 过期/缺失/损坏一律按无编排照章掷点，不炸主流程。
WORKFLOW_MARKER = os.path.expanduser("~/.agents/logs/active_workflow_instance.json")
# 附身掷点去重（触发链风暴防线）：同 (files,units) 量纲窗口内只掷一次，跨路径共用账。
DEDUP_LOG = os.path.expanduser("~/.agents/logs/dispatch_dedup.jsonl")
DEDUP_WINDOW_SEC = int(os.environ.get("DISPATCH_DEDUP_WINDOW_SEC", "600"))


def workflow_active():
    """边③互斥：编排声明 > 会话掷点。激活工作流实例存在时，并行掷点降级为
    登记不裁定。依据 env WORKFLOW_INSTANCE_ID 或标记文件（2h 内新鲜）。"""
    if os.environ.get("WORKFLOW_INSTANCE_ID", "").strip():
        return "env:WORKFLOW_INSTANCE_ID"
    try:
        with open(WORKFLOW_MARKER, encoding="utf-8") as f:
            m = json.load(f)
        ts = datetime.datetime.fromisoformat(m.get("ts") or "")
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if m.get("instance_id") and \
                (datetime.datetime.now(datetime.timezone.utc) - ts) < datetime.timedelta(hours=2):
            return f"file:{m.get('instance_id')}"
    except Exception:
        pass
    return None


def dispatch_dedup_seen(key: str) -> bool:
    """同 (files,units) 量纲时间窗内只掷一次（与 attached_dispatch 共账共窗）。"""
    now = time.time()
    rows, seen = [], False
    try:
        with open(DEDUP_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if now - float(r.get("ts", 0)) <= DEDUP_WINDOW_SEC:
                    rows.append(r)
                    if r.get("key") == key:
                        seen = True
    except FileNotFoundError:
        pass
    except Exception:
        return False
    if not seen:
        rows.append({"ts": now, "key": key, "window_sec": DEDUP_WINDOW_SEC})
        try:
            with open(DEDUP_LOG, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return seen

FILE_TOKEN_RE = re.compile(r"(?:~|/|[\w.-]+/)[\w./~()-]*\.(?:py|md|json|jsonl|sh|js|ts|yaml|yml)")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def marker_window_open():
    """子代理运行窗口：标记文件 count>0 且 expires_at>now（与 precheck hook 同口径）。"""
    try:
        import datetime
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


def session_id() -> str:
    return os.environ.get("DSH_SESSION_ID", "").strip() or "default-session"


def normalize(t: str) -> str:
    return " ".join(t.strip().lower().split())


def load_flip_seen(session: str) -> set:
    path = os.path.join(FLIP_SEAL_DIR, f"{session}.jsonl")
    seen = set()
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line)["task_key"])
                except Exception:
                    continue
    return seen


def seal_flip(session: str, keys: list) -> None:
    try:
        os.makedirs(FLIP_SEAL_DIR, exist_ok=True)
        with open(os.path.join(FLIP_SEAL_DIR, f"{session}.jsonl"), "a", encoding="utf-8") as f:
            for k in keys:
                f.write(json.dumps({"task_key": k}, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 台账写失败不阻断


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    if marker_window_open():
        log("todo_parallel_gate_hook SKIP: via=marker_window")
        return 0
    tool_input = payload.get("tool_input") or {}
    todos = tool_input.get("todos")
    if not isinstance(todos, list) or not todos:
        return 0
    contents = []
    for t in todos:
        if isinstance(t, dict):
            contents.append(str(t.get("content") or t.get("title") or ""))
        else:
            contents.append(str(t))
    contents = [c for c in contents if c]
    if not contents:
        return 0

    session = session_id()
    seen = load_flip_seen(session)
    new_pairs = [(normalize(c), c) for c in contents]
    new_tasks = [c for k, c in new_pairs if k and k not in seen]
    if len(new_tasks) < 2:
        return 0  # 新任务 <2 不启动并行判定（用户终裁）；销号/重发天然被台账滤掉

    units = len(new_tasks)
    blob = "\n".join(new_tasks)
    path_hits = set(FILE_TOKEN_RE.findall(blob))

    if not path_hits:
        # 轻量声明（2026-10-14 用户二次裁定）：无文件证据不调闸本体、零违规注入；
        # 依赖判断归模型：互不依赖/依赖已完成 → 可并行扇出；有未完成依赖 → 串行。
        seal_flip(session, [k for k, _ in new_pairs if k])
        try:
            with open(os.path.expanduser("~/.agents/logs/dispatch_switch.jsonl"),
                      "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(timespec="seconds"),
                    "verdict": "LIGHT", "units": units, "files": 0,
                    "session": session, "via": "todo_parallel_gate_hook"},
                    ensure_ascii=False) + "\n")
        except Exception:
            pass
        ctx = (f"[并行闸·轻量声明] 新任务 {units} 个，无文件路径证据。"
               "依赖判断归模型：互不依赖或依赖已完成 → 可并行（主agent执行，清单并行显示，"
               "不 spawn 子智能体）；有未完成依赖 → 串行。"
               "一句话说明判定即可，零阻断零强制。")
        print(json.dumps({"additionalContext": ctx}, ensure_ascii=False))
        return 0

    files = len(path_hits)

    # 边③互斥（2026-10-24）：激活工作流实例 → 编排已声明并行结构，
    # 会话掷点降级为登记不裁定（编排声明 > 会话闸）。
    orch = workflow_active()
    if orch:
        log(f"todo_parallel_gate_hook SKIP dispatch: via=orchestrated({orch}) units={units} files={files}")
        try:
            with open(os.path.expanduser("~/.agents/logs/dispatch_switch.jsonl"),
                      "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(timespec="seconds"),
                    "verdict": "ORCHESTRATED_SKIP", "units": units, "files": files,
                    "orch": orch, "session": session, "via": "todo_parallel_gate_hook"},
                    ensure_ascii=False) + "\n")
        except Exception:
            pass
        seal_flip(session, [k for k, _ in new_pairs if k])
        return 0

    # 附身掷点去重（触发链风暴防线）：窗口内同量纲已掷 → 跳过（不 seal，
    # 窗口过期后的重发仍可正常掷点）。
    dedup_key = hashlib.sha256(f"{files}|{units}".encode()).hexdigest()[:16]
    if dispatch_dedup_seen(dedup_key):
        log(f"todo_parallel_gate_hook SKIP dispatch: via=dedup key={dedup_key}")
        return 0

    try:
        proc = subprocess.run(
            [sys.executable, DISPATCH_SWITCH,
             "--files", str(files), "--units", str(units),
             "--desc", f"PostToolUse 机械扳：{len(contents)} 总/{units} 新"],
            capture_output=True, timeout=20, text=True)
        raw = (proc.stdout or "").strip()
        verdict = json.loads(raw) if raw else {"verdict": "NO_OUTPUT", "exit": proc.returncode}
    except Exception as e:
        log("todo_parallel_gate_hook ERROR: %r" % e)
        return 0

    seal_flip(session, [k for k, _ in new_pairs if k])

    gate_decl = verdict.get("gate_declaration")
    brief = {
        "verdict": verdict.get("verdict"),
        "throw": verdict.get("throw"),
        "mechanism": verdict.get("mechanism"),
        "fanout": verdict.get("fanout"),
        "scale": verdict.get("scale"),
        "gate_declaration": gate_decl,
        "directive": verdict.get("directive"),
        "clarify": verdict.get("clarify"),
        "violations": [r for r in verdict.get("reasons", []) if "违规" in str(r)] or None,
        "inputs": {"units": units, "files": files, "total_todos": len(contents)},
    }
    ctx = ("[并行闸·PostToolUse 机械扳动（2026-10-14 用户终裁）]\n"
           + json.dumps(brief, ensure_ascii=False, indent=2)
           + "\n照抄 gate_declaration 并执行 directive；并行/串行判定不影响任务分解（两独立维度）；"
             "耦合/依赖语义钩子不可知——知情时人工重扳 dispatch_switch --coupled --dep-reason 修正。")
    print(json.dumps({"additionalContext": ctx}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
