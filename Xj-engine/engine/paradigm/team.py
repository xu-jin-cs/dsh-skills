"""单多决策：①数角色 ②看并行 ③看契约 ④三件套 ⑤单路径 ⑥多路径 ⑦异常。

并行判定遵循既有「并行闸」（dispatch_switch）的逻辑轴：
  units（无依赖单元数）/ files（有效文件数）/ coupled（是否共享可变状态）/ baseline / depReason
本模块只做**拓扑预检**，给出与闸同构的 A(parallel) / B(sequential) 预判与依据；
真正派发时仍以 `dispatch_switch.py` 为准，二者不一致记 mismatch（防两套口径）。
"""
from __future__ import annotations

import re

from . import spec

LIGHT_TITLES = re.compile(r"工具|服务节点|临时|proxy|cache")
# 人工兜底/交接目标不是 Agent（无调度入口），不计入 agentCount
HUMAN_IDS = {"human", "user", "manual", "human_operator", "operator"}


# ── ① 数角色 ────────────────────────────────────────────────────
def count_agents(asset: dict) -> dict:
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    counted, excluded, seen = [], [], set()
    for n in nodes:
        aid = n.get("agentId")
        if not aid:
            excluded.append({"nodeId": n.get("nodeId"), "reason": "缺 agentId"})
            continue
        if str(aid).lower() in HUMAN_IDS:
            excluded.append({"nodeId": n.get("nodeId"), "reason": "人工兜底节点（非 Agent）"})
            continue
        if n.get("disabled") is True:
            excluded.append({"nodeId": n.get("nodeId"), "reason": "disabled"})
            continue
        if n.get("deliverableType") == "none" and LIGHT_TITLES.search(n.get("title") or ""):
            excluded.append({"nodeId": n.get("nodeId"), "reason": "工具/服务节点（无交付物）"})
            continue
        if aid in seen:
            excluded.append({"nodeId": n.get("nodeId"), "reason": f"重复 agentId（{aid}）"})
            continue
        seen.add(aid)
        counted.append(aid)
    team_roles = (asset.get("orchestration") or {}).get("teamRoles") or []
    roles = [r.get("role") for r in team_roles if r.get("agentId") in seen] or counted
    return {"agentCount": len(counted), "distinctAgentIds": counted,
            "agentRoles": roles, "countSource": "teamRoles" if team_roles else "pipeline_nodes",
            "excluded": excluded}


# ── ② 看并行（与并行闸同轴） ────────────────────────────────────
def detect_parallel(asset: dict) -> dict:
    orch = asset.get("orchestration") or {}
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    groups: list[dict] = []
    seen_ids: set[str] = set()
    for g in orch.get("parallelGroups") or []:
        members = [m for m in (g.get("nodes") or []) if m]
        if len(members) >= 2:
            groups.append({"groupId": g.get("id"), "agents": _agents_of(nodes, members),
                           "parallelType": _ptype(nodes, members)})
            seen_ids |= set(members)
    # 节点级 parallelGroup（未写 groups 清单也认）
    by_group: dict[str, list[str]] = {}
    for n in nodes:
        gid = n.get("parallelGroup")
        if gid and n.get("nodeId") not in seen_ids:
            by_group.setdefault(gid, []).append(n.get("nodeId"))
    for gid, members in by_group.items():
        if len(members) >= 2:
            groups.append({"groupId": gid, "agents": _agents_of(nodes, members),
                           "parallelType": _ptype(nodes, members)})
    # inParallel 标记
    flagged = [n.get("nodeId") for n in nodes if n.get("inParallel") is True]
    if len(flagged) >= 2:
        groups.append({"groupId": "inParallel", "agents": _agents_of(nodes, flagged),
                       "parallelType": _ptype(nodes, flagged)})
    for g in groups:
        g["agentParallel"] = len(set(g["agents"])) >= 2
    agent_groups = [g for g in groups if g["agentParallel"]]
    task_groups = [g for g in groups if not g["agentParallel"]]
    return {"hasParallel": bool(agent_groups), "parallelGroups": agent_groups,
            "taskParallelGroups": task_groups,
            "allGroups": groups}


def _agents_of(nodes: list[dict], ids: list[str]) -> list[str]:
    m = {n.get("nodeId"): n.get("agentId") for n in nodes}
    return [m.get(i) for i in ids if m.get(i)]


def _ptype(nodes: list[dict], ids: list[str]) -> str:
    a = _agents_of(nodes, ids)
    return "task_parallel" if len(set(a)) == 1 else "data_parallel"


# ── ③ 看契约 ────────────────────────────────────────────────────
def contracts(asset: dict) -> dict:
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    by_id = {n.get("nodeId"): n for n in nodes}
    rows, errors, warns = [], [], []
    for e in (asset.get("stateContract") or {}).get("edges") or []:
        f, t = e.get("from"), e.get("to")
        fields = e.get("fields") or []
        env = e.get("envelopeSchema") or {}
        name = e.get("interfaceName") or f"{f}_to_{t}"
        if not fields:
            errors.append(f"{name}: 缺 inFields/outFields（edges[].fields 为空）")
        types = {k: v for k, v in env.items() if isinstance(v, str)}
        if fields and not types:
            warns.append(f"{name}: 字段缺类型（envelopeSchema 未给类型）")
        if not e.get("validationRule"):
            warns.append(f"{name}: 缺 validationRule（取值未做格式/范围/枚举校验）")
        down_in = set((by_id.get(t) or {}).get("stateIn") or [])
        miss = [x for x in fields if down_in and x not in down_in]
        if miss:
            errors.append(f"{name}: 下游 {t} 不接受字段 {miss}（schema 不对齐）")
        rows.append({"interfaceName": name, "fromAgent": f, "toAgents": [t],
                     "inFields": fields, "outFields": fields,
                     "types": types, "hasValidation": bool(e.get("validationRule")),
                     "downstreamAccepted": not miss})
    if not rows:
        errors.append("契约缺失：stateContract.edges 为空（多 Agent 必须声明接口契约）")
    return {"contracts": rows, "errors": errors, "warnings": warns}


# ── ④ 三件套 ────────────────────────────────────────────────────
def three_piece(asset: dict, agents: dict, par: dict, con: dict) -> dict:
    errors, warns = [], []
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    roles = (asset.get("orchestration") or {}).get("teamRoles") or []
    declared_ids = {r.get("agentId") for r in roles}
    # 角色套件（单 Agent 路径不要求 teamRoles）
    if agents["agentCount"] > 1 and len(declared_ids) < agents["agentCount"]:
        missing = sorted(set(agents["distinctAgentIds"]) - declared_ids)
        errors.append(f"角色套件不完整：缺 {missing} 的 role/goal/capability 定义")
    if agents["agentCount"] > 1:
        for r in roles:
            for k in ("role", "goal", "capability"):
                if not r.get(k):
                    errors.append(f"角色套件不完整：{r.get('agentId')} 缺 {k}")
    # 流程套件
    if agents["agentCount"] > 1 and not par["hasParallel"]:
        if not ((asset.get("orchestration") or {}).get("parallelDecision") or {}).get("depReason"):
            errors.append("流程套件不完整：多 Agent 串行必须声明 parallelDecision.depReason"
                          "（并行闸 B 档同口径）")
    if agents["agentCount"] > 1 and not any(n.get("dependsOn") for n in nodes):
        errors.append("流程套件不完整：无任何 dependsOn（缺少依赖/顺序）")
    # 契约套件
    if agents["agentCount"] > 1:
        errors.extend(con["errors"])
    # 一致性
    if agents["agentCount"] > 1 and par["hasParallel"]:
        for g in par["parallelGroups"]:
            if len(set(g["agents"])) < 2 and g["parallelType"] == "data_parallel":
                warns.append(f"并行组 {g.get('groupId')} 实际只有 1 个 Agent（按任务并行处理）")
    # 孤立节点（无依赖且无出边，且非首节点）
    ids = [n.get("nodeId") for n in nodes]
    has_out = {d for n in nodes for d in (n.get("dependsOn") or [])}
    for n in nodes:
        nid = n.get("nodeId")
        if nid not in has_out and (n.get("dependsOn") or []) == [] and ids and nid != ids[0]:
            warns.append(f"孤立节点：{nid} 既无前序也无后继（未被流程连接）")
    # 死循环（依赖环）
    if _has_cycle(nodes):
        errors.append("流程套件死循环：dependsOn 存在环且无退出条件")
    return {"rolesComplete": not any("角色套件" in e for e in errors),
            "flowComplete": not any("流程套件" in e for e in errors),
            "contractComplete": not any("契约" in e for e in errors),
            "errors": errors, "warnings": warns}


def _has_cycle(nodes: list[dict]) -> bool:
    graph = {n.get("nodeId"): list(n.get("dependsOn") or []) for n in nodes}
    state: dict[str, int] = {}

    def dfs(u: str) -> bool:
        if state.get(u) == 1:
            return True
        if state.get(u) == 2:
            return False
        state[u] = 1
        for v in graph.get(u, []):
            if v in graph and dfs(v):
                return True
        state[u] = 2
        return False

    return any(dfs(u) for u in graph)


# ── ② 并行闸同轴预判 ────────────────────────────────────────────
def parallel_precheck(asset: dict, agents: dict, par: dict) -> dict:
    all_groups = par.get("allGroups") or par["parallelGroups"]
    units = max([len(g.get("agents") or []) for g in all_groups] + [1])
    nodes = (asset.get("pipeline") or {}).get("nodes") or []
    files = len({n.get("deliverable") for n in nodes if n.get("deliverable")})
    coupled = any(len(e.get("fields") or []) and len(
        {n.get("agentId") for n in nodes if n.get("nodeId") in (e.get("from"), e.get("to"))}) > 1
        for e in (asset.get("stateContract") or {}).get("edges") or [])
    pd = (asset.get("orchestration") or {}).get("parallelDecision") or {}
    dep_reason = pd.get("depReason", "")
    dep_type = pd.get("depType", "")
    can_parallel = units >= 2 and bool(all_groups) and (
        not coupled or dep_type == "contract")
    decision = "A_parallel" if can_parallel else "B_sequential"
    reasons = [f"units={units}", f"files={files}", f"coupled={coupled}",
               f"depType={dep_type or '-'}",
               f"agentParallel={par['hasParallel']}"]
    warnings: list[str] = []
    if decision == "B_sequential":
        if agents["agentCount"] > 1 and not dep_reason:
            warnings.append("B 档多 Agent 串行缺 depReason（并行闸要求）")
        elif units >= 2 and not dep_reason:
            warnings.append("有 ≥2 独立单元但判 B：需 depReason，或冻结契约后用 depType=contract 走 A")
    return {"decision": decision, "units": units, "files": files, "coupled": coupled,
            "depReason": dep_reason, "reasons": reasons, "warnings": warnings,
            "authority": "dispatch_switch.py（派发时以闸为准；此处仅拓扑预检）"}


# ── ⑦ 异常 ──────────────────────────────────────────────────────
def exceptions(asset: dict, agents: dict, par: dict, con: dict, three: dict) -> list[dict]:
    out: list[dict] = []
    if agents["agentCount"] == 0:
        out.append({"type": "count_zero", "level": "block",
                    "message": "agentCount=0，必须至少有一个主 Agent",
                    "action": "route_to_human"})
    roles = (asset.get("orchestration") or {}).get("teamRoles") or []
    role_ids = [r.get("agentId") for r in roles]
    if len(role_ids) != len(set(role_ids)):
        out.append({"type": "count_duplicate", "level": "warn",
                    "message": "teamRoles 中 agentId 重复声明，已按首个定义计数",
                    "action": "record"})
    if agents["agentCount"] > 1 and not con["contracts"]:
        out.append({"type": "contract_missing", "level": "block",
                    "message": "Agent 之间缺少 inFields/outFields 定义", "action": "route_to_human"})
    if agents["agentCount"] > 1 and not ((asset.get("orchestration") or {}).get("teamRoles")):
        out.append({"type": "role_kit_missing", "level": "block",
                    "message": "缺少角色套件（teamRoles）", "action": "route_to_human"})
    if _has_cycle((asset.get("pipeline") or {}).get("nodes") or []):
        out.append({"type": "dead_loop", "level": "block",
                    "message": "依赖环无退出条件", "action": "block"})
    if agents["agentCount"] == 1 and par["hasParallel"]:
        out.append({"type": "parallel_conflict", "level": "block",
                    "message": "单 Agent 却声明了并行组（路径冲突）", "action": "clarify"})
    for e in three["errors"]:
        if "死循环" not in e and "契约" not in e and "角色套件" not in e:
            out.append({"type": "three_piece", "level": "block", "message": e,
                        "action": "block"})
    return out


# ── 汇总：路径判定 ──────────────────────────────────────────────
def analyze(asset: dict) -> dict:
    agents = count_agents(asset)
    par = detect_parallel(asset)
    con = contracts(asset)
    three = three_piece(asset, agents, par, con)
    pre = parallel_precheck(asset, agents, par)
    exc = exceptions(asset, agents, par, con, three)
    for w in pre["warnings"]:
        exc.append({"type": "parallel_decision", "level": "warn",
                    "message": w, "action": "record"})

    if agents["agentCount"] == 0:
        path = "blocked"
    elif agents["agentCount"] == 1 and not par["hasParallel"]:
        path = "single_agent"
    elif agents["agentCount"] == 1 and par["hasParallel"]:
        path = "blocked"
    elif par["hasParallel"]:
        path = "multi_agent"
    else:
        path = "multi_agent_serial"

    orch = asset.get("orchestration") or {}
    out = {
        "path": path,
        "agents": agents,
        "parallel": par,
        "precheck": pre,
        "contracts": con,
        "threePiece": three,
        "exceptions": exc,
        "singleAgent": ({"path": "single_agent", "topology": "serial_chain",
                         "parallelAllowed": False, "multiAgentRoutingAllowed": False}
                        if path == "single_agent" else None),
        "multiAgent": ({"path": "multi_agent",
                        "stages": ["distribute", "parallel", "aggregate"],
                        "distributor": (min(agents["distinctAgentIds"], key=len)
                                        if agents["distinctAgentIds"] else None),
                        "parallelGroups": [g["groupId"] for g in par["parallelGroups"]],
                        "aggregator": (orch.get("parallelDecision") or {}).get("aggregator"),
                        "contracts": [c["interfaceName"] for c in con["contracts"]]}
                       if path.startswith("multi_agent") else None),
        "ok": not any(e["level"] == "block" for e in exc) and not three["errors"],
    }
    out["code"] = 0 if out["ok"] and not three["warnings"] else (1 if not out["ok"] else 2)
    out["verdict"] = {0: "PASS", 1: "FAIL", 2: "WARN"}[out["code"]]
    out["paradigmVersion"] = spec.paradigm_version()
    return out
