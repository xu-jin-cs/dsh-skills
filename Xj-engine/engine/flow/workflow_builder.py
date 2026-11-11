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
BUILDER_VERSION = "builder-1.1"
DEFAULT_PLUGIN_BIN = os.path.expanduser(
    "~/.zcode/workspace/default/plugins/stage-context-isolation/bin")

# 源语义字段：编排源里有、执行投影不需要，但读取方（宿主内核）需要。
# 统一契约后写入 source.stages[]，编译器不消费，读取方按 stage_id 取用。
SOURCE_STAGE_FIELDS = (
    "deliverables", "branch_conditions", "harness_sync", "next_agents",
    "parallel_group", "invoked_skills", "identity", "display_name",
    "permissions", "self_checks",
)
SOURCE_TOP_FIELDS = ("state_model", "flow_b", "engine_name", "engine_api",
                     "input_schema", "rules")


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
        runtime = s.get("agent_runtime", "zcode")
        stage = {
            "stage_id": sid,
            "agent": s.get("agent", sid),
            "agent_runtime": runtime,
            "depends_on": list(s.get("depends_on") or []),
            "type": s.get("type", "zcode"),
            "output_artifacts": [
                {"name": a["name"], "suffix": a.get("suffix", "md")} for a in arts
            ],
            "gate": {},
        }
        if s.get("parallel_group"):
            stage["parallel_group"] = s["parallel_group"]
        # 隔离钩子只注入 ZCode 运行时节点；外部/人工节点不挂 zplugin 钩子
        if runtime == "zcode":
            stage["gate"] = {
                "pre": ["zplugin:cli_assemble_stage"],
                "post": ["index_sync", "zplugin:cli_snapshot_and_clear"],
                "rollback": ["zplugin:cli_restore_snapshot"],
            }
            stage["cli_context_config"] = {
                "isolate_mode": "stage_spawn_subagent",
                "persist_snapshot": True,
                "keep_global": ["INDEX.md"],
                "discard_upstream_chat_history": True,
                "max_artifact_char": 12000,
                "enable_parallel_isolate": True,
                "snapshot_dir": "{stage_dir}/snapshots",
            }
        out.append(stage)
    return out


def _build_source(spec: dict, stages: list[dict]) -> dict:
    """把编排源语义收进 source 段（源数据，编译器只读不覆盖）。

    源语义的权威来源是编排源（flow.yml/spec）；缺失只标注 missing，不伪造。
    """
    src_stages = []
    missing = []
    for s in stages:
        sid = s["stage_id"]
        item = {"stage_id": sid}
        for f in SOURCE_STAGE_FIELDS:
            if s.get(f) not in (None, "", [], {}):
                item[f] = s[f]
        src_stages.append(item)
        if not item.get("deliverables"):
            missing.append(f"{sid}.deliverables")
        if not item.get("branch_conditions"):
            missing.append(f"{sid}.branch_conditions")
    source = {"stages": src_stages}
    for f in SOURCE_TOP_FIELDS:
        if spec.get(f) not in (None, "", [], {}):
            source[f] = spec[f]
    for f in ("state_model", "flow_b"):
        if f not in source:
            missing.append(f)
    source["source_status"] = {"complete": not missing, "missing": missing[:50]}
    return source


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
    raw_stages = spec.get("stages") or []
    stages = _normalize(raw_stages)
    if not stages:
        raise ValueError("spec 缺 stages")
    source = _build_source(spec, raw_stages)
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
        "source": source,
        "stages": stages,
    }
    os.makedirs(out_dir, exist_ok=True)
    wf_path = os.path.join(out_dir, "workflow.json")
    # 观测声明是源数据，不是投影：重编译必须原样保留，丢失即阻断。
    previous: dict = {}
    if os.path.isfile(wf_path):
        try:
            previous = json.load(open(wf_path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    prev_observe = previous.get("observe") if isinstance(previous, dict) else None
    if isinstance(spec.get("observe"), dict):
        workflow["observe"] = spec["observe"]
    elif isinstance(prev_observe, dict):
        workflow["observe"] = prev_observe
    if isinstance(prev_observe, dict):
        new_obs = workflow.get("observe")
        if not isinstance(new_obs, dict):
            raise ValueError("重编译会丢失已有 observe 声明，已阻断（禁止原地覆盖）")
        if len(new_obs.get("nodes") or []) < len(prev_observe.get("nodes") or []):
            raise ValueError("重编译会缩减已有 observe 节点数，已阻断（禁止静默丢观测）")
        if new_obs.get("assetKey") != prev_observe.get("assetKey"):
            raise ValueError("重编译改变了 observe.assetKey，已阻断（降级为新增资产由人工确认）")
    if spec.get("require_source") and not source["source_status"]["complete"]:
        raise ValueError(
            "源语义不完整（require_source=true）：" + "、".join(source["source_status"]["missing"][:8]))
    _atomic_write(wf_path,
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
        "source_status": source["source_status"],
        "observe_preserved": isinstance(workflow.get("observe"), dict),
    }, ensure_ascii=False, indent=1) + "\n")
    return workflow
