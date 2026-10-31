"""stage 运行时契约行为测试：assemble / snapshot CLI 真实可执行。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(os.environ.get(
    "STAGE_RUNTIME_BIN",
    os.path.expanduser("~/.zcode/workspace/default/plugins/stage-context-isolation/bin")))


@pytest.mark.skipif(not (BIN / "assemble_stage_context.py").exists(), reason="plugin missing")
def test_assemble_and_snapshot_contract(tmp_path):
    root = tmp_path / "project_artifacts"
    stage_dir = root / "01_a"
    stage_dir.mkdir(parents=True)
    (root / "INDEX.md").write_text(
        "# index\n\n| 环节 | 版本 | 状态 | 产物路径 |\n| --- | --- | --- | --- |\n"
        "| a | v1 | pending | 01_a/x_v1.md |\n", encoding="utf-8")
    (stage_dir / "manifest.md").write_text(
        "# a manifest\n\n## 上游依赖\n| 上游环节 | 版本 | 交付物相对路径 |\n"
        "| --- | --- | --- |\n（无，首环节）\n\n## 产物清单\n- x_v1.md\n", encoding="utf-8")
    cfg = {
        "stage_id": "a", "workflow_id": "contract", "artifacts_root": str(root),
        "current_stage_dir": str(stage_dir),
        "task_instruction": "执行契约测试阶段任务，产出 x_v1.md 交付物。",
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(BIN / "assemble_stage_context.py"),
         "--config", str(cfg_path), "--report", str(tmp_path / "report.json")],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()

    s = subprocess.run(
        [sys.executable, str(BIN / "snapshot_manager.py"), "snapshot",
         "--artifacts-root", str(root), "--stage-dir", "01_a",
         "--stage-id", "a", "--workflow-id", "contract"],
        capture_output=True, text=True)
    assert s.returncode == 0, s.stderr
    assert (stage_dir / "snapshots").exists()
