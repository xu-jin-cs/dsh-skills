"""范式选型机制单测：打分公式 / 置信三档 / 三门校验 / 缓存 / 回流 / 逃逸。

对应 2026-11-09 用户规格：
  Score = strong×2 + weak×1 − negative×2
  confidence = (top − second) / (top + 1)
  三档：≥0.6 auto｜0.3~0.6 review｜<0.3 blocked
  三门：schema / 三件套 / 反思与资源上界；返回码 0/1/2
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from engine.paradigm import gates, matcher, spec
from engine.paradigm.escape import detect

TEMPLATES = Path.home() / ".agents" / "agent-paradigms" / "templates"


def _tpl(name: str) -> dict:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


# ── 打分公式 ────────────────────────────────────────────────────
def test_formula_is_fixed():
    rows, warns, mode = matcher.score_all("复盘 自省 纠错")
    reflex = next(r for r in rows if r["paradigm"] == "reflexion")
    expect = 2 * len(reflex["strongHits"]) + len(reflex["weakHits"]) - 2 * len(reflex["negativeHits"])
    assert reflex["score"] == expect
    assert reflex["score"] > 0


def test_negative_signals_subtract_double():
    # “并行”是 react 的负向信号
    rows, _, _ = matcher.score_all("并行")
    react = next(r for r in rows if r["paradigm"] == "react")
    assert react["score"] == -2 * len(react["negativeHits"])
    assert react["score"] < 0


def test_confidence_gap_formula():
    rows = [{"paradigm": "a", "score": 4}, {"paradigm": "b", "score": 2}]
    top, second, conf, tie = matcher.confidence_of(rows)
    assert (top, second) == (4, 2)
    assert conf == pytest.approx((4 - 2) / (4 + 1))
    assert not tie


# ── 三档判定 ────────────────────────────────────────────────────
def test_auto_band():
    d = matcher.decide("帮我查一下昨天入库多少条数据", use_cache=False)
    assert d["decision"] == "auto" and d["confidence"] >= 0.6
    assert d["paradigm"] == "single_tool_call"


def test_review_band():
    d = matcher.decide("先规划再拆解任务，然后并行推进", use_cache=False)
    assert d["decision"] == "review"
    assert 0.3 <= d["confidence"] < 0.6


def test_blocked_band_on_tie():
    d = matcher.decide("验证一下 简单", use_cache=False)
    assert d["decision"] == "blocked" and d["tie"] is True
    assert any("tie" in w for w in d["warnings"])


def test_no_signal_is_blocked():
    d = matcher.decide("zzz 无信号文本", use_cache=False)
    assert d["decision"] == "blocked"
    assert any("no_signal" in w for w in d["warnings"])


def test_tie_suggestion_prefers_lighter():
    # 构造两范式同分：single 与 reflexion 各 2 分
    rows, _, _ = matcher.score_all("查询 复盘")
    top, _, conf, tie = matcher.confidence_of(rows)
    best = max(rows, key=lambda r: (r["score"], -spec.order().index(r["paradigm"])))
    assert tie or top > 0
    if tie:
        assert best["paradigm"] == "single_tool_call"


# ── 缓存 / 开关 / 人工覆盖 ──────────────────────────────────────
def test_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(matcher, "CACHE_FILE", tmp_path / "cache.json")
    text = "缓存专用文本-查一下有多少条"
    first = matcher.decide(text, use_cache=True)
    second = matcher.decide(text, use_cache=True)
    assert first["cacheHit"] is False
    assert second["cacheHit"] is True
    assert second["paradigm"] == first["paradigm"]


def test_override_beats_scores(monkeypatch, tmp_path):
    monkeypatch.setattr(spec, "LOG_DIR", tmp_path)
    d = matcher.decide("帮我查一下", override="plan_execute")
    # M6：人工改判不得伪装成 auto；原始建议必须保留
    assert d["decision"] == "override" and d["paradigm"] == "plan_execute"
    assert d["override"] is True
    assert "suggestedByMatch" in d and d["suggestedByMatch"].get("paradigm") is not None
    from engine.paradigm import samples
    p = samples.override_sample("帮我查一下", d, reason="测试")
    row = json.loads(Path(p).read_text(encoding="utf-8").splitlines()[-1])
    assert row["label"] == "human_override" and row["chosen"] == "plan_execute"


def test_skip_switch_default_off(monkeypatch):
    monkeypatch.delenv("PARADIGM_SKIP_SELECTOR", raising=False)
    assert spec.skip_selector() is False
    monkeypatch.setenv("PARADIGM_SKIP_SELECTOR", "1")
    assert spec.skip_selector() is True


# ── 三门校验 ────────────────────────────────────────────────────
def test_gate_pass():
    r = gates.run(_tpl("04_reflexion.json"))
    assert r["code"] == 0 and r["verdict"] == "PASS"


def test_gate_p1_only_returns_2():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["deliverables"]["primary"]["acceptanceAnchor"] = "做得好就行"
    r = gates.run(a)
    assert r["code"] == 2 and r["errors"] == []
    assert any("模糊词" in w or "过短" in w for w in r["warnings"])


def test_gate_p0_returns_1_and_cannot_pass():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a.pop("contextPolicy")
    r = gates.run(a)
    assert r["code"] == 1 and r["errors"]


def test_gate_version_mismatch_blocks():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["meta"]["paradigmVersion"] = "2020-01-01.0"
    r = gates.run(a)
    assert any("版本不匹配" in e for e in r["errors"])


def test_gate_paradigm_mismatch_blocks():
    r = gates.run(_tpl("04_reflexion.json"), expected="react")
    assert any("范式不一致" in e for e in r["errors"])


def test_reflexion_requires_three_bounds():
    a = copy.deepcopy(_tpl("04_reflexion.json"))
    a["orchestration"]["loop"].pop("maxTokensPerTurn")
    r = gates.run(a)
    assert any("maxTokensPerTurn" in e for e in r["errors"])


def test_light_paradigm_forbids_reflection_loop():
    a = copy.deepcopy(_tpl("02_react.json"))
    a["orchestration"]["loop"]["purpose"] = "reflection"
    r = gates.run(a)
    assert any("轻范式" in e for e in r["errors"])


def test_multi_agent_requires_message_rounds():
    a = copy.deepcopy(_tpl("05_multi_agent.json"))
    a["orchestration"].pop("maxMessageRounds")
    r = gates.run(a)
    assert any("maxMessageRounds" in e for e in r["errors"])


def test_three_piece_missing_is_p0():
    a = copy.deepcopy(_tpl("03_plan_execute.json"))
    a["pipeline"]["nodes"] = []
    r = gates.run(a)
    assert any("方案路径" in e for e in r["errors"])


# ── 逃逸检测 ────────────────────────────────────────────────────
def test_escape_light_with_reflection():
    res = detect("react", {"maxIterations": 3, "loopPurpose": "reflection", "distinctAgentId": 1})
    assert res["escaped"] and res["alerts"][0]["code"] == "ESCAPE_LIGHT_WITH_REFLECTION"


def test_escape_single_split_multi():
    res = detect("single_tool_call", {"distinctAgentId": 3})
    assert res["escaped"] and res["alerts"][0]["code"] == "ESCAPE_SINGLE_SPLIT_MULTI"


def test_escape_reflexion_unbounded():
    res = detect("reflexion", {"maxIterations": 0, "loopPurpose": "reflection"})
    assert res["escaped"] and res["alerts"][0]["code"] == "ESCAPE_REFLEXION_UNBOUNDED"


def test_escape_clean():
    assert detect("plan_execute", {"maxIterations": 0, "distinctAgentId": 1})["escaped"] is False


# ── F-14：判定顺序单源（2026-11-10）──────────────────────────────
def test_order_derives_from_match_order():
    from engine.paradigm import spec
    mo = spec.load()["matchOrder"]
    assert spec.order() == tuple(reversed(mo))
    assert set(spec.order()) == set(spec.ORDER)      # 兜底常量不得与真源分叉


# ── F-9：入参错误必须 exit 3（不得与 2=人工复核撞码）──────────────
def test_cli_bad_args_exit_3():
    from engine.paradigm import cli
    try:
        cli.main(["match"])          # 缺 --text → argparse error
    except SystemExit as e:
        assert e.code == 3
    else:
        raise AssertionError("期望 SystemExit(3)")


def test_paradigm_match_bad_args_exit_3():
    import subprocess
    import sys as _sys
    bin_path = str(__import__("pathlib").Path.home() / ".agents/agent-paradigms/bin/paradigm_match.py")
    r = subprocess.run([_sys.executable, bin_path, "match"], capture_output=True, text=True)
    assert r.returncode == 3, r.stderr[:200]
