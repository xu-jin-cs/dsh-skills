"""workflow_builder.py — 单一工作流契约构建器（引擎侧）。

一次原子产出：workflow.json + project_artifacts/INDEX.md + 每 stage manifest.md。
创建者/transform-workflow 都调本构建器，避免双源漂移与骨架缺失。

spec 最小字段：
  {"workflow_id": "...", "stages": [{"stage_id","agent","depends_on":[],
    "output_artifacts":[{"name","suffix"}]}]}
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

CONTRACT_VERSION = "sci/1"
BUILDER_VERSION = "builder-1.0"
DEFAULT_PLUGIN_BIN = os.path.expanduser(
    "~/.zcode/workspace/default/plugins/stage-context-isolation/bin")


def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _topo(stages: list[dict]) -> list[str]:
    deps = {s["stage_id"]: set(s.get("depends_on") or []) for s in stages}
    order: list[str] = []
    while deps:
        ready = sorted([sid for sid, d in deps.items() if not (d & set(deps))])
        if not ready:
            raise ValueError(f"依赖环或依赖缺失: {sorted(deps)}")
        for sid in ready:
            order.append(sid)
            deps.pop(sid)
    return order


def _final_stages(stages: list[dict], order: list[str]) -> list[str]:
    has_child = set()
    for s in stages:
        has_child |= set(s.get("depends_on") or [])
    return [sid for sid in order if sid not in has_child]


def _normalize(stages: list[dict]) -> list[dict]:
    out = []
    for s in stages:
        sid = s.get("stage_id")
        if not sid:
            raise ValueError("stage 缺 stage_id")
        arts = s.get("output_artifacts") or []
        out.append({
            "stage_id": sid,
            "agent": s.get("agent", sid),
            "agent_runtime": s.get("agent_runtime", "zcode"),
            "depends_on": list(s.get("depends_on") or []),
            "type": s.get("type", "zcode"),
            "output_artifacts": [
                {"name": a["name"], "suffix": a.get("suffix", "md")} for a in arts
            ],
            "gate": {
                "pre": ["zplugin:cli_assemble_stage"],
                "post": ["index_sync", "zplugin:cli_snapshot_and_clear"],
                "rollback": ["zplugin:cli_restore_snapshot"],
            },
            "cli_context_config": {
                "isolate_mode": "stage_spawn_subagent",
                "persist_snapshot": True,
                "keep_global": ["INDEX.md"],
                "discard_upstream_chat_history": True,
                "max_artifact_char": 12000,
                "enable_parallel_isolate": True,
                "snapshot_dir": "{stage_dir}/snapshots",
            },
        })
    return out


def _skeleton(stages: list[dict], order: list[str], dir_of: dict[str, str],
              out_dir: str, workflow_id: str) -> None:
    art_root = os.path.join(out_dir, "project_artifacts")
    by = {s["stage_id"]: s for s in stages}
    rows = []
    for sid in order:
        for a in by[sid].get("output_artifacts", []):
            rows.append(f"| {sid} | v1 | pending | {dir_of[sid]}/{a['name']}_v1.{a.get('suffix','md')} |")
    index_text = (f"# 项目台账（workflow: {workflow_id}，builder v{BUILDER_VERSION} 生成）\n\n"
                  "| 环节 | 版本 | 状态 | 产物路径 |\n| --- | --- | --- | --- |\n"
                  + "\n".join(rows) + "\n")
    _atomic_write(os.path.join(art_root, "INDEX.md"), index_text)
    for sid in order:
        deps = by[sid].get("depends_on") or []
        dep_rows = []
        for d in deps:
            for a in by.get(d, {}).get("output_artifacts", []):
                dep_rows.append(f"| {d} | v1 | {dir_of[d]}/{a['name']}_v1.{a.get('suffix','md')} |")
        deps_text = "\n".join(dep_rows) if dep_rows else "（无，首环节）"
        plist = "\n".join(
            f"- {a['name']}_v1.{a.get('suffix','md')}"
            for a in by[sid].get("output_artifacts", [])) or "- （待补充）"
        manifest = (f"# {sid} 环节 manifest\n\n## 上游依赖\n"
                    "| 上游环节 | 版本 | 交付物相对路径 |\n| --- | --- | --- |\n"
                    f"{deps_text}\n\n## 产物清单\n{plist}\n")
        _atomic_write(os.path.join(art_root, dir_of[sid], "manifest.md"), manifest)


def build_workflow(spec: dict[str, Any], out_dir: str,
                   plugin_bin: str = "") -> dict[str, Any]:
    workflow_id = spec.get("workflow_id")
    if not workflow_id:
        raise ValueError("spec 缺 workflow_id")
    stages = _normalize(spec.get("stages") or [])
    if not stages:
        raise ValueError("spec 缺 stages")
    order = _topo(stages)
    dir_of = {sid: f"{i + 1:02d}_{sid}" for i, sid in enumerate(order)}
    final = _final_stages(stages, order)
    for s in stages:
        s["coord"] = f"环节{order.index(s['stage_id']) + 1}"
        if s["stage_id"] in final:
            s["terminal"] = True

    plugin_bin = plugin_bin or spec.get("plugin_bin") or DEFAULT_PLUGIN_BIN
    enforcement = {
        "version": 1,
        "ledger": "~/.agents/logs/stage_isolation.jsonl",
        "require": ["assemble", "spawn"],
        "commands": {
            "assemble": f'python3 "{plugin_bin}/stage_guard.py" assemble --dispatch <dispatch_file> --instruction "<task_instruction>"',
            "spawn": f'python3 "{plugin_bin}/stage_guard.py" spawn --dispatch <dispatch_file>',
            "snapshot": f'python3 "{plugin_bin}/stage_guard.py" snapshot --dispatch <dispatch_file>',
            "check": f'python3 "{plugin_bin}/stage_guard.py" check --workflow {workflow_id} --stage <stage_id>',
            "status": f'python3 "{plugin_bin}/stage_guard.py" status --workflow {workflow_id} --strict',
        },
    }
    workflow = {
        "workflow_id": workflow_id,
        "transformer_version": BUILDER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "topo_order": order,
        "coords": {s["stage_id"]: s["coord"] for s in stages},
        "final_stages": final,
        "cleanup_on_complete": True,
        "stage_dirs": dir_of,
        "plugin_bin": plugin_bin,
        "enforcement": enforcement,
        "stages": stages,
    }
    os.makedirs(out_dir, exist_ok=True)
    _atomic_write(os.path.join(out_dir, "workflow.json"),
                  json.dumps(workflow, ensure_ascii=False, indent=1) + "\n")
    _skeleton(stages, order, dir_of, out_dir, workflow_id)
    _atomic_write(os.path.join(out_dir, "registry.json"), json.dumps({
        "workflow_id": workflow_id,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "builder_version": BUILDER_VERSION,
        "contract_version": CONTRACT_VERSION,
    }, ensure_ascii=False, indent=1) + "\n")
    _atomic_write(os.path.join(out_dir, "compile_report.json"), json.dumps({
        "workflow_id": workflow_id,
        "builder_version": BUILDER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "topo_order": order,
        "final_stages": final,
        "stages": len(stages),
    }, ensure_ascii=False, indent=1) + "\n")
    return workflow
