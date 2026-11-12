"""资产判定口径层 → 引擎功能支撑回归（2026-11-12）。

覆盖：input_boundary 熔断、refusal 终止、artifact_contract 打回、loop_bounds 透传。
"""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.flow.workflow_builder import build_workflow  # noqa: E402
from engine.flow.workflow_compiler import (  # noqa: E402
    build_flow_graph, compile_workflow_json,
)
from engine.flow.integration import build_initial_state  # noqa: E402

PLUGIN = os.path.expanduser(
    "~/.zcode/workspace/default/plugins/stage-context-isolation/bin")
pytestmark = pytest.mark.skipif(not os.path.isdir(PLUGIN), reason="plugin missing")


def _run(tmp_path, monkeypatch, spec, runner):
    wp = tmp_path / "wf"
    build_workflow(spec, str(wp), PLUGIN)
    sl, rl = tmp_path / "s.jsonl", tmp_path / "r.jsonl"
    monkeypatch.setenv("STAGE_ISOLATION_LEDGER", str(sl))
    monkeypatch.setenv("ENGINE_FLOW_RUN_LEDGER", str(rl))
    c = compile_workflow_json(str(wp / "workflow.json"))
    g = build_flow_graph(c, str(wp / "project_artifacts"), PLUGIN, runner)
    st = g.execute(build_initial_state(instance_id="t", project_name="t",
                                       evidence_root=str(tmp_path / "ev")),
                   start_node=c["topo_order"][0])
    return c, st, sl


def _spec(**extra):
    s = {"workflow_id": "judge", "stages": [
        {"stage_id": "a", "agent": "a", "depends_on": [],
         "output_artifacts": [{"name": "a", "suffix": "md"}]},
    ]}
    s.update(extra)
    return s


def test_input_boundary_freezes(tmp_path, monkeypatch):
    c, st, _ = _run(tmp_path, monkeypatch,
                    _spec(input_boundary={"accepts": ["x"], "rejects": ["y"], "maxInputChars": 1}),
                    lambda p, s: "ok")
    assert st.is_frozen and "INPUT_BOUNDARY" in (st.freeze_reason or "")
    assert any("输入超界" in e for e in st.error_log)


def test_refusal_artifact_terminates(tmp_path, monkeypatch):
    c, st, sl = _run(tmp_path, monkeypatch,
                     _spec(refusal={"triggers": ["out_of_scope"],
                                    "artifact": "refusal.md", "exit": "blocked"}),
                     lambda p, s: {"refusal.md": "# 拒答\n触发条件：out_of_scope"})
    assert not st.is_frozen
    assert (tmp_path / "wf" / "project_artifacts" / "01_a" / "refusal.md").is_file()
    events = [json.loads(l)["event"] for l in open(sl, encoding="utf-8") if l.strip()]
    assert "refused" in events
    assert "snapshot" not in events      # 拒答后不进入快照/收口
    assert not any("node_end" in e for e in st.error_log)


def test_artifact_contract_rejects_bad_json(tmp_path, monkeypatch):
    spec = _spec()
    spec["stages"][0]["output_artifacts"] = [{"name": "v", "suffix": "json"}]
    spec["stages"][0]["artifact_contract"] = {"format": "json", "fields": ["status"]}
    c, st, _ = _run(tmp_path, monkeypatch, spec, lambda p, s: "not-json")
    assert any("交付物契约不满足" in e for e in st.error_log)


def test_artifact_contract_accepts_good_json(tmp_path, monkeypatch):
    spec = _spec()
    spec["stages"][0]["output_artifacts"] = [{"name": "v", "suffix": "json"}]
    spec["stages"][0]["artifact_contract"] = {"format": "json", "fields": ["status"]}
    c, st, _ = _run(tmp_path, monkeypatch, spec,
                    lambda p, s: json.dumps({"status": "pass", "evidence": "ok"}))
    assert not any("交付物契约不满足" in e for e in st.error_log)
    assert not st.is_frozen


def test_loop_bounds_reach_compiled(tmp_path, monkeypatch):
    c, st, _ = _run(tmp_path, monkeypatch,
                    _spec(loop_bounds={"maxPlanCycles": 1, "maxVerifyCycles": 2}),
                    lambda p, s: "ok")
    assert c["loop_bounds"] == {"maxPlanCycles": 1, "maxVerifyCycles": 2}


def test_refusal_bogus_trigger_rejected(tmp_path, monkeypatch):
    """拒答必须引用声明的 triggers，否则判 REFUSAL_TRIGGER_INVALID。"""
    c, st, _ = _run(tmp_path, monkeypatch,
                    _spec(refusal={"triggers": ["out_of_scope"],
                                   "artifact": "refusal.md", "exit": "blocked"}),
                    lambda p, s: {"refusal.md": "触发条件：bogus"})
    assert any("未引用声明触发条件" in e for e in st.error_log), st.error_log


def test_max_rollback_from_loop_bounds_freezes(tmp_path, monkeypatch):
    """loopBounds 必须真控熔断：maxVerifyCycles=1 → 第二次打回即冻结。"""
    from engine.flow.workflow_compiler import GateReject
    spec = {"workflow_id": "rb", "stages": [
        {"stage_id": "a", "agent": "a", "depends_on": [],
         "output_artifacts": [{"name": "a", "suffix": "md"}]},
        {"stage_id": "b", "agent": "b", "depends_on": ["a"],
         "output_artifacts": [{"name": "b", "suffix": "md"}]},
    ], "loop_bounds": {"maxVerifyCycles": 1}}
    def runner(prompt, stage_id):
        if stage_id == "b":
            raise GateReject("verify failed")
        return "ok"
    c, st, _ = _run(tmp_path, monkeypatch, spec, runner)
    assert st.is_frozen
    assert "熔断" in (st.freeze_reason or "")
