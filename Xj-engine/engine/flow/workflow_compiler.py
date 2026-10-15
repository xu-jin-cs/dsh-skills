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

SUPPORTED_CONTRACT_VERSIONS = {"sci/1"}  # 锚契约版本（语义承诺）；transformer_version 仅观测不参与判定
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
    cv = wf.get("contract_version")
    if cv not in SUPPORTED_CONTRACT_VERSIONS:
        raise CompileError(f"契约版本不受支持: contract_version={cv!r}（支持 {sorted(SUPPORTED_CONTRACT_VERSIONS)}）")

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


class GateReject(Exception):
    """runner/门禁打回信号：节点捕获后按 depends_on 路由回上游重建。"""


def _next_hop(compiled: dict, stage_id: str) -> str:
    """拓扑下一跳（组感知）：下一环节若是并行组成员 → 该组 fanout 节点；否则本身。"""
    order = compiled["topo_order"]
    groups = compiled.get("parallel_groups", {})
    member2group = {m: layer for layer, ms in groups.items() for m in ms}
    i = order.index(stage_id) + 1
    if i >= len(order):
        return "__end__"
    cand = order[i]
    if cand in member2group:
        return f"fanout_{member2group[cand]}"
    return cand


def _rollback_target(compiled: dict, stage_id: str) -> Optional[str]:
    deps = compiled["stages"][stage_id].get("depends_on", [])
    return deps[-1] if deps else None


def _semantic_gate(stage: dict, deliverable_path: Optional[str]) -> Optional[str]:
    """语义层挂载点：stage 声明 gate_spec 时扳对应 gate-switch spec（判定照抄不手写）。
    返回 None=判A放行；否则返回 violations 文本（判B）。"""
    spec = stage.get("gate_spec")
    if not spec or not deliverable_path:
        return None
    gate = os.path.expanduser("~/.agents/skills/gate-switch/scripts/gate_switch.py")
    r = subprocess.run(
        ["python3", gate, "--spec", os.path.expanduser(spec),
         "--set", f"block={deliverable_path}"],
        capture_output=True, text=True)
    try:
        out = json.loads(r.stdout[r.stdout.find("{"):])
        if out.get("verdict") == "A":
            return None
        return json.dumps(out.get("violations"), ensure_ascii=False)
    except (ValueError, KeyError):
        return f"gate_spec 输出不可解析(exit={r.returncode}): {(r.stderr or r.stdout)[-200:]}"


def make_stage_node(
    stage_id: str,
    compiled: dict,
    artifacts_root: str,
    plugin_bin: str,
    runner: Callable[[str, str], str],
    max_rollback: int = 3,
) -> Callable:
    """生成 NodeFn 兼容节点：装配→执行委托→index_sync→语义闸→快照 五步+显式路由。

    runner(prompt, stage_id) -> 交付物文本；抛 GateReject 表示门禁打回。
    路由：正常→拓扑下一环节（末环→__end__ 并触发 clean）；打回→depends_on 上游；
    打回次数超 max_rollback → 冻结（熔断红线）。
    """
    stage = compiled["stages"][stage_id]
    stage_dir = compiled["stage_dirs"][stage_id]
    assemble_cli = os.path.join(plugin_bin, "assemble_stage_context.py")
    snapshot_cli = os.path.join(plugin_bin, "snapshot_manager.py")

    def node(state):
        wf_id = compiled["workflow_id"]
        rollback_count = sum(1 for e in state.error_log if e.startswith(f"[{stage_id}] 打回"))
        if rollback_count >= max_rollback:
            state.is_frozen = True
            state.freeze_reason = f"[{stage_id}] 打回次数达熔断上限 {max_rollback}"
            return state, None
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
            target = _rollback_target(compiled, stage_id)
            return state, target  # 装配失败=上游产物问题，路由回上游重建

        prompt = r.stdout

        # 步骤2：执行委托（LLM/spawn 桥接由 runner 注入）
        try:
            deliverable = runner(prompt, stage_id)
        except GateReject as e:
            state.error_log.append(f"[{stage_id}] 打回: {e}")
            return state, _rollback_target(compiled, stage_id)

        # 步骤3：index_sync（交付物落盘）
        outs = stage.get("output_artifacts", [])
        deliverable_path = None
        if outs:
            a = outs[0]
            rel = os.path.join(stage_dir, f"{a['name']}_v1.{a.get('suffix', 'md')}")
            deliverable_path = os.path.join(artifacts_root, rel)
            _atomic_write(deliverable_path, deliverable)

        # 步骤4：语义闸挂载点（gate.post 业务段，spec 由工作流声明）
        violations = _semantic_gate(stage, deliverable_path)
        if violations:
            state.error_log.append(f"[{stage_id}] 打回: 语义闸判B {violations}")
            return state, _rollback_target(compiled, stage_id)

        # 账本绑定：外部角色交付物入 DeliverableRecord（角色名记 summary，枚举用 EXTERNAL）
        if deliverable_path:
            try:
                from engine.flow.state import DeliverableRecord, NodeType
                import datetime as _dt
                rec = DeliverableRecord(
                    content_type=outs[0].get("suffix", "md"),
                    summary=f"[external:{stage.get('agent', stage_id)}] {stage_id} 交付物",
                    agent_role=NodeType.EXTERNAL,
                    file_path=deliverable_path,
                    validated=True,
                    validation_result="assemble+semantic_gate pass",
                    created_at=_dt.datetime.now().isoformat(),
                )
                state.deliverables = state.deliverables + [rec]
            except Exception as e:  # 账本绑定失败不阻断业务，留痕即可
                state.error_log.append(f"[{stage_id}] WARN 账本绑定失败: {e}")

        # 步骤5：快照（gate.post 插件段；幂等）
        subprocess.run(
            ["python3", snapshot_cli, "snapshot", "--artifacts-root", artifacts_root,
             "--stage-dir", stage_dir, "--stage-id", stage_id, "--workflow-id", wf_id],
            capture_output=True, text=True)

        # 显式路由：末环完成→闭环清理→__end__
        nxt = _next_hop(compiled, stage_id)
        if nxt == "__end__" and stage_id in compiled["final_stages"] and compiled["cleanup_on_complete"]:
            subprocess.run(
                ["python3", snapshot_cli, "clean", "--artifacts-root", artifacts_root,
                 "--stage-dir", "."],
                capture_output=True, text=True)
        return state, nxt

    return node


# ─── runner 桥（执行委托的注入点）──────────────────────────────
# runner 契约：runner(prompt: str, stage_id: str) -> str（交付物文本）；
# 抛 GateReject = 门禁打回。生产桥接二选一：ZCode 子 Agent spawn（隔离语义已实测）
# 或引擎内推理；默认实现走 SCI_RUNNER_CMD 环境变量声明的外部命令桥。

def default_runner(prompt: str, stage_id: str) -> str:
    """默认 runner：SCI_RUNNER_CMD 外部命令桥。
    SCI_RUNNER_CMD 为命令模板，{prompt_file} 会被替换为 prompt 临时文件路径，
    命令 stdout 即交付物文本。未配置即报错指路（禁止静默桩跑生产）。"""
    cmd_tpl = os.environ.get("SCI_RUNNER_CMD")
    if not cmd_tpl:
        raise RuntimeError(
            "runner 未配置：设 SCI_RUNNER_CMD（如 'my-llm-cli --file {prompt_file}'），"
            "或向 build_flow_graph 显式注入 runner 桥（ZCode spawn / 引擎内推理）")
    fd, pf = tempfile.mkstemp(suffix=".md", prefix=f"prompt_{stage_id}_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(prompt)
    try:
        r = subprocess.run(cmd_tpl.format(prompt_file=pf), shell=True,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"runner 命令失败(exit={r.returncode}): {r.stderr[-200:]}")
        return r.stdout
    finally:
        os.unlink(pf)


# ─── 图构建（零引擎改动：显式路由驱动，不碰全局注册表）─────────

def _merge_branch_error_log(state, branch_state) -> None:
    for e in getattr(branch_state, "error_log", []):
        if e not in state.error_log:
            state.error_log.append(e)


def make_fanout_node(layer: str, members: list, compiled: dict,
                     artifacts_root: str, plugin_bin: str,
                     runner: Callable[[str, str], str], graph_ref):
    """并行组扇出节点：闸判定（judge_parallel_fanout）→ 真并发线程池执行各分支 → 合流。
    每分支深拷贝 state 跑完整五步节点体；交付物按环节目录物理隔离天然无写冲突。"""
    from concurrent.futures import ThreadPoolExecutor

    join_target = None
    order = compiled["topo_order"]
    groups = compiled.get("parallel_groups", {})
    member2group = {m: ly for ly, ms in groups.items() for m in ms}
    last_idx = max(order.index(m) for m in members)
    j = last_idx + 1
    while j < len(order) and order[j] in member2group and member2group[order[j]] == layer:
        j += 1
    join_target = order[j] if j < len(order) else "__end__"
    if join_target != "__end__" and join_target in member2group:
        join_target = f"fanout_{member2group[join_target]}"  # 连续并行组：合流点指下一组的扇出

    def fanout(state):
        verdict = graph_ref.judge_parallel_fanout(members)
        state.error_log.append(f"[fanout:{layer}] 并行判定 {verdict['verdict']} via {verdict['via']}")
        if verdict["verdict"] == "parallel":
            with ThreadPoolExecutor(max_workers=len(members)) as pool:
                futs = []
                for m in members:
                    node_fn = make_stage_node(m, compiled, artifacts_root, plugin_bin, runner)
                    futs.append(pool.submit(node_fn, state.model_copy(deep=True)))
                for f in futs:
                    branch_state, _ = f.result()
                    _merge_branch_error_log(state, branch_state)
        else:
            for m in members:  # 闸判串行/降级 → 顺序执行保语义
                node_fn = make_stage_node(m, compiled, artifacts_root, plugin_bin, runner)
                state, _ = node_fn(state)
        return state, join_target

    return fanout


def build_flow_graph(compiled: dict, artifacts_root: str, plugin_bin: str,
                     runner: Callable[[str, str], str], checkpointer=None):
    """把编译产物组装成可执行 FlowGraph。

    节点显式 routing_key 驱动流转（graph.py step 第5步：显式路由覆盖 Edge），
    不注册全局条件边、不调用 FlowGraph.compile()（避免注册引擎内置开发流节点）。
    并行组（坐标含"分支"）折叠为 fanout_<层级> 合成节点，闸判定后真并发执行。
    """
    from engine.flow.graph import FlowGraph

    g = FlowGraph()
    groups = compiled.get("parallel_groups", {})
    member2group = {m: layer for layer, members in groups.items() for m in members}
    order = compiled["topo_order"]
    i = 0
    while i < len(order):
        sid = order[i]
        if sid in member2group:
            layer = member2group[sid]
            members = sorted(groups[layer], key=lambda m: order.index(m))
            g.register_node(f"fanout_{layer}",
                            make_fanout_node(layer, members, compiled, artifacts_root,
                                             plugin_bin, runner, g))
            i = order.index(members[-1]) + 1  # 跳过整组（组内成员由扇出节点执行）
            continue
        g.register_node(sid, make_stage_node(sid, compiled, artifacts_root, plugin_bin, runner))
        i += 1
    g._compiled = True  # 内核接入层同包内手工编译态：本图节点已全部注册
    g._checkpointer = checkpointer
    return g
