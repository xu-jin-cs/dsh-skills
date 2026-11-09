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


# ── 第 14 段 promptContract（系统提示词宪法，2026-11-09） ─────────
def _pc(**over) -> dict:
    pc = {
        "agent_role": "只读查询助手：一次查询、一次整理、如实回报",
        "core_goal": {"statement": "按口径查询一次", "done_when": "结果带 source 与 queriedAt"},
        "allow_actions": ["query_readonly", "format_output"],
        "tool_spec": [
            {"name": "query_readonly", "when": "口径明确时", "how": "只调一次只读接口",
             "args": {"endpoint": "string"}},
            {"name": "format_output", "when": "拿到结果后", "how": "按 outputSchema 组装",
             "args": {"rows": "array"}},
        ],
        "error_handling": {"failure": "如实报错", "timeout": "判失败不重试",
                           "exception": "截断多余字段并告警"},
        "few_shot_examples": [
            {"kind": "format", "input": "查一下昨天入库量", "output": "{\"rows\":[...]}"},
            {"kind": "refusal", "input": "删掉这条记录", "output": "拒绝：只读，不写。"},
            {"kind": "boundary", "input": "你先猜个数", "output": "拒绝编造：需先查询。"},
        ],
        "isolate_prompt_rule": True,
        "stable_sections": ["agent_role", "core_goal", "allow_actions", "tool_spec"],
        "dynamic_sections": ["task_input", "retrieved_context"],
    }
    pc.update(over)
    return pc


def test_prompt_contract_valid():
    validate_observe("skill:test-paradigm", _ob(promptContract=_pc()))


def test_prompt_contract_absent_is_ok():
    validate_observe("skill:test-paradigm", _ob())


def test_allow_actions_must_not_be_empty():
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=_pc(allow_actions=[])))
    assert "allow_actions" in str(e.value)


def test_tool_must_be_allowed():
    pc = _pc()
    pc["tool_spec"][0]["name"] = "drop_table"      # 不在 allow_actions
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=pc))
    assert "不在 allow_actions" in str(e.value)


def test_tool_spec_requires_when_how_args():
    pc = _pc()
    pc["tool_spec"][0].pop("how")
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=pc))
    assert "how" in str(e.value)


def test_few_shot_count_between_2_and_5():
    for bad in ([_pc()["few_shot_examples"][0]],
                [_pc()["few_shot_examples"][i % 3] for i in range(6)]):
        with pytest.raises(ContractError) as e:
            validate_observe("skill:test-paradigm", _ob(promptContract=_pc(few_shot_examples=bad)))
        assert "2~5" in str(e.value)


def test_few_shot_must_cover_three_kinds():
    shots = [s for s in _pc()["few_shot_examples"] if s["kind"] == "format"] * 2
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=_pc(few_shot_examples=shots)))
    assert "格式/拒答/边界" in str(e.value)


def test_error_handling_requires_three_cases():
    pc = _pc()
    pc["error_handling"].pop("timeout")
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=pc))
    assert "timeout" in str(e.value)


def test_stable_and_dynamic_must_be_disjoint():
    pc = _pc()
    pc["dynamic_sections"] = ["task_input", "agent_role"]     # 与 stable 重叠
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(promptContract=pc))
    assert "既稳定又动态" in str(e.value)


def test_prompt_separation_off_warns():
    from engine.observe.contract_loader import prompt_contract_warnings
    ws = prompt_contract_warnings("x", {"promptContract": _pc(isolate_prompt_rule=False)})
    assert {w["code"] for w in ws} == {"PROMPT_SEPARATION_OFF"}
    ws2 = prompt_contract_warnings("x", {"promptContract": _pc()})
    assert ws2 == []


def test_registry_carries_prompt_contract_key():
    res = scan()
    assert res["errors"] == []
    for entry in res["registry"].values():
        assert "promptContract" in entry


# ── 第 15 段 modelPolicy（模型底座分层选型，2026-11-09） ──────────
def _mp(**over) -> dict:
    mp = {
        "tiers": {
            "router": {"model": "kimi-k3", "maxComplexity": "S", "minConfidence": 0.6},
            "primary": {"model": "deepseek-v4", "maxComplexity": "XL"},
            "verifier": {"model": "qwen-judge", "maxComplexity": "XL",
                         "decoupled": True, "votes": 3},
        },
        "degrade": {"triggers": ["timeout", "error", "quota_exhausted"],
                    "chain": ["deepseek-v4", "kimi-k3"], "onExhausted": "escalate"},
        "verify": {"onFail": "rework", "maxRework": 2, "feedback": "structured"},
        "selection": {"model": "primary",
                      "scores": {"reasoning": 0.9, "contextWindow": 0.85, "latency": 0.6,
                                 "tokenPrice": 0.55, "localPrivacy": 0.4}},
    }
    mp.update(over)
    return mp


def test_lexicon_has_model_enums():
    lex = paradigm_lexicon()
    assert lex["modelTriggers"] == {"timeout", "error", "quota_exhausted"}
    assert lex["selectionDims"] == {"reasoning", "contextWindow", "latency",
                                    "tokenPrice", "localPrivacy"}


def test_model_policy_valid():
    validate_observe("skill:test-paradigm", _ob(modelPolicy=_mp()))


def test_model_policy_absent_is_ok():
    validate_observe("skill:test-paradigm", _ob())


def test_verifier_must_differ_from_primary():
    mp = _mp()
    mp["tiers"]["verifier"]["model"] = "deepseek-v4"      # 同模型自查
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "裁判≠运动员" in str(e.value)


def test_verifier_must_be_decoupled():
    mp = _mp()
    mp["tiers"]["verifier"]["decoupled"] = False
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "decoupled" in str(e.value)


def test_router_boundary_must_be_strictly_weaker():
    mp = _mp()
    mp["tiers"]["router"]["maxComplexity"] = "XL"          # 与 primary 同档
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "严格弱于" in str(e.value)


def test_degrade_triggers_must_cover_three():
    mp = _mp()
    mp["degrade"]["triggers"] = ["timeout", "error"]       # 缺 quota_exhausted
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "quota_exhausted" in str(e.value)


def test_chain_head_must_be_primary_model():
    mp = _mp()
    mp["degrade"]["chain"] = ["kimi-k3", "deepseek-v4"]     # 链首不是 primary
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "chain[0]" in str(e.value)


def test_verify_on_fail_must_rework():
    mp = _mp()
    mp["verify"]["onFail"] = "pass"
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "onFail" in str(e.value)


def test_selection_needs_five_dims():
    mp = _mp()
    del mp["selection"]["scores"]["localPrivacy"]
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(modelPolicy=mp))
    assert "五维" in str(e.value)


def test_registry_carries_model_policy_key():
    res = scan()
    assert res["errors"] == []
    for entry in res["registry"].values():
        assert "modelPolicy" in entry


# ── 复审补：multi_agent 三件套门 / 状态转移（F-6 / F-11） ────────
def _multi_ob(agents=("a", "b"), group=True, stateout=True) -> dict:
    ob = _ob(paradigm={"id": "multi_agent"})
    for i, n in enumerate(ob["nodes"]):
        n["agentId"] = agents[i % len(agents)]
        if stateout:
            n["stateOut"] = [f"f{i}"]
        else:
            n.pop("stateOut", None)
        if group:
            n["mode"] = "optional_parallel"
            n["parallelGroup"] = "g1"
    return ob


def test_multi_agent_gate_ok():
    validate_observe("skill:test-paradigm", _multi_ob())


def test_multi_agent_requires_two_agents():
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _multi_ob(agents=("only",)))
    assert "角色分工" in str(e.value)


def test_multi_agent_requires_parallel_group():
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _multi_ob(group=False))
    assert "并行" in str(e.value)


def test_multi_agent_requires_state_contract():
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _multi_ob(stateout=False))
    assert "接口契约" in str(e.value)


def test_node_transitions_are_guarded():
    from engine.observe.contract_loader import NODE_STATUSES, is_valid_transition
    assert is_valid_transition("pending", "running")
    assert is_valid_transition("running", "completed")
    assert not is_valid_transition("pending", "completed")      # 不许越级
    assert not is_valid_transition("voided", "running")         # 终态不可复活
    assert not is_valid_transition("nonsense", "running")       # 未知状态一律 False
    assert {"paused", "aborted", "incomplete"} <= NODE_STATUSES


# ── 第四轮补：口径守卫（observationCodes / 执行器常量 / vector.status） ──
def test_vector_status_reserved_conflicts_with_enabled():
    cp = _ctx()
    cp["memory"]["vector"].update({"status": "reserved", "enabled": True,
                                   "collection": "kb", "embeddingModel": "bge-m3", "dim": 1024})
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "reserved" in str(e.value)


def test_vector_status_illegal_value():
    cp = _ctx()
    cp["memory"]["vector"]["status"] = "live"
    with pytest.raises(ContractError) as e:
        validate_observe("skill:test-paradigm", _ob(contextPolicy=cp))
    assert "vector.status" in str(e.value)


def test_emitted_warning_codes_are_registered():
    """observationCodes 的唯一消费者：发出的码必须都在登记表内（防第二份码表）。"""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "engine" / "observe" / "contract_loader.py"
    emitted = set(re.findall(r'"code":\s*"([A-Z_]+)"', src.read_text(encoding="utf-8")))
    registered = set((load_paradigms_doc().get("observationCodes") or {}).get("codes") or [])
    assert emitted <= registered, f"未登记的告警码：{sorted(emitted - registered)}"


def test_router_constants_match_single_source():
    """执行器常量与真源等值（防静默漂移）。"""
    from engine.model.router import COMPLEXITY_RANK, TRIGGERS
    lex = paradigm_lexicon()
    assert set(TRIGGERS) == lex["modelTriggers"]
    assert set(COMPLEXITY_RANK) == {"XS", "S", "M", "L", "XL"}


def load_paradigms_doc() -> dict:
    import json
    from pathlib import Path
    p = Path.home() / ".agents" / "agent-paradigms" / "paradigms.json"
    return json.loads(p.read_text(encoding="utf-8"))
