"""模板三门串行校验（唯一实现）。

门一 schema 静态校验：字段/嵌套/枚举 + 范式一致性 + 版本绑定（P0）
门二 需求三件套：需求定义 / 方案路径 / 交付物契约（缺失 P0；表述不可验证 P1）
门三 反思与资源上界（P0）

返回码：0 全通过｜1 存在 P0｜2 仅 P1（等待人工确认）
"""
from __future__ import annotations

import re

from . import spec

VAGUE = re.compile(r"良好|差不多|尽快|适当|合理|优质|高效|尽快完成|自行把握|视情况")
LIGHT = {"single_tool_call", "react"}
CONJ = re.compile(r"[和并再以及同]")
TEST_PREFIX = re.compile(r"^\s*(python3|python|pytest|curl|wget|grep|test|sh|bash|node|npm|npx|jq|git|ruff|mypy|tsc)\b")


def _gate_schema(asset: dict, schema: dict, expected: str | None) -> tuple[list, list]:
    errors, warns = [], []
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema 不可用，无法执行 schema 静态校验（禁止当作通过）"], []
    try:
        jsonschema.validate(asset, schema)
    except jsonschema.ValidationError as e:
        errors.append(f"schema: {e.message} @ {'/'.join(str(p) for p in e.absolute_path)}")

    meta = asset.get("meta") or {}
    pid = meta.get("paradigm")
    if expected and pid and pid != expected:
        errors.append(f"范式不一致：模板 meta.paradigm={pid!r}，选型结果={expected!r}")
    ver = meta.get("paradigmVersion")
    cur = spec.paradigm_version()
    if ver != cur:
        errors.append(f"版本不匹配：模板 paradigmVersion={ver!r}，当前范式层={cur!r}"
                      "（旧模板禁止静默失效）")
    errors.extend(_static_structure(asset, schema))
    return errors, warns


def _static_structure(asset: dict, schema: dict) -> list[str]:
    """结构化静态校验（原子三判据 / 编排声明一致 / 状态契约 / 段数口径）。"""
    v: list[str] = []
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    ids = [n.get("nodeId") for n in nodes]
    idset = set(ids)
    if len(ids) != len(idset):
        v.append("pipeline.nodes: nodeId 重复")
    id2 = {n.get("nodeId"): n for n in nodes}

    for n in nodes:
        for dep in n.get("dependsOn") or []:
            if dep not in idset:
                v.append(f"pipeline.nodes.{n.get('nodeId')}: dependsOn 不存在 {dep}")
        if n.get("mode") == "optional_parallel" and not n.get("parallelGroup"):
            v.append(f"pipeline.nodes.{n.get('nodeId')}: optional_parallel 缺 parallelGroup")
        if n.get("mode") == "fallback_hook":
            fo = n.get("fallbackOf")
            if not fo:
                v.append(f"pipeline.nodes.{n.get('nodeId')}: fallback_hook 缺 fallbackOf")
            elif fo not in idset:
                v.append(f"pipeline.nodes.{n.get('nodeId')}: fallbackOf 指向不存在 {fo}")

    orch = asset.get("orchestration") or {}
    decl = orch.get("declared") or []
    dmap = {d.get("nodeId"): d for d in decl}
    for nid in idset - set(dmap):
        v.append(f"orchestration.declared: 漏声明节点 {nid}")
    for nid in set(dmap) - idset:
        v.append(f"orchestration.declared: 多声明不存在节点 {nid}")
    for nid, d in dmap.items():
        node = id2.get(nid) or {}
        if d.get("mode") and node.get("mode") and d["mode"] != node["mode"]:
            v.append(f"orchestration.declared.{nid}: mode 与节点声明不一致")
    for g in orch.get("parallelGroups") or []:
        for nid in g.get("nodes") or []:
            if nid not in idset:
                v.append(f"orchestration.parallelGroups.{g.get('id')}: 节点不存在 {nid}")

    for e in (asset.get("stateContract") or {}).get("edges") or []:
        f, t = e.get("from"), e.get("to")
        if f not in idset or t not in idset:
            v.append(f"stateContract.edge: 节点不存在 {f}->{t}")
            continue
        out_fields = set(id2[f].get("stateOut") or [])
        for fld in e.get("fields") or []:
            if out_fields and fld not in out_fields:
                v.append(f"stateContract {f}->{t}: 字段 {fld} 不在 {f}.stateOut")

    for t in asset.get("atomicTasks") or []:
        verb = t.get("verb") or ""
        if CONJ.search(verb):
            v.append(f"atomicTasks.{t.get('id')}: verb 含并列连词（{verb}）→ 必须一件事一动词")
        cmd = (t.get("unitTest") or {}).get("command") or ""
        if not TEST_PREFIX.match(cmd):
            v.append(f"atomicTasks.{t.get('id')}: unitTest.command 不是可执行入口（{cmd[:40]}）")

    reg_pid = (((asset.get("registration") or {}).get("observe") or {}).get("paradigm") or {}).get("id")
    if reg_pid and reg_pid != (asset.get("meta") or {}).get("paradigm"):
        v.append(f"registration.observe.paradigm.id={reg_pid!r} 与 meta.paradigm 不一致")

    req_sec = list(((spec.load().get("paradigms") or [{}])[0].get("requiredSections") or []))
    schema_req = list(schema.get("required") or [])
    if req_sec != schema_req:
        v.append(f"段数口径不一致：paradigms.requiredSections={len(req_sec)} vs schema.required={len(schema_req)}")
    miss = [k for k in schema_req if k not in asset]
    if miss:
        v.append(f"缺段：{miss}")
    return v


def _gate_three_piece(asset: dict) -> tuple[list, list]:
    errors, warns = [], []
    need = (asset.get("scenario") or {}).get("naturalLanguage") or ""
    path = (asset.get("pipeline") or {}).get("nodes") or []
    anchor = (((asset.get("deliverables") or {}).get("primary") or {}).get("acceptanceAnchor") or "")

    if not str(need).strip():
        errors.append("三件套缺失：需求定义（scenario.naturalLanguage）为空")
    if not path:
        errors.append("三件套缺失：方案路径（pipeline.nodes）为空")
    if not str(anchor).strip():
        errors.append("三件套缺失：交付物契约（deliverables.primary.acceptanceAnchor）为空")

    if str(need).strip() and len(str(need).strip()) < 10:
        warns.append("需求定义过短（<10 字符）：可能缺少可验证上下文")
    if str(anchor).strip():
        if len(str(anchor).strip()) < 8:
            warns.append("交付物契约过短（<8 字符）：无法作为验收锚点")
        if VAGUE.search(str(anchor)):
            warns.append("交付物契约含模糊词（良好/尽快/合理…）：不可机械复判")
    return errors, warns


def _gate_bounds(asset: dict) -> tuple[list, list]:
    errors, warns = [], []
    pid = (asset.get("meta") or {}).get("paradigm")
    orch = asset.get("orchestration") or {}
    loop = orch.get("loop")
    cap_rounds = int(spec.bounds_cfg().get("maxMessageRounds", 100))

    if pid == "reflexion":
        if not isinstance(loop, dict):
            errors.append("reflexion 缺少 orchestration.loop：反思无上限")
        else:
            if loop.get("purpose") != "reflection":
                errors.append("reflexion 的 loop.purpose 必须是 reflection")
            if not (isinstance(loop.get("maxIterations"), int) and loop["maxIterations"] >= 1):
                errors.append("reflexion 缺少 maxIterations（或 <1）")
            if not (isinstance(loop.get("maxTokensPerTurn"), int) and loop["maxTokensPerTurn"] > 0):
                errors.append("reflexion 缺少 maxTokensPerTurn（单轮 token 上限）")
            if not (isinstance(loop.get("maxDurationSec"), int) and loop["maxDurationSec"] > 0):
                errors.append("reflexion 缺少 maxDurationSec（总执行时长上限）")

    if pid in LIGHT and isinstance(loop, dict) and loop.get("purpose") == "reflection":
        errors.append(f"{pid} 是轻范式，禁止配置反思回路（loop.purpose=reflection）")

    if pid == "multi_agent":
        roles = {n.get("agentId") for n in (asset.get("pipeline") or {}).get("nodes") or []}
        if len(roles) < 2:
            errors.append(f"multi_agent 角色数不足：{len(roles)}（需 ≥2）")
        mr = orch.get("maxMessageRounds")
        if not isinstance(mr, int) or mr <= 0:
            errors.append("multi_agent 缺少 maxMessageRounds（禁止无边界广播调度）")
        elif mr > cap_rounds:
            errors.append(f"maxMessageRounds={mr} 超过上限 {cap_rounds}")
    return errors, warns


def run(asset: dict, *, expected: str | None = None) -> dict:
    schema = spec.schema()
    e1, w1 = _gate_schema(asset, schema, expected)
    e2, w2 = _gate_three_piece(asset)
    e3, w3 = _gate_bounds(asset)
    errors = e1 + e2 + e3
    warnings = w1 + w2 + w3
    code = 1 if errors else (2 if warnings else 0)
    return {"code": code,
            "verdict": {1: "FAIL", 2: "WARN", 0: "PASS"}[code],
            "errors": errors, "warnings": warnings,
            "gates": {"schema": {"errors": e1, "warnings": w1},
                      "threePiece": {"errors": e2, "warnings": w2},
                      "bounds": {"errors": e3, "warnings": w3}},
            "paradigmVersion": spec.paradigm_version()}
