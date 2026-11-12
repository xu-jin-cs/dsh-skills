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

import datetime
import hashlib
import json
import os
import re
import subprocess
import tempfile
import sys
import threading
from typing import Callable, Optional

from engine.flow.node_defs import FlowNodeMeta

SUPPORTED_CONTRACT_VERSIONS = {"sci/1"}  # 锚契约版本（语义承诺）；transformer_version 仅观测不参与判定

# ─── 执行留痕（引擎节点自写；宿主不可绕过）──────────────────────
DEFAULT_STAGE_LEDGER = "~/.agents/logs/stage_isolation.jsonl"
DEFAULT_RUN_LEDGER = "~/.agents/logs/engine_flow_runs.jsonl"


def _ledger_path(kind: str = "stage") -> str:
    if kind == "stage":
        return os.path.expanduser(os.environ.get("STAGE_ISOLATION_LEDGER") or DEFAULT_STAGE_LEDGER)
    return os.path.expanduser(os.environ.get("ENGINE_FLOW_RUN_LEDGER") or DEFAULT_RUN_LEDGER)


def _append_jsonl(path: str, rec: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _stage_event(event: str, wf: str, stage: str, root: str,
                 ok: bool = True, chars: int = 0, note: str = "") -> None:
    _append_jsonl(_ledger_path("stage"), {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": event, "ok": bool(ok), "workflow_id": wf,
        "stage_id": stage, "artifacts_root": root,
        "chars": int(chars or 0), "note": note[:200],
    })


def _run_event(event: str, wf: str, **extra) -> None:
    _append_jsonl(_ledger_path("run"), {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "event": event, "workflow_id": wf, **extra,
    })


_INDEX_LOCK = threading.Lock()


def _update_index_status(artifacts_root: str, stage_id: str,
                         status: str = "active") -> None:
    """交付物落盘后回写 INDEX 状态（pending → active）。

    并行组会并发调用：必须串行化，否则后写覆盖先写，导致某成员状态丢失。
    """
    with _INDEX_LOCK:
        _update_index_status_locked(artifacts_root, stage_id, status)


def _update_index_status_locked(artifacts_root: str, stage_id: str,
                                status: str = "active") -> None:
    path = os.path.join(artifacts_root, "INDEX.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return
    pat = re.compile(rf"^(\|\s*{re.escape(stage_id)}\s*\|\s*v\d+\s*\|)\s*[^|]*\s*(\|.*)$")
    changed = False
    lines = []
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            line = f"{m.group(1)} {status} {m.group(2)}"
            changed = True
        lines.append(line)
    if changed:
        _atomic_write(path, "\n".join(lines) + "\n")


def _global_base() -> str:
    """子代理不继承 AGENTS.md；把全局提示词基线随 stage prompt 前置。"""
    try:
        text = open(os.path.expanduser("~/AGENTS.md"), encoding="utf-8").read()
    except OSError:
        return ""
    start, end = "<!-- GLOBAL-PROMPT-DIGEST:START -->", "<!-- GLOBAL-PROMPT-DIGEST:END -->"
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def _stage_has(event: str, wf: str, stage: str, root: str) -> bool:
    path = _ledger_path("stage")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (e.get("event") == event and e.get("ok")
                        and e.get("workflow_id") == wf and e.get("stage_id") == stage
                        and e.get("artifacts_root") == root):
                    return True
    except OSError:
        pass
    return False
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
    # 并行组：优先读契约显式声明的 parallel_group；旧产物无该字段时回落坐标文本启发
    coords = wf.get("coords", {})
    parallel_groups = {}
    for s in stages:
        pg = s.get("parallel_group")
        if pg:
            parallel_groups.setdefault(str(pg), []).append(s["stage_id"])
    if not parallel_groups:
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
        "enforcement": wf.get("enforcement") or {},
        "prompt": wf.get("prompt") or "",
        "tools": wf.get("tools") or [],
        "loop_bounds": wf.get("loop_bounds") or {},
        "refusal": wf.get("refusal") or {},
        "input_boundary": wf.get("input_boundary") or {},
        "asset_version": wf.get("asset_version") or "",
        "plan_approval": wf.get("plan_approval") or {},
        "failure_classes": wf.get("failure_classes") or {},
        "asset_acceptance": wf.get("asset_acceptance") or [],
        "asset_key": (wf.get("observe") or {}).get("assetKey") or "",
        "observe_runtime": (wf.get("observe") or {}).get("runtime") or "engine",
        "plugin_bin": wf.get("plugin_bin") or "",
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
    """打回目标（组感知）：上游是并行组成员 → 该组 fanout 节点（成员未单独注册）。"""
    deps = compiled["stages"][stage_id].get("depends_on", [])
    if not deps:
        return None
    target = deps[-1]
    groups = compiled.get("parallel_groups", {})
    for layer, members in groups.items():
        if target in members:
            return f"fanout_{layer}"
    return target


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


def _latest_snapshot(artifacts_root: str, stage_dir: str) -> str | None:
    d = os.path.join(artifacts_root, stage_dir, "snapshots")
    if not os.path.isdir(d):
        return None
    files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    return files[-1][:-5] if files else None


def _restore_stage(compiled: dict, target: str | None, artifacts_root: str,
                   plugin_bin: str) -> None:
    """打回/回退时重建目标环节上下文：restore 出装配配置，落 .restore_config.json。

    下次进入该环节时装配步骤会读取该配置（仅一次），确保回退后不是带脏上下文重跑。
    """
    if not target or target == "__end__" or target not in compiled.get("stage_dirs", {}):
        return
    wf_id = compiled["workflow_id"]
    stage_dir = compiled["stage_dirs"][target]
    sid = _latest_snapshot(artifacts_root, stage_dir)
    if not sid:
        _stage_event("restore_skip", wf_id, target, artifacts_root, True, note="无快照")
        return
    restore_cli = os.path.join(plugin_bin, "snapshot_manager.py")
    r = subprocess.run(
        ["python3", restore_cli, "restore", "--artifacts-root", artifacts_root,
         "--stage-dir", stage_dir, "--stage-id", target, "--snapshot-id", sid,
         "--workflow-id", wf_id],
        capture_output=True, text=True)
    if r.returncode != 0:
        _stage_event("restore_fail", wf_id, target, artifacts_root, False,
                     note=(r.stderr or r.stdout or "")[-200:])
        return
    try:
        cfg = json.loads(r.stdout)
    except ValueError:
        cfg = {}
    if isinstance(cfg, dict):
        _atomic_write(os.path.join(artifacts_root, stage_dir, ".restore_config.json"),
                      json.dumps(cfg, ensure_ascii=False, indent=1) + "\n")
    _stage_event("restore", wf_id, target, artifacts_root, True, note=sid)


def _observe_emit(compiled: dict, state, stage_id: str, agent_id: str,
                  event_type: str, status: str | None = None,
                  artifacts: list | None = None, error_code: str | None = None) -> None:
    """引擎执行向平台上报（官方通道：observe_hook.emit_event 唯一构造入口）。"""
    asset_key = compiled.get("asset_key") or ""
    if not asset_key:
        return
    task_id = str(getattr(state, "instance_id", "") or "engine_run")
    try:
        sys.path.insert(0, os.path.expanduser("~/.agents/agent-observe/bin"))
        import observe_hook as _oh  # type: ignore
        _oh.emit_event(task_id=task_id, asset_key=asset_key, agent_id=agent_id or stage_id,
                       node_id=stage_id, event_type=event_type, status=status,
                       artifacts=artifacts, error_code=error_code)
    except Exception as exc:  # noqa: BLE001 - 观测失败不影响执行
        _stage_event("observe_emit_fail", compiled.get("workflow_id", ""), stage_id,
                     "", False, note=f"{type(exc).__name__}: {exc}"[:180])


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
        ib = compiled.get("input_boundary") or {}
        max_chars = ib.get("maxInputChars")
        if max_chars and len(task) > int(max_chars):
            state.error_log.append(f"[{stage_id}] 输入超界 {len(task)} > {max_chars}")
            state.is_frozen = True
            state.freeze_reason = f"[{stage_id}] INPUT_BOUNDARY"
            _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                          "node_failed", status="failed", error_code="INPUT_BOUNDARY")
            return state, "__end__"
        cfg: dict = {}
        restore_cfg_path = os.path.join(artifacts_root, stage_dir, ".restore_config.json")
        if os.path.isfile(restore_cfg_path):
            try:
                loaded = json.load(open(restore_cfg_path, encoding="utf-8"))
                if isinstance(loaded, dict):
                    cfg.update(loaded)
            except (OSError, ValueError):
                pass
            try:
                os.unlink(restore_cfg_path)
            except OSError:
                pass
        cfg.update({
            "stage_id": stage_id,
            "workflow_id": wf_id,
            "artifacts_root": artifacts_root,
            "current_stage_dir": stage_dir,
            "task_instruction": task,
        })
        _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id), "node_start")
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
            _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                          "node_failed", status="failed", error_code="ASSEMBLE_BLOCKED")
            target = _rollback_target(compiled, stage_id)
            _restore_stage(compiled, target, artifacts_root, plugin_bin)
            return state, target  # 装配失败=上游产物问题，路由回上游重建

        prompt = r.stdout
        # 提示词注入：agent 自身提示词（agent.md 正文）优先于装配上下文，工具白名单随行
        agent_prompt = str(compiled.get("prompt") or "").strip()
        tools = compiled.get("tools") or []
        if agent_prompt:
            allow = ""
            if tools:
                def _tool_desc(t):
                    if not isinstance(t, dict):
                        return str(t)
                    acc = t.get("access") or ""
                    sc = "、".join(t.get("scopes") or [])
                    tail = f"（{acc}{'：' + sc if sc else ''}）" if acc else ""
                    return f"{t.get('name')}{tail}"
                names = [_tool_desc(t) for t in tools if (t.get("name") if isinstance(t, dict) else t)]
                if names:
                    allow = f"\n\n[工具白名单] 仅允许：{', '.join(names)}；超出声明范围（access/scopes）视为失败。"
            prompt = agent_prompt + allow + "\n\n---\n\n" + prompt
        base = _global_base()
        if base:
            prompt = base + "\n\n" + prompt
        _stage_event("assemble", compiled["workflow_id"], stage_id, artifacts_root,
                     True, len(prompt))

        # 步骤2：执行委托（LLM/spawn 桥接由 runner 注入）
        _stage_event("spawn", compiled["workflow_id"], stage_id, artifacts_root, True)
        try:
            deliverable = runner(prompt, stage_id)
        except Exception as e:  # noqa: BLE001 - runner 异常也要上报失败
            if not isinstance(e, GateReject):
                _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                              "node_failed", status="failed", error_code="RUNNER_ERROR")
                raise
            _stage_event("spawn_fail", compiled["workflow_id"], stage_id, artifacts_root,
                         False, note=str(e))
            state.error_log.append(f"[{stage_id}] 打回: {e}")
            _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                          "node_failed", status="failed", error_code="GATE_REJECT")
            target = _rollback_target(compiled, stage_id)
            _restore_stage(compiled, target, artifacts_root, plugin_bin)
            return state, target

        # 拒答契约（资产级）：产物即为拒答件 → 终止并上报 REFUSED
        ref = compiled.get("refusal") or {}
        ref_art = str(ref.get("artifact") or "")
        if ref_art:
            body = None
            if isinstance(deliverable, dict) and ref_art in deliverable:
                body = deliverable[ref_art]
            else:
                rp = os.path.join(artifacts_root, stage_dir, ref_art)
                if os.path.isfile(rp):
                    body = open(rp, encoding="utf-8", errors="ignore").read()
            if body is not None:
                # 拒答必须引用声明的触发条件，否则视为 runner 违约（triggers 不能只声明不读）
                triggers = [str(t) for t in (ref.get("triggers") or [])]
                text = body if isinstance(body, str) else str(body)
                if triggers and not any(t in text for t in triggers):
                    state.error_log.append(f"[{stage_id}] 拒答未引用声明触发条件：{triggers}")
                    _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                                  "node_failed", status="failed",
                                  error_code="REFUSAL_TRIGGER_INVALID")
                    target = _rollback_target(compiled, stage_id)
                    _restore_stage(compiled, target, artifacts_root, plugin_bin)
                    return state, target
                _atomic_write(os.path.join(artifacts_root, stage_dir, ref_art), text)
                _stage_event("refused", wf_id, stage_id, artifacts_root, False,
                             note=str(body)[:120])
                _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                              "node_failed", status="failed", error_code="REFUSED")
                if str(ref.get("exit") or "blocked") == "aborted":
                    state.is_frozen = True
                    state.freeze_reason = f"[{stage_id}] REFUSED(aborted)"
                return state, "__end__"

        # 步骤3：index_sync（交付物落盘；runner 返回 str=首件交付物，dict{name:content}=多件）
        outs = stage.get("output_artifacts", [])
        deliverable_path = None
        written = {}
        produced: list[dict] = []
        if outs:
            if isinstance(deliverable, dict):
                written = deliverable
            else:
                written = {outs[0]["name"]: deliverable}
            for a in outs:
                if a["name"] not in written:
                    state.error_log.append(f"[{stage_id}] WARN 交付物缺件: {a['name']}（runner 未产出）")
                    continue
                rel = os.path.join(stage_dir, f"{a['name']}_v1.{a.get('suffix', 'md')}")
                _atomic_write(os.path.join(artifacts_root, rel), written[a["name"]])
                full = os.path.join(artifacts_root, rel)
                try:
                    data = open(full, "rb").read()
                    produced.append({"storagePath": full, "deliverableType": a.get("suffix", "md"),
                                     "sha256": hashlib.sha256(data).hexdigest(),
                                     "sizeBytes": len(data)})
                except OSError:
                    produced.append({"storagePath": full, "deliverableType": a.get("suffix", "md")})
                if deliverable_path is None:
                    deliverable_path = full
            if written:
                _update_index_status(artifacts_root, stage_id, "active")

        # 交付物契约（判定产物可解析）：声明 artifact_contract 时逐字段核验
        ac = stage.get("artifact_contract") or {}
        if ac and deliverable_path:
            fmt = str(ac.get("format") or "").lower()
            bad = None
            if fmt == "json":
                try:
                    doc = json.load(open(deliverable_path, encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    bad = f"JSON 不可解析：{exc}"
                else:
                    miss = [f for f in (ac.get("fields") or []) if f not in doc]
                    if miss:
                        bad = f"缺字段 {miss}"
            if bad:
                state.error_log.append(f"[{stage_id}] 打回: 交付物契约不满足 {bad}")
                _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                              "node_failed", status="failed", error_code="ARTIFACT_CONTRACT")
                target = _rollback_target(compiled, stage_id)
                _restore_stage(compiled, target, artifacts_root, plugin_bin)
                return state, target

        # 步骤4：语义闸挂载点（gate.post 业务段，spec 由工作流声明）
        violations = _semantic_gate(stage, deliverable_path)
        if violations:
            state.error_log.append(f"[{stage_id}] 打回: 语义闸判B {violations}")
            _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                          "node_failed", status="failed", error_code="SEMANTIC_BLOCK")
            target = _rollback_target(compiled, stage_id)
            _restore_stage(compiled, target, artifacts_root, plugin_bin)
            return state, target

        # 步骤5：快照（gate.post 插件段；幂等）
        subprocess.run(
            ["python3", snapshot_cli, "snapshot", "--artifacts-root", artifacts_root,
             "--stage-dir", stage_dir, "--stage-id", stage_id, "--workflow-id", wf_id],
            capture_output=True, text=True)
        _stage_event("snapshot", wf_id, stage_id, artifacts_root, True)
        _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                      "node_end", status="completed", artifacts=produced)

        # 显式路由：末环完成→闭环清理→__end__
        nxt = _next_hop(compiled, stage_id)
        if nxt == "__end__" and stage_id in compiled["final_stages"] and compiled["cleanup_on_complete"]:
            missing = [sid for sid in compiled["stages"]
                       if not (_stage_has("assemble", wf_id, sid, artifacts_root)
                               and _stage_has("spawn", wf_id, sid, artifacts_root))]
            if missing:
                state.is_frozen = True
                state.freeze_reason = f"stage 隔离留痕缺失: {','.join(missing)}"
                return state, None
            _run_event("run_complete", wf_id, stages=len(compiled["stages"]),
                       instance_id=getattr(state, "instance_id", ""))
            _observe_emit(compiled, state, stage_id, stage.get("agent", stage_id),
                          "task_end", status="completed")
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

def _merge_branch_state(state, branch_state) -> None:
    """分支状态合流：error_log 去重合并（账本绑定已按用户裁定拆除，2026-10-15）。"""
    for e in getattr(branch_state, "error_log", []):
        if e not in state.error_log:
            state.error_log.append(e)


def make_fanout_node(layer: str, members: list, compiled: dict,
                     artifacts_root: str, plugin_bin: str,
                     runner: Callable[[str, str], str], graph_ref,
                     max_rollback: int = 3):
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
        # 并行判定是信息留痕，不是错误：写入 run 台账，避免被当作执行失败
        _run_event("fanout_decision", compiled["workflow_id"], layer=layer,
                   verdict=verdict["verdict"], via=verdict["via"], members=members)
        if verdict["verdict"] == "parallel":
            with ThreadPoolExecutor(max_workers=len(members)) as pool:
                futs = []
                for m in members:
                    node_fn = make_stage_node(m, compiled, artifacts_root, plugin_bin,
                                          runner, max_rollback=max_rollback)
                    futs.append(pool.submit(node_fn, state.model_copy(deep=True)))
                for f in futs:
                    branch_state, _ = f.result()
                    _merge_branch_state(state, branch_state)
        else:
            for m in members:  # 闸判串行/降级 → 顺序执行保语义
                node_fn = make_stage_node(m, compiled, artifacts_root, plugin_bin,
                                          runner, max_rollback=max_rollback)
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
    lb = compiled.get("loop_bounds") or {}
    max_rollback = int(lb.get("maxVerifyCycles") or lb.get("maxPlanCycles") or 3)
    i = 0
    while i < len(order):
        sid = order[i]
        if sid in member2group:
            layer = member2group[sid]
            members = sorted(groups[layer], key=lambda m: order.index(m))
            g.register_node(f"fanout_{layer}",
                            make_fanout_node(layer, members, compiled, artifacts_root,
                                             plugin_bin, runner, g, max_rollback))
            i = order.index(members[-1]) + 1  # 跳过整组（组内成员由扇出节点执行）
            continue
        g.register_node(sid, make_stage_node(sid, compiled, artifacts_root, plugin_bin,
                                            runner, max_rollback=max_rollback))
        i += 1
    g._compiled = True  # 内核接入层同包内手工编译态：本图节点已全部注册
    g._checkpointer = checkpointer
    _run_event("run_start", compiled["workflow_id"], stages=len(compiled["stages"]))
    return g
