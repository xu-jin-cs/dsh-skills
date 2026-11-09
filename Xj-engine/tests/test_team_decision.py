"""单多决策七步单测：数角色 / 看并行 / 看契约 / 三件套 / 路径 / 并行闸同轴预判 / 异常。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from engine.paradigm import team

T = Path.home() / ".agents" / "agent-paradigms" / "templates"


def _tpl(name: str) -> dict:
    return json.loads((T / name).read_text(encoding="utf-8"))


# ── ① 数角色 ────────────────────────────────────────────────────
def test_count_excludes_human_and_disabled():
    a = _tpl("05_multi_agent.json")
    assert team.count_agents(a)["agentCount"] == 5          # human 不计
    a["pipeline"]["nodes"][1]["disabled"] = True
    assert team.count_agents(a)["agentCount"] == 4


def test_count_zero_blocks():
    a = _tpl("03_plan_execute.json")
    for n in a["pipeline"]["nodes"]:
        n["agentId"] = "human"                              # 全被排除
    res = team.analyze(a)
    assert res["agents"]["agentCount"] == 0 and res["path"] == "blocked"


def test_count_reports_roles():
    a = _tpl("05_multi_agent.json")
    c = team.count_agents(a)
    assert c["countSource"] == "teamRoles"
    assert "编排员" in c["agentRoles"] and "orchestrator" in c["distinctAgentIds"]


# ── ② 看并行 ────────────────────────────────────────────────────
def test_parallel_agent_group_detected():
    p = team.detect_parallel(_tpl("05_multi_agent.json"))
    assert p["hasParallel"] is True and p["parallelGroups"][0]["agentParallel"] is True


def test_task_parallel_not_counted_as_agent_parallel():
    p = team.detect_parallel(_tpl("03_plan_execute.json"))
    assert p["hasParallel"] is False
    assert len(p["taskParallelGroups"]) >= 1


def test_inparallel_flag_detected():
    a = _tpl("03_plan_execute.json")
    a["pipeline"]["nodes"][1]["inParallel"] = True
    a["pipeline"]["nodes"][2]["inParallel"] = True
    a["pipeline"]["nodes"][1]["agentId"] = "a1"
    a["pipeline"]["nodes"][2]["agentId"] = "a2"
    p = team.detect_parallel(a)
    assert any(g["groupId"] == "inParallel" for g in p["allGroups"])


# ── ③ 看契约 ────────────────────────────────────────────────────
def test_contract_missing_edges_blocks():
    a = _tpl("05_multi_agent.json")
    a["stateContract"]["edges"] = []
    c = team.contracts(a)
    assert any("契约缺失" in e for e in c["errors"])


def test_contract_downstream_mismatch_blocks():
    a = _tpl("05_multi_agent.json")
    a["pipeline"]["nodes"][3]["stateIn"] = []                # n4 不再接受上游字段
    c = team.contracts(a)
    assert any("不接受字段" in e for e in c["errors"])


def test_contract_missing_validation_is_warning():
    a = _tpl("05_multi_agent.json")
    for e in a["stateContract"]["edges"]:
        e.pop("validationRule", None)
    c = team.contracts(a)
    assert c["errors"] == [] and any("validationRule" in w for w in c["warnings"])


# ── ④ 三件套 ────────────────────────────────────────────────────
def test_three_piece_requires_team_roles():
    a = _tpl("05_multi_agent.json")
    a["orchestration"].pop("teamRoles")
    res = team.analyze(a)
    assert res["path"].startswith("multi") and not res["threePiece"]["rolesComplete"]
    assert any(e["type"] == "role_kit_missing" for e in res["exceptions"])


def test_three_piece_requires_dep_reason_for_serial_multi():
    a = _tpl("04_reflexion.json")
    a["orchestration"].pop("parallelDecision")
    res = team.analyze(a)
    assert any("depReason" in e for e in res["threePiece"]["errors"])


def test_three_piece_detects_cycle():
    a = _tpl("05_multi_agent.json")
    a["pipeline"]["nodes"][0]["dependsOn"] = ["n4"]          # n1 ← n4 形成环
    res = team.analyze(a)
    assert any(e["type"] == "dead_loop" for e in res["exceptions"])


def test_three_piece_isolated_node_warns():
    a = _tpl("05_multi_agent.json")
    a["pipeline"]["nodes"].append({
        "nodeId": "n9", "title": "孤立节点", "agentId": "role_a", "dependsOn": [],
        "mode": "required_serial", "deliverable": "x", "acceptance": "无",
        "stateIn": [], "stateOut": ["x"]})
    res = team.analyze(a)
    assert any("孤立节点" in w for w in res["threePiece"]["warnings"])


# ── ⑤⑥ 路径分流 ─────────────────────────────────────────────────
def test_path_single_agent():
    res = team.analyze(_tpl("03_plan_execute.json"))
    assert res["path"] == "single_agent"
    assert res["singleAgent"] == {"path": "single_agent", "topology": "serial_chain",
                                  "parallelAllowed": False, "multiAgentRoutingAllowed": False}


def test_path_multi_serial():
    res = team.analyze(_tpl("04_reflexion.json"))
    assert res["path"] == "multi_agent_serial"


def test_path_multi_parallel_has_three_stages():
    res = team.analyze(_tpl("05_multi_agent.json"))
    assert res["path"] == "multi_agent"
    assert res["multiAgent"]["stages"] == ["distribute", "parallel", "aggregate"]
    assert res["multiAgent"]["aggregator"] == "orchestrator"


# ── 并行闸同轴预判 ──────────────────────────────────────────────
def test_precheck_a_when_contract_frozen():
    res = team.analyze(_tpl("05_multi_agent.json"))
    assert res["precheck"]["decision"] == "A_parallel"
    assert res["precheck"]["depType"] == "contract"
    assert res["precheck"]["authority"].startswith("dispatch_switch.py")


def test_precheck_b_without_dep_reason_warns():
    a = _tpl("04_reflexion.json")
    a["orchestration"].pop("parallelDecision")
    res = team.analyze(a)
    assert res["precheck"]["decision"] == "B_sequential"
    assert any(e["type"] == "parallel_decision" for e in res["exceptions"])


# ── ⑦ 异常分类 ──────────────────────────────────────────────────
def test_exception_parallel_conflict_single_agent():
    a = _tpl("03_plan_execute.json")
    for n in a["pipeline"]["nodes"][1:3]:
        n["agentId"] = "other"
    res = team.analyze(a)
    assert res["agents"]["agentCount"] > 1          # 不再是单 Agent
    assert res["path"].startswith("multi")


def test_exception_contract_missing_routes_to_human():
    a = _tpl("05_multi_agent.json")
    a["stateContract"]["edges"] = []
    res = team.analyze(a)
    ex = next(e for e in res["exceptions"] if e["type"] == "contract_missing")
    assert ex["level"] == "block" and ex["action"] == "route_to_human"
