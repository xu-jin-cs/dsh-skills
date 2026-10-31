"""xj-engine 命令行入口。

用法示例：
  xj-engine health
  xj-engine run --payload '{"op": ...}'
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
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


def _cmd_workflow_init(spec_path: str, out_dir: str, plugin_bin: str) -> int:
    try:
        from engine.flow.workflow_builder import build_workflow
        spec = json.load(open(os.path.expanduser(spec_path), encoding="utf-8"))
        wf = build_workflow(spec, os.path.expanduser(out_dir), plugin_bin)
        print(json.dumps({"workflow_id": wf["workflow_id"], "stages": len(wf["stages"]),
                          "out_dir": os.path.abspath(os.path.expanduser(out_dir))},
                         ensure_ascii=False, indent=1))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"workflow init 失败: {exc}", file=sys.stderr)
        return 2


def _cmd_workflow_validate(path: str, as_json: bool) -> int:
    from engine.flow.workflow_validator import validate
    errs = validate(os.path.expanduser(path))
    if as_json:
        print(json.dumps({"valid": not errs, "errors": errs}, ensure_ascii=False, indent=1))
    elif errs:
        for e in errs:
            print(f"BLOCK {e}", file=sys.stderr)
    else:
        print("OK 工作流契约与骨架完整")
    return 0 if not errs else 2


def _cmd_flow_run(args) -> int:
    if not getattr(args, "allow_host", False):
        os.environ.setdefault("XJFRAME_STRICT_NO_HOST", "1")
    try:
        from engine.flow.workflow_compiler import (
            build_flow_graph, compile_workflow_json, default_runner,
        )
        from engine.flow.integration import build_initial_state
    except Exception as exc:  # noqa: BLE001
        print(f"flow run 导入失败: {exc}", file=sys.stderr)
        return 2

    from engine.flow.workflow_validator import validate
    wf_path = os.path.abspath(os.path.expanduser(args.workflow_json))
    errs = validate(wf_path)
    if errs:
        for e in errs:
            print(f"BLOCK {e}", file=sys.stderr)
        return 2

    compiled = compile_workflow_json(wf_path)
    wf = compiled["workflow_id"]
    root = args.artifacts_root or os.path.join(os.path.dirname(wf_path), "project_artifacts")
    if args.runner_mode == "stub":
        runner = lambda prompt, stage: f"# {stage}\n\nstub deliverable"
    else:
        if args.runner_cmd:
            os.environ["SCI_RUNNER_CMD"] = args.runner_cmd
        runner = default_runner

    binp = compiled.get("plugin_bin") or os.path.join(
        os.path.expanduser("~/.zcode/workspace/default/plugins/stage-context-isolation/bin"))
    graph = build_flow_graph(compiled, root, binp, runner)
    state = graph.execute(
        build_initial_state(
            instance_id=args.instance_id,
            project_name=args.project,
            project_description=args.description,
            evidence_root=args.evidence_root or os.path.join(
                args.project, "workspace/evidence", args.instance_id),
        ),
        start_node=compiled["topo_order"][0],
    )
    print(json.dumps({
        "workflow_id": wf,
        "strict_host": os.environ.get("XJFRAME_STRICT_NO_HOST") == "1",
        "frozen": bool(getattr(state, "is_frozen", False)),
        "freeze_reason": getattr(state, "freeze_reason", ""),
        "errors": (getattr(state, "error_log", []) or [])[-5:],
    }, ensure_ascii=False, indent=1))

    verify = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "scripts", "verify_engine_run.py")
    verify = os.path.abspath(verify)
    r = subprocess.run(
        ["python3", verify, "--workflow", wf, "--workflow-json", wf_path,
         "--artifacts-root", root, "--strict-stages"],
        capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="xj-engine", description="Xj-engine CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="检查 Xj-engine 是否可用")

    run_p = sub.add_parser("run", help="执行引擎 payload")
    run_p.add_argument("--payload", required=True, help="JSON payload 字符串")

    wf_p = sub.add_parser("workflow", help="工作流契约构建/校验")
    wf_sub = wf_p.add_subparsers(dest="wf_cmd", required=True)
    wf_init = wf_sub.add_parser("init", help="从 spec 生成 workflow.json + 骨架")
    wf_init.add_argument("--spec", required=True)
    wf_init.add_argument("--out-dir", required=True)
    wf_init.add_argument("--plugin-bin", default="")
    wf_val = wf_sub.add_parser("validate", help="校验契约与骨架")
    wf_val.add_argument("--workflow-json", required=True)
    wf_val.add_argument("--json", action="store_true")

    flo_p = sub.add_parser("flow", help="执行编译后的工作流图")
    flo_sub = flo_p.add_subparsers(dest="flow_cmd", required=True)
    flo_run = flo_sub.add_parser("run", help="编译→建图→执行→engine_entry 对账")
    flo_run.add_argument("--workflow-json", required=True)
    flo_run.add_argument("--artifacts-root", default="")
    flo_run.add_argument("--runner-cmd", default="")
    flo_run.add_argument("--runner-mode", choices=["cmd", "stub"], default="cmd")
    flo_run.add_argument("--project", default=".")
    flo_run.add_argument("--instance-id", default="engine-flow")
    flo_run.add_argument("--description", default="")
    flo_run.add_argument("--evidence-root", default="")
    flo_run.add_argument("--allow-host", action="store_true",
                         help="允许加载 agent-harness 集成（默认 strict 无宿主）")

    args = parser.parse_args(argv)
    if args.cmd == "health":
        return _cmd_health()
    if args.cmd == "run":
        return _cmd_run(args.payload)
    if args.cmd == "workflow":
        if args.wf_cmd == "init":
            return _cmd_workflow_init(args.spec, args.out_dir, args.plugin_bin)
        return _cmd_workflow_validate(args.workflow_json, args.json)
    if args.cmd == "flow":
        return _cmd_flow_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
