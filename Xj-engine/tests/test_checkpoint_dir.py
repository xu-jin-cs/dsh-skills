"""checkpoint 默认目录解析回归（2026-11-04 langgraph 残迹清零）。

对应 spec_challenge_xjengine_round_20261104 判据：
legacy .langgraph 有存量数据必须回退可用（数据不断链），
新装落 .xjengine，env 新名优先、历史别名兼容。
"""
from engine.flow.checkpoint import resolve_default_checkpoint_dir


def test_legacy_dir_fallback(tmp_path, monkeypatch):
    """新目录无数据、旧 .langgraph 有 checkpoints.db → 回退旧目录。"""
    monkeypatch.delenv("XJENGINE_CHECKPOINT_DIR", raising=False)
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_DIR", raising=False)
    legacy = tmp_path / ".langgraph"
    legacy.mkdir()
    (legacy / "checkpoints.db").write_bytes(b"x")
    assert resolve_default_checkpoint_dir(str(tmp_path)) == str(legacy)


def test_new_dir_wins_when_has_data(tmp_path, monkeypatch):
    monkeypatch.delenv("XJENGINE_CHECKPOINT_DIR", raising=False)
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_DIR", raising=False)
    new = tmp_path / ".xjengine"
    new.mkdir()
    (new / "checkpoints.db").write_bytes(b"x")
    assert resolve_default_checkpoint_dir(str(tmp_path)) == str(new)


def test_fresh_root_lands_new_name(tmp_path, monkeypatch):
    monkeypatch.delenv("XJENGINE_CHECKPOINT_DIR", raising=False)
    monkeypatch.delenv("LANGGRAPH_CHECKPOINT_DIR", raising=False)
    assert resolve_default_checkpoint_dir(str(tmp_path)) == str(tmp_path / ".xjengine")


def test_env_new_name_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("XJENGINE_CHECKPOINT_DIR", str(tmp_path / "envdir"))
    assert resolve_default_checkpoint_dir(str(tmp_path)) == str(tmp_path / "envdir")
