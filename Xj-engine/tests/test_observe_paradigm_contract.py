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
             "deliverableType": "text",
             "capabilities": {"canReplace": True, "supportPause": False, "supportRerun": False}},
            {"nodeId": "n2", "agentId": "main", "title": "产出", "seq": 2,
             "deliverableType": "text",
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
