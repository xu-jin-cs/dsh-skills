#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PostToolUse(TodoWrite) hook：并行闸机械扳动（2026-10-14 用户终裁·双闸触发原理调换）。

设计锚点（终裁口径）：
  - 清单新任务数 ≥2 才启动"可否并行"判定；=1 不扳、零噪声。
  - units=新任务数（机械取）；files=任务文本路径正则提取，提取不到兜底=1
    （无路径证据即无并行面，2026-10-14 REFORM/LOGIC 双闸判A修复；原兜底=任务数会把
    无路径串行任务误判成 N 文件并行面，强逼基线文件）；耦合语义钩子不可知，模型知情时人工重扳 --coupled/--dep-reason 修正。
  - 销号/重发不重扳（独立 flip 台账，扳过的任务键不重扳——关5 教训：销号不重算）。
  - 闸本体 dispatch_switch 零改动：清单已落账，闸1 清单登记天然满足
    （zcode sqlite → session cache 物化先于 PostToolUse）。
  - PostToolUse 不可阻断：VIOLATION/CLARIFY 同样原文注入，照抄 directive 补正后人工重扳。
  - 子代理运行窗口（marker）内静默放行，不注入。

掷点结论以 additionalContext 注入，模型照抄 PARALLEL-GATE 声明执行；
每次扳动由 dispatch_switch 自身落 dispatch_switch.jsonl 留痕。
"""
import json
import os
import re
import subprocess
import sys

DISPATCH_SWITCH = os.path.expanduser(
    "~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
MARKER = os.path.expanduser("~/.agents/logs/zcode_subagent_marker.json")
FLIP_SEAL_DIR = os.environ.get(
    "TODO_FLIP_SEAL_DIR",
    os.path.expanduser("~/.agents/logs/todo_flip_seal"),
)

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
    files = len(set(FILE_TOKEN_RE.findall(blob))) or 1  # 兜底=1：无路径证据即无并行面（2026-10-14 判A修复，原兜底=任务数会把串行步骤误判成并行面）

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
