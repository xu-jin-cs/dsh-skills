"""Spec 字段可达性：gate_spec 透传 + 回退重建（restore）。"""
import json
import os

from engine.flow.workflow_builder import build_workflow
from engine.flow.workflow_compiler import _latest_snapshot, _restore_stage


def test_gate_spec_passthrough(tmp_path):
    spec = {"workflow_id": "zt", "stages": [{
        "stage_id": "n1", "agent": "main", "depends_on": [],
        "output_artifacts": [{"name": "out", "suffix": "md"}],
        "deliverables": [{"filename": "out.md"}],
        "branch_conditions": {"done": "__end__"},
        "gate_spec": {"name": "demo", "spec": "/tmp/x.json"},
        "nodeType": "executor", "retryPolicy": {"maxRetries": 2},
        "compensationAction": {"type": "reset"},
    }]}
    wf = build_workflow(spec, str(tmp_path))
    assert wf["stages"][0]["gate_spec"] == {"name": "demo", "spec": "/tmp/x.json"}
    src = wf["source"]["stages"][0]
    assert src["retryPolicy"] == {"maxRetries": 2}
    assert src["compensationAction"] == {"type": "reset"}


def test_restore_stage_writes_config(tmp_path):
    root = tmp_path / "artifacts"
    stage_dir = "01_a"
    snap_dir = root / stage_dir / "snapshots"
    snap_dir.mkdir(parents=True)
    (root / "INDEX.md").write_text(
        "# 台账\n\n| 环节 | 版本 | 状态 | 产物路径 |\n| --- | --- | --- | --- |\n", encoding="utf-8")
    (root / stage_dir / "manifest.md").write_text(
        "# a 环节 manifest\n\n## 上游依赖\n| 上游环节 | 版本 | 交付物相对路径 |\n"
        "| --- | --- | --- |\n（无，首环节）\n\n## 产物清单\n- x\n", encoding="utf-8")
    (snap_dir / "a_v1_snap01.json").write_text(json.dumps({
        "snapshot_id": "a_v1_snap01", "stage_id": "a", "stage_dir": stage_dir,
        "workflow_id": "w", "artifact_refs": [], "index_ref": "INDEX.md @ 0",
    }), encoding="utf-8")

    plugin_bin = os.path.expanduser(
        "~/.zcode/workspace/default/plugins/stage-context-isolation/bin")
    compiled = {"workflow_id": "w", "stage_dirs": {"a": stage_dir}}
    assert _latest_snapshot(str(root), stage_dir) == "a_v1_snap01"
    _restore_stage(compiled, "a", str(root), plugin_bin)
    cfg_path = root / stage_dir / ".restore_config.json"
    assert cfg_path.is_file()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["stage_id"] == "a"
    assert cfg["workflow_id"] == "w"
