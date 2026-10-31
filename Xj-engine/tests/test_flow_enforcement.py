"""引擎 flow 强制执行回归：成功路径、骨架缺失、runner 失败。"""
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


def _spec(wid="flowtest"):
    return {"workflow_id": wid, "stages": [
        {"stage_id": "a", "agent": "a", "depends_on": [],
         "output_artifacts": [{"name": "a", "suffix": "md"}]},
        {"stage_id": "b", "agent": "b", "depends_on": ["a"],
         "output_artifacts": [{"name": "b", "suffix": "md"}]},
    ]}


def _rows(path):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


@pytest.mark.skipif(not os.path.isdir(PLUGIN), reason="plugin missing")
def test_success_writes_ledger_and_index(tmp_path, monkeypatch):
    wp = tmp_path / "wf"
    build_workflow(_spec("ok"), str(wp), PLUGIN)
    sl, rl = tmp_path / "s.jsonl", tmp_path / "r.jsonl"
    monkeypatch.setenv("STAGE_ISOLATION_LEDGER", str(sl))
    monkeypatch.setenv("ENGINE_FLOW_RUN_LEDGER", str(rl))
    c = compile_workflow_json(str(wp / "workflow.json"))
    g = build_flow_graph(c, str(wp / "project_artifacts"), PLUGIN,
                         lambda p, s: f"# {s}\ncontent")
    st = g.execute(build_initial_state(instance_id="t", project_name="t",
                                       evidence_root=str(tmp_path / "ev")),
                   start_node=c["topo_order"][0])
    assert not st.is_frozen
    ev = [r["event"] for r in _rows(sl)]
    assert ev.count("assemble") == 2 and ev.count("spawn") == 2
    assert [r["event"] for r in _rows(rl)].count("run_complete") == 1
    index = (wp / "project_artifacts" / "INDEX.md").read_text(encoding="utf-8")
    assert "| a | v1 | active |" in index and "| b | v1 | active |" in index


@pytest.mark.skipif(not os.path.isdir(PLUGIN), reason="plugin missing")
def test_assemble_block_without_skeleton(tmp_path, monkeypatch):
    wp = tmp_path / "wf"
    build_workflow(_spec("bare"), str(wp), PLUGIN)
    import shutil
    shutil.rmtree(wp / "project_artifacts")
    sl, rl = tmp_path / "s2.jsonl", tmp_path / "r2.jsonl"
    monkeypatch.setenv("STAGE_ISOLATION_LEDGER", str(sl))
    monkeypatch.setenv("ENGINE_FLOW_RUN_LEDGER", str(rl))
    c = compile_workflow_json(str(wp / "workflow.json"))
    g = build_flow_graph(c, str(wp / "project_artifacts"), PLUGIN,
                         lambda p, s: "content")
    g.execute(build_initial_state(instance_id="t", project_name="t",
                                  evidence_root=str(tmp_path / "ev")),
              start_node=c["topo_order"][0])
    assert not any(r["event"] == "run_complete" for r in _rows(rl))
    assert not any(r["event"] == "spawn" for r in _rows(sl))


@pytest.mark.skipif(not os.path.isdir(PLUGIN), reason="plugin missing")
def test_runner_failure_no_run_complete(tmp_path, monkeypatch):
    wp = tmp_path / "wf"
    build_workflow(_spec("fail"), str(wp), PLUGIN)
    sl, rl = tmp_path / "s3.jsonl", tmp_path / "r3.jsonl"
    monkeypatch.setenv("STAGE_ISOLATION_LEDGER", str(sl))
    monkeypatch.setenv("ENGINE_FLOW_RUN_LEDGER", str(rl))
    c = compile_workflow_json(str(wp / "workflow.json"))

    def boom(prompt, stage):
        raise RuntimeError("runner exploded")

    g = build_flow_graph(c, str(wp / "project_artifacts"), PLUGIN, boom)
    st = g.execute(build_initial_state(instance_id="t", project_name="t",
                                       evidence_root=str(tmp_path / "ev")),
                   start_node=c["topo_order"][0])
    assert any("冻结" in e and "runner exploded" in e for e in st.error_log)
    assert not any(r["event"] == "run_complete" for r in _rows(rl))
