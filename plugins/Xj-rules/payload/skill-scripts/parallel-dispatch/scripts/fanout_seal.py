#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fanout_seal.py — 扇出收尾闸（2026-08-16 用户裁定"概率即扳手"原则，parallel-dispatch 配套）

概率点：掷点 A 之后，模型可能①只评估不执行（无真实扇出）②分身 settle 后漏销号
（任务清单残留 pending/in_progress，GUI 面板永远显示"进行中"）。两者原为软规则，
本闸机械化：终答前必须扳动，照抄输出。

校验（全部基于当前 turn 的会话日志实证 + 开关留痕）：
  1. 真扇出：本 turn 每有一次掷点 A 留痕，就必须存在 subagent/subagent_fork/workflow
     的 tool/call 事件；否则判"只评估不执行"。
  2. 全销号：本 turn 最后一次 todo/write 的清单必须全部 completed；
     残留 pending/in_progress 逐条列出。
  3. 基线阅读：本 turn 掷点 A 留痕携带的 --baseline 基线文件，本 turn 每个子分身
     的会话日志中必须出现其 basename 引用（read/grep/bash 等任何工具引用即算）；
     未读基线的分身逐个列出。治"各分身上下文不一致"（2026-08-16 裁定）。
  4. 顶层残渣 tripwire（2026-08-20 根源治理 v2，REFORM-GATE 判A）：项目顶层
     _partial_* / _gov_* 落盘产物必须为零——落盘路径按结果落盘制路径模板应指向
     .fanout/<ts>/ 暂存区或 archive/ 子目录；顶层出现即任务书违反路径模板。
     本项为兜底拦截，方案本体是暂存区约定（产物从诞生起不进顶层）。

退出码：0 = SEAL（放行终答）  3 = CLARIFY（会话日志不可定位/不可读）  4 = VIOLATION

用法：
  python3 fanout_seal.py                          # 自动定位当前会话（DSH_SESSION_JSONL 权威）
  python3 fanout_seal.py --session-log <路径>     # 显式指定会话日志
  python3 fanout_seal.py --project-root <路径>    # 顶层残渣扫描目标（缺省 cwd）
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import time

EXIT_SEAL, EXIT_CLARIFY, EXIT_VIOLATION = 0, 3, 4

DSH_SESSIONS_GLOB = os.path.expanduser("~/.dsh/sessions/*/*/session.jsonl.zstd")
DEFAULT_SWITCH_LOG = os.path.expanduser("~/.agents/logs/dispatch_switch.jsonl")
FRESH_SECONDS = 900
FANOUT_TOOLS = ("subagent", "subagent_fork", "workflow")
TOP_RESIDUE_PATTERNS = ("_partial_*", "_gov_*")  # 顶层残渣 tripwire（校验4）


def resolve_session_log(session_log=None):
    """同 dispatch_switch：--session-log > DSH_SESSION_JSONL > mtime 启发式。"""
    if session_log:
        return session_log, "arg"
    env_path = os.environ.get("DSH_SESSION_JSONL")
    if env_path and os.path.isfile(env_path):
        return env_path, "env"
    now = time.time()
    best = None
    for path in glob.glob(DSH_SESSIONS_GLOB):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if now - mtime > FRESH_SECONDS:
            continue
        if best is None or mtime > best[1]:
            best = (path, mtime)
    return (best[0], "mtime-heuristic") if best else (None, None)


def scan_current_turn(path):
    """扫描会话日志，返回当前 turn 的实证切片；解压失败返回 None。

    切片内容：turn 起始时间（ms）、最终 todo 清单、扇出工具调用计数。
    todos 投影随 turn/start 清空（last-write-wins），只认最后一个 turn/start 之后。
    """
    try:
        proc = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    turn_start_ms = None
    todos = None
    fanout_calls = 0
    children = []
    for raw in proc.stdout.decode("utf-8", errors="replace").splitlines():
        if '"type":"turn/start"' in raw:
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            turn_start_ms = obj.get("time")
            todos = None
            fanout_calls = 0
            children = []
        elif '"type":"todo/write"' in raw:
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            data = obj.get("data", {}).get("todos")
            todos = data if isinstance(data, list) else None
        elif '"type":"tool/call"' in raw and any(f'"name":"{t}"' in raw for t in FANOUT_TOOLS):
            fanout_calls += 1
        elif '"type":"tool/result"' in raw and "started subagent " in raw:
            i = raw.find("started subagent ") + len("started subagent ")
            j = i
            while j < len(raw) and raw[j] in "0123456789abcdef-":
                j += 1
            if j - i >= 8:
                children.append(raw[i:j])
    return {"turn_start_ms": turn_start_ms, "todos": todos,
            "fanout_calls": fanout_calls, "children": children}


def collect_turn_a_throws(switch_log, turn_start_ms, session_id):
    """收集本 turn 的掷点 A 留痕（次数 + 携带的基线路径）。带 session 字段的留痕
    精确归属；无 session 字段的历史留痕按时间窗归入（过渡期兼容）。"""
    if turn_start_ms is None or not os.path.isfile(switch_log):
        return 0, []
    count = 0
    baselines = []
    with open(switch_log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("verdict") != "A":
                continue
            entry_session = entry.get("session")
            if entry_session is not None and session_id is not None and entry_session != session_id:
                continue
            ts = entry.get("ts")
            if not ts:
                continue
            try:
                entry_ms = datetime.datetime.fromisoformat(ts).timestamp() * 1000
            except ValueError:
                continue
            if entry_ms >= turn_start_ms:
                count += 1
                for b in entry.get("baseline") or []:
                    if b not in baselines:
                        baselines.append(b)
    return count, baselines


def check_baseline_reads(children, baselines, sessions_root):
    """校验每个子分身日志引用了至少一个基线文件（basename  substring 命中即算）。"""
    if not children or not baselines:
        return []
    names = [os.path.basename(b) for b in baselines]
    violations = []
    for child in children:
        matches = glob.glob(os.path.join(sessions_root, "*", child, "session.jsonl.zstd"))
        if not matches:
            violations.append(f"子分身 {child} 会话日志缺失，基线阅读无法核验")
            continue
        try:
            proc = subprocess.run(["zstd", "-dc", matches[0]], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            violations.append(f"子分身 {child} 会话日志解压失败，基线阅读无法核验")
            continue
        if proc.returncode != 0:
            violations.append(f"子分身 {child} 会话日志解压失败，基线阅读无法核验")
            continue
        text = proc.stdout.decode("utf-8", errors="replace")
        if not any(name in text for name in names):
            violations.append(f"子分身 {child} 全程未引用基线文件（{'、'.join(names)}）→ 上下文脱基线")
    return violations


def check_top_residue(project_root):
    """校验4 tripwire：项目顶层不得有 _partial_* / _gov_* 落盘残渣。
    返回 (残渣清单, 违例文本列表)。project_root 不存在或 None 时跳过。"""
    if not project_root or not os.path.isdir(project_root):
        return [], []
    residue = []
    for pat in TOP_RESIDUE_PATTERNS:
        residue.extend(
            p for p in glob.glob(os.path.join(project_root, pat))
            if os.path.isfile(p)
        )
    if not residue:
        return [], []
    names = "、".join(os.path.basename(p) for p in sorted(residue))
    return residue, [
        f"项目顶层检出落盘残渣 {len(residue)} 件（{names}）→ 违反结果落盘制路径模板"
        f"（应落 .fanout/<ts>/ 暂存区或 archive/ 子目录），收编后须归档/清场再重扳"
    ]


def seal(session_log=None, switch_log=DEFAULT_SWITCH_LOG, sessions_root=None, project_root=None):
    path, source = resolve_session_log(session_log)
    if path is None:
        return {
            "verdict": "CLARIFY",
            "reason": "无法定位当前 DSH 会话日志 → 用 --session-log 显式指定后重扳",
        }, EXIT_CLARIFY
    turn = scan_current_turn(path)
    if turn is None:
        return {
            "verdict": "CLARIFY",
            "reason": f"会话日志解压失败：{path}（需 zstd CLI 在 PATH 中）",
        }, EXIT_CLARIFY

    session_id = os.environ.get("DSH_SESSION_ID")
    a_throws, baselines = collect_turn_a_throws(switch_log, turn["turn_start_ms"], session_id)
    violations = []

    # ---- 校验 1：真扇出（禁止只评估不执行的机械牙齿）----
    if a_throws > 0 and turn["fanout_calls"] == 0:
        violations.append(
            f"本 turn 有 {a_throws} 次掷点 A 留痕，但会话日志无 subagent/subagent_fork/workflow "
            f"调用实证 → 只评估不执行"
        )

    # ---- 校验 2：全销号（禁止进度黑盒的机械牙齿）----
    todos = turn["todos"]
    todo_stats = None
    if todos is not None:
        incomplete = [t.get("content", "?") for t in todos
                      if isinstance(t, dict) and t.get("status") != "completed"]
        todo_stats = {"total": len(todos), "incomplete": len(incomplete)}
        if incomplete:
            violations.append(
                f"任务清单残留 {len(incomplete)}/{len(todos)} 条未销号：" + "；".join(incomplete)
            )

    # ---- 校验 3：基线阅读（禁止上下文脱基线的机械牙齿）----
    root = sessions_root or os.path.expanduser("~/.dsh/sessions")
    violations.extend(check_baseline_reads(turn["children"], baselines, root))

    # ---- 校验 4：顶层残渣 tripwire（2026-08-20 根源治理 v2）----
    residue, residue_violations = check_top_residue(project_root or os.getcwd())
    violations.extend(residue_violations)

    evidence = {
        "log": path,
        "log_source": source,
        "a_throws": a_throws,
        "fanout_calls": turn["fanout_calls"],
        "todos": todo_stats,
        "children": turn["children"],
        "baselines": baselines,
        "top_residue": [os.path.basename(p) for p in residue],
    }
    if violations:
        return {
            "verdict": "VIOLATION",
            "evidence": evidence,
            "violations": violations,
            "directive": "逐条整改后重扳本闸；全部通过（exit 0）才允许终答",
        }, EXIT_VIOLATION
    return {
        "verdict": "SEAL",
        "evidence": evidence,
        "directive": "收尾校验通过，允许终答",
    }, EXIT_SEAL


def main():
    ap = argparse.ArgumentParser(description="扇出收尾闸：真扇出 + 全销号的机械实证")
    ap.add_argument("--session-log", type=str, default=None,
                    help="显式指定当前会话 session.jsonl.zstd 路径（缺省 DSH_SESSION_JSONL/活跃启发式）")
    ap.add_argument("--switch-log", type=str, default=DEFAULT_SWITCH_LOG,
                    help="dispatch_switch 留痕 jsonl 路径")
    ap.add_argument("--sessions-root", type=str, default=None,
                    help="子分身会话存储根目录（缺省 ~/.dsh/sessions，测试可指向夹具目录）")
    ap.add_argument("--project-root", type=str, default=None,
                    help="顶层残渣 tripwire 扫描目标项目根（缺省 cwd）")
    args = ap.parse_args()

    result, code = seal(args.session_log, args.switch_log, args.sessions_root, args.project_root)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
