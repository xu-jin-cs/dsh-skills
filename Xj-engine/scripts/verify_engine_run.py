#!/usr/bin/env python3
"""校验工作流是否经 Xj-engine 跑完（engine_entry 收尾闸）。

判据：
  1. ~/.agents/logs/engine_flow_runs.jsonl 存在该 workflow 的 run_complete；
  2. （--strict-stages）该 workflow 的每个 stage 在 stage_isolation 台账里都有 assemble+spawn。

用法：
  python3 verify_engine_run.py --workflow pm --strict-stages
  python3 verify_engine_run.py --workflow pm --workflow-json <path> --strict-stages
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

RUN_LEDGER = os.environ.get(
    "ENGINE_FLOW_RUN_LEDGER",
    os.path.expanduser("~/.agents/logs/engine_flow_runs.jsonl"))
STAGE_LEDGER = os.environ.get(
    "STAGE_ISOLATION_LEDGER",
    os.path.expanduser("~/.agents/logs/stage_isolation.jsonl"))


def _rows(path: str) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def _recent(rows: list[dict], within_hours: int) -> list[dict]:
    if not within_hours:
        return rows
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=within_hours)
    kept = []
    for r in rows:
        try:
            ts = datetime.datetime.fromisoformat(str(r.get("ts")))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            if ts >= cutoff:
                kept.append(r)
        except Exception:
            continue
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description="Xj-engine 运行留痕校验")
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--workflow-json", default="")
    ap.add_argument("--artifacts-root", default="")
    ap.add_argument("--run-ledger", default=RUN_LEDGER)
    ap.add_argument("--stage-ledger", default=STAGE_LEDGER)
    ap.add_argument("--strict-stages", action="store_true")
    ap.add_argument("--within-hours", type=int, default=0)
    args = ap.parse_args()

    runs = _recent(_rows(args.run_ledger), args.within_hours)
    done = [r for r in runs if r.get("event") == "run_complete"
            and r.get("workflow_id") == args.workflow]
    if not done:
        print(f"BLOCK 未发现 {args.workflow} 的 engine run_complete 留痕"
              f"（{args.run_ledger}）", file=sys.stderr)
        return 2

    if not args.strict_stages:
        print(f"OK {args.workflow} engine run_complete 存在（{len(done)} 次）")
        return 0

    wf_path = args.workflow_json or os.path.expanduser(
        f"~/.agents/skills/{args.workflow}/transformed/workflow.json")
    try:
        compiled = json.load(open(wf_path, encoding="utf-8"))
    except OSError:
        print(f"BLOCK workflow.json 不存在: {wf_path}", file=sys.stderr)
        return 2
    stages = [s.get("stage_id") for s in compiled.get("stages", [])]
    root = args.artifacts_root or os.path.join(os.path.dirname(os.path.abspath(wf_path)), "project_artifacts")
    try:
        index_text = open(os.path.join(root, "INDEX.md"), encoding="utf-8").read()
    except OSError:
        index_text = ""
    rows = _rows(args.stage_ledger)
    missing = []; pending = []
    for st in stages:
        ok_a = any(r.get("event") == "assemble" and r.get("ok")
                   and r.get("workflow_id") == args.workflow and r.get("stage_id") == st
                   and r.get("artifacts_root") == root for r in rows)
        ok_s = any(r.get("event") == "spawn" and r.get("ok")
                   and r.get("workflow_id") == args.workflow and r.get("stage_id") == st
                   and r.get("artifacts_root") == root for r in rows)
        if not (ok_a and ok_s):
            missing.append(st)
        m = re.search(rf"^\|\s*{re.escape(st)}\s*\|\s*v\d+\s*\|\s*([^|]*?)\s*\|", index_text, re.MULTILINE)
        if not m or m.group(1).strip() != "active":
            pending.append(st)
    if missing:
        print(f"BLOCK {args.workflow} stage 留痕缺失: {','.join(missing)}", file=sys.stderr)
        return 2
    if pending:
        print(f"BLOCK {args.workflow} INDEX 状态未回写 active: {','.join(pending)}", file=sys.stderr)
        return 2
    print(f"OK {args.workflow} engine run_complete + {len(stages)} stage 留痕完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
