"""能力建模 ①⑥⑦ 单测：矩阵/角色修正/冲突/三门/接线。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from engine.paradigm import capability, gates, wiring

TEMPLATES = Path.home() / ".agents" / "agent-paradigms" / "templates"
PARADIGMS = ["single_tool_call", "react", "plan_execute", "reflexion", "multi_agent"]
ROLES = ["one_shot", "long_session", "batch_job"]


def _tpl(name: str) -> dict:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


# ── ① 矩阵与角色修正 ────────────────────────────────────────────
@pytest.mark.parametrize("pid", PARADIGMS)
@pytest.mark.parametrize("role", ROLES)
def test_every_combo_derives(pid, role):
    row = capability.build(pid, role)
    p = row["capabilityProfile"]
    assert p["plan"]["mode"] in ("full", "lite", "none")
    assert p["tool"]["mode"] in ("required", "on_demand", "none")
    assert p["reflect"]["mode"] in ("forbidden", "lite", "once", "required_capped", "arbitrate_once")
    assert p["memory"]["source"] in ("paradigm", "role_override")
    assert set(p) == {"plan", "tool", "memory", "reflect"}


def test_role_override_beats_paradigm():
    row = capability.build("plan_execute", "one_shot")     # full → lite
    assert row["capabilityProfile"]["plan"]["mode"] == "lite"
    assert row["capabilityProfile"]["plan"]["source"] == "role_override"
    assert row["overrides"]


def test_long_session_forces_episodic():
    row = capability.build("react", "long_session")        # working_only → +episodic
    assert row["capabilityProfile"]["memory"]["enabledTiers"] == ["working", "episodic"]
    assert row["capabilityProfile"]["memory"]["persist"] is True


def test_batch_job_forces_retry_and_resumable():
    row = capability.build("plan_execute", "batch_job")
    p = row["capabilityProfile"]
    assert p["tool"].get("retry") is True and p["tool"].get("idempotencyKey") is True
    assert p["plan"].get("resumable") is True
    assert p["reflect"]["loop"]["maxIterations"] <= 3


def test_batch_job_alias_normalized():
    a = capability.build("react", "background_batch")
    b = capability.build("react", "batch_job")
    assert a["capabilityProfile"] == b["capabilityProfile"]


# ── 冲突裁决（§1.4 五条） ───────────────────────────────────────
def test_forbidden_single_with_reflection():
    row = capability.build("single_tool_call", "one_shot")
    row["capabilityProfile"]["reflect"]["mode"] = "lite"
    assert any("单轮工具调用 + 反思回路" in c for c in capability.conflicts(row))


def test_forbidden_memory_none_long_session():
    row = capability.build("react", "long_session")
    row["capabilityProfile"]["memory"]["enabledTiers"] = []
    assert any("记忆 none + long_session" in c for c in capability.conflicts(row))


def test_forbidden_capped_without_bounds():
    row = capability.build("reflexion", "one_shot")
    row["capabilityProfile"]["reflect"]["loop"]["maxIterations"] = 0
    assert any("required_capped" in c for c in capability.conflicts(row))


def test_forbidden_multi_agent_without_memory():
    row = capability.build("multi_agent", "long_session")
    row["capabilityProfile"]["memory"]["enabledTiers"] = []
    assert any("多 Agent + 记忆 none" in c for c in capability.conflicts(row))


def test_forbidden_tool_none_for_external_paradigm():
    row = capability.build("react", "one_shot")
    row["capabilityProfile"]["tool"]["mode"] = "none"
    assert any("工具 none" in c for c in capability.conflicts(row))


# ── ⑥ 门三 引用完整性 ───────────────────────────────────────────
def test_reference_missing_allow_actions():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["promptContract"]["allow_actions"] = []
    r = gates.run(a)
    assert any("allow_actions" in e for e in r["errors"])


def test_reference_outside_global_whitelist():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["promptContract"]["allow_actions"].append("drop_database")
    r = gates.run(a)
    assert any("全局白名单" in e for e in r["errors"])


def test_reference_tool_without_timeout():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["promptContract"]["tool_spec"][0].pop("timeoutMs")
    r = gates.run(a)
    assert any("timeoutMs" in e for e in r["errors"])


def test_reverse_coverage_is_warning():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["promptContract"]["tool_spec"] = [t for t in a["promptContract"]["tool_spec"]
                                        if t["name"] != "file_read"]
    r = gates.run(a)
    assert r["errors"] == []
    assert any("反向覆盖" in w for w in r["warnings"])


# ── ⑥ 门四 证据充分 ─────────────────────────────────────────────
def test_evidence_single_exempted_to_one():
    a = copy.deepcopy(_tpl("01_single_tool_call.json"))
    a["promptContract"]["few_shot_examples"] = a["promptContract"]["few_shot_examples"][:1]
    a["promptContract"]["fewShotExemption"] = {"allowed": True, "reason": "单轮场景样例可 1 条"}
    r = gates.run(a)
    assert not any("Few-shot" in e for e in r["errors"])


def test_evidence_react_requires_two():
    a = copy.deepcopy(_tpl("02_react.json"))
    a["promptContract"]["few_shot_examples"] = a["promptContract"]["few_shot_examples"][:1]
    r = gates.run(a)
    assert any("Few-shot" in e for e in r["errors"])


def test_evidence_bound_over_five():
    a = copy.deepcopy(_tpl("04_reflexion.json"))
    a["capabilityProfile"]["capabilityProfile"]["reflect"]["loop"]["maxIterations"] = 6
    r = gates.run(a)
    assert any("超过硬线 5" in e for e in r["errors"])


def test_evidence_bound_zero_rejected():
    a = copy.deepcopy(_tpl("04_reflexion.json"))
    a["capabilityProfile"]["capabilityProfile"]["reflect"]["loop"]["maxIterations"] = 0
    r = gates.run(a)
    assert any("正整数" in e for e in r["errors"])


# ── ⑥ 门五 一致性 ───────────────────────────────────────────────
def test_consistency_profile_mismatch():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["capabilityProfile"]["capabilityProfile"]["plan"]["mode"] = "none"
    r = gates.run(a)
    assert any("能力与矩阵/角色不符" in e for e in r["errors"])


def test_consistency_long_session_requires_persist():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["capabilityProfile"]["capabilityProfile"]["memory"]["persist"] = False
    a["capabilityProfile"]["capabilityProfile"]["memory"]["enabledTiers"] = ["working"]
    r = gates.run(a)
    assert any("persist" in e for e in r["errors"])


def test_consistency_output_contract_required():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["controlLists"]["ioConstraints"]["provenanceRequired"] = []
    r = gates.run(a)
    assert any("溯源" in e for e in r["errors"])


# ── ⑦ 接线：报告 + fail-closed ──────────────────────────────────
def test_wiring_report_non_strict_warns(monkeypatch, tmp_path):
    monkeypatch.setattr(wiring, "REPORT_FILE", tmp_path / "w.json")
    r = wiring.check(_tpl("03_plan_execute.json"), strict=False)
    assert r["code"] == 2 and r["blocking"]


def test_wiring_strict_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(wiring, "REPORT_FILE", tmp_path / "w.json")
    r = wiring.check(_tpl("03_plan_execute.json"), strict=True)
    assert r["code"] == 1 and r["verdict"] == "FAIL"


def test_failclosed_tool_call():
    wl = ["file_read", "script_run"]
    assert wiring.check_tool_call("file_read", allow_actions=["file_read"], whitelist=wl)["allow"]
    assert not wiring.check_tool_call("drop_db", allow_actions=["drop_db"], whitelist=wl)["allow"]
    assert not wiring.check_tool_call("script_run", allow_actions=["file_read"], whitelist=wl)["allow"]


def test_failclosed_plan_missing():
    assert wiring.check_plan(None)["code"] == "FAIL_DECLARED_NOT_CONSUMED"
    assert wiring.check_plan([{"id": "t1"}])["allow"]


def test_failclosed_memory_snapshot(tmp_path):
    assert wiring.check_memory_snapshot(None, persist=False)["allow"]
    assert not wiring.check_memory_snapshot(None, persist=True)["allow"]
    assert wiring.check_memory_snapshot(str(tmp_path), persist=True)["allow"]


def test_failclosed_reflect_limit():
    assert wiring.check_reflect_iteration(5, 5)["allow"]
    r = wiring.check_reflect_iteration(6, 5)
    assert not r["allow"] and r["code"] == "REFLECT_LIMIT_EXCEEDED"
    assert not wiring.check_reflect_iteration(1, 0)["allow"]


# ── F-7：禁止组合标签单源（2026-11-10）────────────────────────────
def test_forbidden_combos_labels_are_implemented():
    from engine.paradigm import capability as C
    labels = (C.spec.load().get("forbiddenCombos") or [])
    assert labels and all(lb in C._combo_rules() for lb in labels)


def test_forbidden_combo_drift_is_reported(monkeypatch):
    from engine.paradigm import capability as C
    orig = C.spec.load()

    def fake_load(force=False):
        d = dict(orig)
        d["forbiddenCombos"] = list(orig["forbiddenCombos"]) + ["未实现的新组合 + x"]
        return d

    monkeypatch.setattr(C.spec, "load", fake_load)
    row = C.derive("react", "one_shot")
    errs = C.conflicts(row)
    assert any("规则未实现" in e for e in errs)
