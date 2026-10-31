"""workflow_validator.py — 工作流契约与骨架校验（引擎侧，运行前）。

只校验「能不能跑」：契约版本、拓扑、目录、骨架 INDEX/manifest、依赖可解析、插件运行时可执行。
"""

from __future__ import annotations

import json
import os

CONTRACT_VERSION = "sci/1"


def validate(path: str) -> list[str]:
    errs: list[str] = []
    try:
        wf = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"workflow.json 不可读: {e}"]

    if wf.get("contract_version") != CONTRACT_VERSION:
        errs.append(f"contract_version 必须为 {CONTRACT_VERSION}（实际 {wf.get('contract_version')!r}）")
    for key in ("workflow_id", "topo_order", "stages", "stage_dirs"):
        if key not in wf:
            errs.append(f"缺字段: {key}")
    if errs:
        return errs

    stages = wf["stages"]
    if isinstance(stages, list):
        stages = {s.get("stage_id"): s for s in stages}
    order = wf["topo_order"]
    stage_dirs = wf["stage_dirs"]

    if set(order) != set(stages):
        errs.append(f"topo_order 与 stages 不一致: order={order} stages={sorted(stages)}")
    for sid in order:
        if sid not in stage_dirs:
            errs.append(f"stage_dirs 缺 {sid}")
        for dep in (stages[sid].get("depends_on") or []):
            if dep not in stages:
                errs.append(f"{sid} 依赖未定义: {dep}")
            elif order.index(dep) > order.index(sid):
                errs.append(f"{sid} 依赖 {dep} 在拓扑序之后")

    root = os.path.join(os.path.dirname(os.path.abspath(path)), "project_artifacts")
    index = os.path.join(root, "INDEX.md")
    if not os.path.isfile(index):
        errs.append(f"缺骨架 INDEX.md: {index}")
    for sid in order:
        d = stage_dirs.get(sid)
        if not d:
            continue
        man = os.path.join(root, d, "manifest.md")
        if not os.path.isfile(man):
            errs.append(f"{sid} 缺 manifest.md: {man}")
            continue
        try:
            text = open(man, encoding="utf-8").read()
        except OSError:
            text = ""
        if "## 上游依赖" not in text:
            errs.append(f"{sid} manifest 缺「## 上游依赖」节")
        for dep in (stages[sid].get("depends_on") or []):
            dep_dir = stage_dirs.get(dep)
            if dep_dir and not os.path.isdir(os.path.join(root, dep_dir)):
                errs.append(f"{sid} 依赖目录不存在: {dep_dir}")

    plugin_bin = wf.get("plugin_bin") or ""
    if not plugin_bin:
        errs.append("缺 plugin_bin（stage 运行时路径）")
    else:
        for name in ("assemble_stage_context.py", "snapshot_manager.py"):
            if not os.path.isfile(os.path.join(plugin_bin, name)):
                errs.append(f"stage 运行时缺 {name}: {plugin_bin}")
    return errs
