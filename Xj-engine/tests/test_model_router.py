"""模型底座 · 分层路由状态机单测（纯函数，无网络/无 DB）。

覆盖用户 2026-11-09 裁定的标准执行路径：
  工具路由小模型 → 简单直出 / 复杂上抛 → 主推理 → 校验模型独立裁判
  → 通过放行 / 结构化打回重试 / 返工超限熔断；超时·报错·配额耗尽 → 降级链切换。
"""
from __future__ import annotations

import pytest

from engine.model.router import (
    decide_route, on_failure, on_verify, simulate,
)

POLICY = {
    "tiers": {
        "router": {"model": "kimi-k3", "maxComplexity": "S", "minConfidence": 0.6,
                   "timeoutMs": 800, "maxTokens": 512},
        "primary": {"model": "deepseek-v4", "maxComplexity": "XL"},
        "verifier": {"model": "qwen-judge", "decoupled": True, "votes": 1},
    },
    "degrade": {"triggers": ["timeout", "error", "quota_exhausted"],
                "chain": ["deepseek-v4", "kimi-k3", "local-qwen"],
                "onExhausted": "fail"},
    "verify": {"onFail": "rework", "maxRework": 2, "feedback": "structured"},
}


# ── 路由判定 ────────────────────────────────────────────────────
def test_complex_task_escalates_even_with_high_confidence():
    """Given 复杂度 L > router 边界 S / When 路由判定 / Then 强制上抛。"""
    r = decide_route(policy=POLICY, complexity="L", tool_intent=True, confidence=0.99)
    assert r["target"] == "primary" and r["tier"] == "primary"
    assert "能力边界" in r["reason"]


def test_no_tool_intent_goes_direct():
    r = decide_route(policy=POLICY, complexity="XS", tool_intent=False, confidence=0.9)
    assert r["target"] == "direct" and r["tier"] == "router"


def test_low_confidence_escalates():
    r = decide_route(policy=POLICY, complexity="S", tool_intent=True, confidence=0.4)
    assert r["target"] == "primary"
    assert "置信度" in r["reason"]


def test_simple_with_tool_and_confidence_goes_direct():
    r = decide_route(policy=POLICY, complexity="S", tool_intent=True, confidence=0.8)
    assert r["target"] == "direct"


def test_illegal_complexity_raises():
    with pytest.raises(ValueError):
        decide_route(policy=POLICY, complexity="XXL", tool_intent=True, confidence=0.9)


# ── 校验裁判 ────────────────────────────────────────────────────
def test_verify_pass_releases():
    v = on_verify(policy=POLICY, verdict="pass", rework_count=0)
    assert v["action"] == "release" and v["state"] == "pass"


def test_verify_fail_reworks_with_structured_feedback():
    v = on_verify(policy=POLICY, verdict="fail", rework_count=0)
    assert v["action"] == "rework" and v["reworkCount"] == 1
    assert v["feedbackFormat"] == "structured"


def test_rework_limit_blocks_not_passes():
    v = on_verify(policy=POLICY, verdict="fail", rework_count=2)   # 已达 maxRework
    assert v["action"] == "blocked"
    assert "上限" in v["reason"]


# ── 降级链 ──────────────────────────────────────────────────────
def test_timeout_degrades_to_next_model():
    d = on_failure(policy=POLICY, trigger="timeout", chain_index=0)
    assert d["action"] == "degrade" and d["model"] == "kimi-k3" and d["chainIndex"] == 1


def test_error_from_backup_degrades_again():
    d = on_failure(policy=POLICY, trigger="error", chain_index=1)
    assert d["model"] == "local-qwen"


def test_chain_exhausted_uses_on_exhausted():
    d = on_failure(policy=POLICY, trigger="quota_exhausted", chain_index=2)
    assert d["action"] == "fail" and d["model"] is None


def test_illegal_trigger_raises():
    with pytest.raises(ValueError):
        on_failure(policy=POLICY, trigger="rate_limit", chain_index=0)


# ── 全路径模拟 ──────────────────────────────────────────────────
def test_simulate_direct_path_uses_router_model():
    r = simulate(policy=POLICY, complexity="XS", tool_intent=False, confidence=0.9)
    assert r["final"] == "direct" and r["model"] == "kimi-k3"
    assert [s["state"] for s in r["steps"]] == ["input", "router"]


def test_simulate_primary_rework_then_pass():
    r = simulate(policy=POLICY, complexity="M", tool_intent=True, confidence=0.9,
                 verify_verdicts=["fail", "pass"])
    states = [s["state"] for s in r["steps"]]
    assert r["final"] == "pass"
    assert states.count("rework") == 1
    assert states.count("primary") == 2       # 首跑 + 打回后重试


def test_simulate_rework_limit_blocks():
    r = simulate(policy=POLICY, complexity="M", tool_intent=True, confidence=0.9,
                 verify_verdicts=["fail", "fail", "fail"])
    assert r["final"] == "blocked"


def test_simulate_timeout_then_pass_on_backup():
    r = simulate(policy=POLICY, complexity="M", tool_intent=True, confidence=0.9,
                 failures=["timeout"], verify_verdicts=["pass"])
    states = [s["state"] for s in r["steps"]]
    assert r["final"] == "pass"
    assert "degrade" in states
    assert r["model"] == "kimi-k3"            # 降级到链上第二模型后通过


def test_simulate_without_verdict_never_defaults_to_pass():
    r = simulate(policy=POLICY, complexity="M", tool_intent=True, confidence=0.9,
                 verify_verdicts=[])
    assert r["final"] == "blocked"
    assert "禁止默认放行" in r["reason"]
