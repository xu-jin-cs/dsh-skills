"""xj-engine 命令行入口。

用法示例：
  xj-engine health
  xj-engine run --payload '{"op": ...}'
  xj-engine complete --task-id xxx --evidence '{"output":"result.json"}'
"""
from __future__ import annotations

import argparse
import json
import sys


def _cmd_health() -> int:
    try:
        import engine.kernel as kernel
        import engine.database as database
        print(json.dumps({
            "status": "ok",
            "engine": "Xj-engine",
            "entry": "engine.kernel.et",
            "database": str(database.DATABASE_URL),
            "has_et": hasattr(kernel, "et"),
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Xj-engine health check failed: {exc}", file=sys.stderr)
        return 1


def _cmd_run(payload_text: str) -> int:
    try:
        payload = json.loads(payload_text)
        from engine.kernel import et
        result = et(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("code") == "success" else 1
    except Exception as exc:
        print(f"xj-engine run failed: {exc}", file=sys.stderr)
        return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="xj-engine", description="Xj-engine CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="检查 Xj-engine 是否可用")

    run_p = sub.add_parser("run", help="执行引擎 payload")
    run_p.add_argument("--payload", required=True, help="JSON payload 字符串")

    complete_p = sub.add_parser("complete", help="任务完成 hook：触发 task.complete")
    complete_p.add_argument("--task-id", required=True, help="任务 ID")
    complete_p.add_argument("--evidence", required=True, help="完成证据 JSON（非空）")
    complete_p.add_argument("--trace-id", default="", help="可选，缺省自动生成")

    args = parser.parse_args(argv)
    if args.cmd == "health":
        return _cmd_health()
    if args.cmd == "run":
        return _cmd_run(args.payload)
    if args.cmd == "complete":
        from engine.task_complete_hook import main_cli
        return main_cli(args.task_id, args.evidence, args.trace_id)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
