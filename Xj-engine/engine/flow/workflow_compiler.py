"""
workflow_compiler.py — Xj-engine 内核接入层：stage-context-isolation 契约编译器

职责：把插件侧改造器产出的 workflow.json 编译为引擎声明式图层件——
  1. FlowNodeMeta 声明集（node_key=stage_id / display_name=agent / depends_on / produces）
  2. 接线计划（拓扑序、并行组、坐标、末环、cleanup_on_complete）
  3. 通用环节节点工厂 make_stage_node：节点体=装配→执行委托→index_sync→快照 四步，
     调插件 CLI（assemble_stage_context.py / snapshot_manager.py），LLM 执行由调用方
     注入 runner 桥接（本编译器不内置任何模型调用）。

契约版本锚（DIM-049）：仅接受 SUPPORTED_TRANSFORMER_VERSIONS；不符即 CompileError(BLOCK)。

V0.1 边界（诚实声明）：
  - FlowState 绑定只读 instance_id/project_description 用于 config 组装；DeliverableRecord
    的 agent_role 是引擎 NodeType 固定枚举，外部工作流角色不在枚举内，本期不写
    deliverables 列表，交付物语义由 index_sync 文件落盘+快照引用承担。
  - 分支/回退的条件边函数由接线计划声明（rollback_target），路由实现随执行集成落地。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Callable, Optional

from engine.flow.node_defs import FlowNodeMeta

SUPPORTED_TRANSFORMER_VERSIONS = {"0.2.0"}
CONTRACT_REQUIRED_KEYS = ("workflow_id", "topo_order", "stages", "stage_dirs")


class CompileError(Exception):
    """契约不符/校验失败（BLOCK 语义）。"""


# ─── 契约编译 ─────────────────────────────────────────────────

def compile_workflow_json(path: str) -> dict:
    """workflow.json → 编译产物（FlowNodeMeta 声明集 + 接线计划）。"""
    try:
        wf = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CompileError(f"workflow.json 读取失败: {e}")
    missing = [k for k in CONTRACT_REQUIRED_KEYS if k not in wf]
    if missing:
        raise CompileError(f"契约缺必填字段: {missing}")
    tv = wf.get("transformer_version")
    if tv not in SUPPORTED_TRANSFORMER_VERSIONS:
        raise CompileError(f"契约版本不受支持: transformer_version={tv!r}（支持 {sorted(SUPPORTED_TRANSFORMER_VERSIONS)}）")

    stages = wf["stages"]
    ids = [s["stage_id"] for s in stages]
    if len(ids) != len(set(ids)):
        raise CompileError("stage_id 重复")
    idset = set(ids)
    for s in stages:
        for d in s.get("depends_on", []):
            if d not in idset:
                raise CompileError(f"depends_on 引用不存在: {s['stage_id']} → {d}")

    metas = {
        s["stage_id"]: FlowNodeMeta(
            node_key=s["stage_id"],
            display_name=s.get("agent", s["stage_id"]),
            depends_on=list(s.get("depends_on", [])),
            produces=[a["name"] for a in s.get("output_artifacts", [])],
        )
        for s in stages
    }
    # 并行组：同坐标层级内带分支号的成员
    coords = wf.get("coords", {})
    parallel_groups = {}
    for sid, coord in coords.items():
        if "分支" in coord:
            layer = coord.split("分支")[0]
            parallel_groups.setdefault(layer, []).append(sid)

    return {
        "workflow_id": wf["workflow_id"],
        "metas": metas,
        "topo_order": list(wf["topo_order"]),
        "coords": coords,
        "parallel_groups": parallel_groups,
        "final_stages": list(wf.get("final_stages", [])),
        "cleanup_on_complete": bool(wf.get("cleanup_on_complete", False)),
        "stage_dirs": dict(wf["stage_dirs"]),
        "stages": {s["stage_id"]: s for s in stages},
    }


# ─── 通用环节节点工厂 ─────────────────────────────────────────

def _atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def make_stage_node(
    stage_id: str,
    compiled: dict,
    artifacts_root: str,
    plugin_bin: str,
    runner: Callable[[str, str], str],
) -> Callable:
    """生成 NodeFn 兼容节点：装配→执行委托→index_sync→快照 四步。

    runner(prompt, stage_id) -> 交付物文本；LLM/spawn 桥接由调用方注入。
    返回 (state, None)；装配 BLOCK 时把原因追加进 state.error_log 并短路返回。
    """
    stage = compiled["stages"][stage_id]
    stage_dir = compiled["stage_dirs"][stage_id]
    assemble_cli = os.path.join(plugin_bin, "assemble_stage_context.py")
    snapshot_cli = os.path.join(plugin_bin, "snapshot_manager.py")

    def node(state):
        wf_id = compiled["workflow_id"]
        task = f"[{wf_id}/{stage_id}] {getattr(state, 'project_description', '') or '执行本环节任务'}"
        cfg = {
            "stage_id": stage_id,
            "workflow_id": wf_id,
            "artifacts_root": artifacts_root,
            "current_stage_dir": stage_dir,
            "task_instruction": task,
        }
        # 步骤1：装配（gate.pre）
        fd, cfg_path = tempfile.mkstemp(suffix=".json", prefix=f"stage_cfg_{stage_id}_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        r = subprocess.run(
            ["python3", assemble_cli, "--config", cfg_path],
            capture_output=True, text=True)
        os.unlink(cfg_path)
        if r.returncode != 0:
            state.error_log.append(f"[{stage_id}] 装配 BLOCK: {r.stderr.strip()}")
            return state, None
        prompt = r.stdout

        # 步骤2：执行委托（LLM/spawn 桥接由 runner 注入）
        deliverable = runner(prompt, stage_id)

        # 步骤3：index_sync（交付物落盘；版本取 manifest 声明的 v1 口径）
        outs = stage.get("output_artifacts", [])
        if outs:
            a = outs[0]
            rel = os.path.join(stage_dir, f"{a['name']}_v1.{a.get('suffix', 'md')}")
            _atomic_write(os.path.join(artifacts_root, rel), deliverable)

        # 步骤4：快照（gate.post 的插件段；幂等，状态不变不新增）
        subprocess.run(
            ["python3", snapshot_cli, "snapshot", "--artifacts-root", artifacts_root,
             "--stage-dir", stage_dir, "--stage-id", stage_id, "--workflow-id", wf_id],
            capture_output=True, text=True)
        return state, None

    return node
