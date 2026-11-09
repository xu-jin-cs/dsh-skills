"""范式块 / 节点编排属性的契约校验单测（2026-11-09）。

只测纯函数 `validate_observe` 与 `scan` 的注册表形状，不碰 DB、不起服务。
覆盖点：
  - 不带 paradigm 块的既有资产**照常通过**（向后兼容）
  - 五范式枚举来自 ~/.agents/agent-paradigms/paradigms.json（唯一真源）
  - 非法枚举 / 引用悬空 / 并行组只有 1 个节点 → fail-fast
  - registry 透传 paradigm 字段
"""
from __future__ import annotations

import copy

import pytest

from engine.observe.contract_loader import (
    ContractError,
    paradigm_lexicon,
    scan,
    validate_observe,
)


def _ob(**extra) -> dict:
    ob = {
        "contractVersion": "1.0",
        "assetKey": "skill:test-paradigm",
        "sourceHash": "sha256:0000000000000000",
        "runtime": "host",
        "report": {"sink": "platform", "endpoint": "/api/observe/nodes/runtime",
                   "onEvents": ["node_start", "node_end"], "fields": ["taskId"]},
        "nodes": [
            {"nodeId": "n1", "agentId": "main", "title": "读取", "seq": 1,
             "deliverableType": "text", "stateOut": ["draft"],
             "capabilities": {"canReplace": True, "supportPause": False, "supportRerun": False}},
            {"nodeId": "n2", "agentId": "main", "title": "产出", "seq": 2,
             "deliverableType": "text", "stateOut": ["verdict"],
             "capabilities": {"canReplace": True, "supportPause": False, "supportRerun": False}},
        ],
    }
    ob.update(extra)
    return ob


def test_lexicon_is_single_source():
    lex = paradigm_lexicon()
    assert lex["paradigmIds"] == {"single_tool_call", "react", "plan_execute",
                                  "reflexion", "multi_agent"}
    assert lex["nodeModes"] == {"required_serial", "optional_parallel", "fallback_hook"}
    assert "long_session" in lex["taskRoles"]
    assert {"hallucination", "tool_abuse", "data_leak", "deadloop"} <= lex["riskGuards"]


def test_backward_compatible_without_paradigm():
    validate_observe("skill:test-paradigm", _ob())      # 不抛即通过


def test_valid_paradigm_block():
    ob = _ob(paradigm={"id": "plan_execute", "taskRole": "long_session",
                       "deliverableAnchor": "n2",
                       "metrics": {"completionRate": 0.9},
                       "riskGuards": ["hallucination", "deadloop"]})
    ob["nodes"][1]["mode"] = "required_serial"
    ob["nodes"][1]["acceptance"] = "产出文件存在且非空"
    validate_observe("skill:test-paradigm", ob)


def test_illegal_paradigm_id():
    ob = _ob(paradigm={"id": "auto_magic"})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "observe.paradigm.id" in str(e.value)


def test_illegal_task_role():
    ob = _ob(paradigm={"id": "react", "taskRole": "normal"})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "taskRole" in str(e.value)


def test_deliverable_anchor_must_exist():
    ob = _ob(paradigm={"id": "react", "deliverableAnchor": "n99"})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "deliverableAnchor" in str(e.value)


def test_illegal_risk_guard():
    ob = _ob(paradigm={"id": "react", "riskGuards": ["security"]})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "riskGuards" in str(e.value)


def test_optional_parallel_requires_group():
    ob = _ob()
    ob["nodes"][0]["mode"] = "optional_parallel"
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "parallelGroup" in str(e.value)


def test_parallel_group_needs_two_nodes():
    ob = _ob()
    ob["nodes"][0].update({"mode": "optional_parallel", "parallelGroup": "g1"})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "至少 2 个" in str(e.value)


def test_parallel_group_ok_with_two_nodes():
    ob = _ob()
    ob["nodes"][0].update({"mode": "optional_parallel", "parallelGroup": "g1"})
    ob["nodes"][1].update({"mode": "optional_parallel", "parallelGroup": "g1"})
    validate_observe("skill:test-paradigm", ob)


def test_fallback_requires_existing_target():
    ob = _ob()
    ob["nodes"][1].update({"mode": "fallback_hook", "fallbackOf": "n99"})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "fallbackOf" in str(e.value)


def test_fallback_target_must_be_upstream():
    ob = _ob()
    ob["nodes"][0].update({"mode": "fallback_hook", "fallbackOf": "n2"})   # 兜底自己下游
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "在其之后" in str(e.value)


def test_state_fields_must_be_string_arrays():
    ob = _ob()
    ob["nodes"][0]["stateOut"] = ["ok", 123]
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "stateOut" in str(e.value)


def test_acceptance_must_be_string():
    ob = _ob()
    ob["nodes"][0]["acceptance"] = {"text": "x"}
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "acceptance" in str(e.value)


def test_registry_carries_paradigm_key():
    res = scan()
    assert res["errors"] == []
    for entry in res["registry"].values():
        assert "paradigm" in entry           # 缺省为空 dict，字段恒在


def test_scan_does_not_mutate_assets():
    """scan 是只读的：跑两次结果一致（防止在扫描期改写声明）。"""
    a, b = scan(), scan()
    assert a["registry"].keys() == b["registry"].keys()
    for k in a["registry"]:
        assert a["registry"][k]["nodes"] == b["registry"][k]["nodes"]


# ── 第 13 段 contextPolicy（2026-11-09） ─────────────────────────
def _ctx(**over) -> dict:
    cp = {
        "budget": {"contextWindowTokens": 128000, "outputReserveTokens": 16000,
                   "systemPromptTokens": 8000, "safetyMarginRatio": 0.1,
                   "degradeAtRatio": 0.85, "calibrated": False},
        "compression": {"strategy": "summary", "fallbackStrategy": "fifo",
                        "triggerAtRatio": 0.8, "keepRecentTurns": 6,
                        "keepPinned": True, "summaryMaxTokens": 2000,
                        "importanceWeights": {"task": 0.5, "artifact": 0.3},
                        "dropPolicy": "drop_lowest_importance"},
        "memory": {"enabledTiers": ["working", "episodic"],
                   "recall": {"strategy": "keyword", "topK": 5, "minScore": 0.5,
                              "injectAt": "stage_start"},
                   "vector": {"status": "reserved", "enabled": False,
                              "reservedFor": "rag_engineering", "collection": None,
                              "embeddingModel": None, "dim": None, "metric": "cosine",
                              "chunkSize": None, "chunkOverlap": None, "indexName": None,
                              "namespaceFields": ["assetKey", "nodeId", "tier"]}},
        "overflow": {"onBudgetExceeded": "summarize",
                     "onCompressionExhausted": "escalate", "escalateTo": "human",
                     "hardStop": True, "recordEvidence": True,
                     "alarm": {"enabled": True, "channels": ["log", "platform"],
                               "codes": ["BUDGET_DEGRADED", "BUDGET_EXHAUSTED"],
                               "throttleSec": 300}},
        "handoff": {"carrier": "file", "pathPattern": "{stage_dir}/handoff/{from}__{to}.json",
                    "fields": ["draft"], "maxBytes": 1048576, "checksum": True,
                    "onMissing": "escalate",
                    "envelope": {"schemaVersion": "handoff/1",
                                 "requiredFields": ["from", "to", "ts", "fields"]}},
    }
    cp.update(over)
    return cp


def test_lexicon_has_context_enums():
    lex = paradigm_lexicon()
    assert lex["compressionStrategies"] == {"none", "fifo", "summary", "importance"}
    assert lex["memoryTiers"] == {"working", "episodic", "semantic"}
    assert lex["recallStrategies"] == {"keyword", "embedding", "hybrid"}
    assert lex["vectorMetrics"] == {"cosine", "l2", "ip"}


def test_context_policy_valid():
    ob = _ob(contextPolicy=_ctx())
    validate_observe("skill:test-paradigm", ob)


def test_context_policy_absent_is_ok():
    validate_observe("skill:test-paradigm", _ob())          # 不声明不报错


def test_calibrated_requires_evidence():
    cp = _ctx()
    cp["budget"]["calibrated"] = True
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "calibrationEvidence" in str(e.value)


def test_effective_budget_must_be_positive():
    cp = _ctx()
    cp["budget"]["outputReserveTokens"] = 120000
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "有效预算" in str(e.value)


def test_summary_requires_max_tokens():
    cp = _ctx()
    cp["compression"]["summaryMaxTokens"] = None
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "summaryMaxTokens" in str(e.value)


def test_trigger_must_not_exceed_degrade():
    cp = _ctx()
    cp["compression"]["triggerAtRatio"] = 0.95       # degradeAtRatio=0.85
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "triggerAtRatio" in str(e.value)


def test_none_strategy_allows_null_trigger():
    cp = _ctx()
    cp["compression"].update({"strategy": "none", "triggerAtRatio": None, "summaryMaxTokens": None})
    validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))


def test_working_tier_mandatory():
    cp = _ctx()
    cp["memory"]["enabledTiers"] = ["episodic"]
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "working" in str(e.value)


def test_vector_enabled_requires_landing_fields():
    cp = _ctx()
    cp["memory"]["vector"]["enabled"] = True       # collection/embeddingModel/dim 仍为 null
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "vector" in str(e.value)


def test_context_policy_warnings_emitted():
    from engine.observe.contract_loader import context_policy_warnings
    cp = _ctx()
    ws = context_policy_warnings("skill:test-paradigm", {"contextPolicy": cp})
    codes = {w["code"] for w in ws}
    assert "BUDGET_UNCALIBRATED" in codes          # calibrated=false

    cp2 = _ctx()
    cp2["memory"]["vector"]["enabled"] = True
    cp2["memory"]["vector"].update({"collection": "kb", "embeddingModel": "bge-m3", "dim": 1024})
    codes2 = {w["code"] for w in context_policy_warnings("x", {"contextPolicy": cp2})}
    assert "VECTOR_RESERVED" in codes2

    cp3 = _ctx()
    cp3["memory"]["recall"]["strategy"] = "hybrid"  # 但 vector.enabled=false
    codes3 = {w["code"] for w in context_policy_warnings("x", {"contextPolicy": cp3})}
    assert "RECALL_WITHOUT_VECTOR" in codes3


def test_registry_carries_context_policy_key():
    res = scan()
    assert res["errors"] == []
    for entry in res["registry"].values():
        assert "contextPolicy" in entry            # 缺省为空 dict，字段恒在


# ── 溢出降级与告警 / 跨节点交接载体（2026-11-09 追加） ────────────
def test_lexicon_has_overflow_and_handoff_enums():
    lex = paradigm_lexicon()
    assert lex["overflowActions"] == {"truncate", "summarize", "escalate", "fail"}
    assert lex["escalateTargets"] == {"human", "orchestrator", "none"}
    assert lex["alarmChannels"] == {"log", "platform", "notify"}
    assert lex["handoffCarriers"] == {"file", "message", "artifact_store", "none"}
    assert lex["missingPolicies"] == {"refuse", "escalate"}


def test_truncate_requires_alarm():
    cp = _ctx()
    cp["overflow"]["onBudgetExceeded"] = "truncate"
    cp["overflow"]["alarm"]["enabled"] = False       # 静默截断 → 必须拦住
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "静默截断" in str(e.value)


def test_escalate_requires_target():
    cp = _ctx()
    cp["overflow"]["onCompressionExhausted"] = "escalate"
    cp["overflow"]["escalateTo"] = "none"
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "escalateTo" in str(e.value)


def test_alarm_channels_validated():
    cp = _ctx()
    cp["overflow"]["alarm"]["channels"] = ["sms"]
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "channels" in str(e.value)


def test_handoff_file_requires_path_pattern():
    cp = _ctx()
    cp["handoff"]["carrier"] = "file"
    cp["handoff"].pop("pathPattern", None)
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "pathPattern" in str(e.value)


def test_handoff_fields_must_come_from_stateout():
    cp = _ctx()
    cp["handoff"]["fields"] = ["draft", "unrelated_field"]
    ob = _ob(contextPolicy=cp)
    ob["nodes"][0]["stateOut"] = ["draft"]           # unrelated_field 无人产出
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", ob)
    assert "unrelated_field" in str(e.value)


def test_handoff_fields_ok_when_declared():
    cp = _ctx()
    cp["handoff"]["fields"] = ["draft", "verdict"]
    ob = _ob(contextPolicy=cp)
    ob["nodes"][0]["stateOut"] = ["draft"]
    ob["nodes"][1]["stateOut"] = ["verdict"]
    validate_observe("skill:test-paradigm", ob)


def test_handoff_envelope_needs_from_to_ts():
    cp = _ctx()
    cp["handoff"]["envelope"]["requiredFields"] = ["from", "to"]     # 缺 ts
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "from/to/ts" in str(e.value)


def test_handoff_none_carrier_allows_empty_fields():
    cp = _ctx()
    cp["handoff"].update({"carrier": "none", "fields": []})
    cp["handoff"].pop("pathPattern", None)
    validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
