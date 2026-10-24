#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attached_dispatch.py — 任务量判定附身闸（2026-08-22 块N 混合模式方向1，REFORM-GATE 判A，
块文件 ~/.agents/logs/reform_blocks/attached_dispatch_hook_20260822.md）。

定位：附身执行非判定——宿主闸（plan_select chosen 输出链 / reform_gate 判A 检查项）
机械调用本脚本扳 dispatch_switch.py 做任务量纲判定，掷点结果原文转发：
  - verdict/throw/reasons/gate_declaration 原文打印（JSON 整包）；
  - 闸1/闸2 拒扳（VIOLATION exit 4）等一切非 A 结果同样原文转发为提醒，不炸宿主判定；
  - 本脚本恒 exit 0。
入参：--files/--units/--desc 参数优先；缺省时读 stdin（JSON {files,units,desc} 或纯文本
作 desc）；再取不到 → --files 1 --units 1 保守值（量纲判定的最小保守输入）。
留痕：dispatch_switch 自身落 dispatch_switch.jsonl；附身事件落 attached_dispatch.jsonl
（host/desc/files/units/掷点），供复盘区分"附身普检"与"信号路/手动"扳动。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import datetime
import time

DISPATCH_SWITCH = os.path.expanduser("~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py")
ATTACHED_LOG = os.path.expanduser("~/.agents/logs/attached_dispatch.jsonl")
DEDUP_LOG = os.path.expanduser("~/.agents/logs/dispatch_dedup.jsonl")
DEDUP_WINDOW_SEC = int(os.environ.get("DISPATCH_DEDUP_WINDOW_SEC", "600"))


def dispatch_dedup_seen(key: str) -> bool:
    """附身掷点去重（2026-10-24 触发链风暴防线）：同 (files,units) 量纲在时间窗内
    只掷一次。窗口内有记录→跳过；无→记录本次并放行。追加账+整档重写有竞态窗口，
    定位为尽力去重（并发同键可能双掷，可由 dispatch_switch.jsonl 复盘发现）。"""
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
        return False  # 去重账故障不放行去重语义，照常掷点
    if not seen:
        rows.append({"ts": now, "key": key, "window_sec": DEDUP_WINDOW_SEC})
        try:
            with open(DEDUP_LOG, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return seen


def resolve_inputs(args):
    files, units, desc = args.files, args.units, args.desc
    if files is None or units is None or not desc:
        raw = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
        if raw:
            try:
                payload = json.loads(raw)
                files = files if files is not None else payload.get("files")
                units = units if units is not None else payload.get("units")
                desc = desc or payload.get("desc")
            except Exception:
                desc = desc or raw[:120]
    # 保守兜底（块N：取不到就 --files 1 --units 1）
    files = files if isinstance(files, int) and files > 0 else 1
    units = units if isinstance(units, int) and units > 0 else 1
    desc = desc or "未命名任务（附身普检）"
    return files, units, desc


def main():
    ap = argparse.ArgumentParser(description="任务量判定附身闸（附身执行非判定，恒 exit 0）")
    ap.add_argument("--files", type=int, default=None)
    ap.add_argument("--units", type=int, default=None)
    ap.add_argument("--desc", default=None)
    ap.add_argument("--host", default="manual", help="宿主闸标识（plan_select/reform_gate/manual）")
    args = ap.parse_args()

    files, units, desc = resolve_inputs(args)
    dedup_key = hashlib.sha256(f"{files}|{units}".encode()).hexdigest()[:16]
    if dispatch_dedup_seen(dedup_key):
        print(json.dumps({
            "attached": True, "host": args.host, "dedup": True,
            "dedup_key": dedup_key, "window_sec": DEDUP_WINDOW_SEC,
            "note": f"同一量纲（files={files},units={units}）{DEDUP_WINDOW_SEC}s 窗口内已掷点，本次去重跳过。",
        }, ensure_ascii=False))
        try:
            with open(ATTACHED_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                                    "host": args.host, "desc": desc, "files": files,
                                    "units": units, "verdict": "DEDUP_SKIP",
                                    "key": dedup_key}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return 0
    try:
        r = subprocess.run(
            [sys.executable, DISPATCH_SWITCH, "--files", str(files),
             "--units", str(units), "--desc", desc],
            capture_output=True, text=True, timeout=120)
        try:
            dispatch = json.loads(r.stdout)
        except Exception:
            dispatch = {"verdict": "UNPARSEABLE", "stdout": r.stdout[:500],
                        "stderr": r.stderr[:500], "exit": r.returncode}
    except Exception as e:
        dispatch = {"verdict": "SPAWN_FAIL", "error": f"{type(e).__name__}: {e}"}

    out = {
        "attached": True, "host": args.host,
        "files": files, "units": units, "desc": desc,
        "dispatch_verdict": dispatch.get("verdict"),
        "dispatch_throw": dispatch.get("throw"),
        # 原文转发（含 VIOLATION 拒扳理由，作提醒不炸宿主）
        "dispatch_raw": dispatch,
        "note": ("附身执行非判定：dispatch 结果原文转发。"
                 + ("闸1/闸2 拒扳（VIOLATION）→ 按 directive 补登记后重扳。"
                    if dispatch.get("verdict") == "VIOLATION" else "照抄掷点结论执行。")),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    try:
        os.makedirs(os.path.dirname(ATTACHED_LOG), exist_ok=True)
        with open(ATTACHED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "host": args.host, "desc": desc, "files": files, "units": units,
                "verdict": dispatch.get("verdict"), "throw": dispatch.get("throw"),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0  # 恒 exit 0：附身执行非判定


if __name__ == "__main__":
    sys.exit(main())
