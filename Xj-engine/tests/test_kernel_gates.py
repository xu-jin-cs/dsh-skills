"""内核四钩子回归测试（2026-11-04 双法合流审核 P0 修复项）。

覆盖：契约违例 / sha256 签发验签 / 水印防篡改 / state_meta 绑定签名 /
artifact_validate reject+重试预算 / state_intercept block+success /
gate_guard ACL+内核实测限流（报低无法穿透）/ resource_control 台账夹紧（报低伪造）/
抢占式超时 / error 通道 / fallback_target 改写投递 / delivery transform / 任务生命周期。

约束（对应 spec_challenge_xjengine_round_20261104 判据）：
- 全部用例经 conftest 隔离库，不触碰生产 data/engine.db；
- 不依赖网络与宿主（audit 未绑定走隔离库，桥接 adapter 未注册 skipped 不阻塞）。
"""
import uuid

import pytest

from engine.kernel import et
from engine.et_contract import ContractViolationError
from engine.et_sign import verify_issue


def _tid() -> str:
    return f"test-{uuid.uuid4().hex[:10]}"


def _tmp_file(tmp_path, name="artifact.json", size=32):
    p = tmp_path / name
    p.write_bytes(b"x" * size)
    return str(p)


# ── 契约层 ──────────────────────────────────────────────────────

def test_contract_violation_missing_required():
    """缺 trace_id → 契约违例，内核不执行。"""
    with pytest.raises(ContractViolationError):
        et({"artifact": {}})


# ── content_issue：签发 + 验签 + 水印 ───────────────────────────

def test_minimal_success_sha256_verify():
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "content_issue": {"sign": True, "sign_algo": "sha256"}}
    out = et(payload)
    assert out["code"] == "success"
    meta = out["issue_meta"]
    assert meta["algo"] == "sha256" and meta["signature"] and meta["issued_at"]
    assert verify_issue(out["signed_artifact"], meta, payload["trace_id"]) is True


def test_watermark_tamper_detection():
    """ENG-WM-ASYMM：水印先于签名注入，篡改交付物任一字节即验签失败。"""
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "content_issue": {"sign": True, "sign_algo": "sha256", "watermark": True}}
    out = et(payload)
    assert out["code"] == "success"
    signed = out["signed_artifact"]
    assert signed["_watermark"].startswith("wm:")
    assert out["issue_meta"]["watermark"] == signed["_watermark"]
    assert verify_issue(signed, out["issue_meta"], payload["trace_id"]) is True
    tampered = dict(signed)
    tampered["k"] = "hacked"
    assert verify_issue(tampered, out["issue_meta"], payload["trace_id"]) is False


def test_state_meta_bound_into_signature():
    """P2-3：签名原文含 state_meta——换状态元数据即验签失败。"""
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "state_intercept": {"current_state": "PENDING", "target_state": "DESIGN"},
               "content_issue": {"sign": True, "sign_algo": "sha256"}}
    out = et(payload)
    assert out["code"] == "success"
    assert out["new_task_state"] == "DESIGN"
    meta = out["issue_meta"]
    assert verify_issue(out["signed_artifact"], meta, payload["trace_id"],
                        state_meta={"current_state": "PENDING", "target_state": "DESIGN"}) is True
    assert verify_issue(out["signed_artifact"], meta, payload["trace_id"],
                        state_meta={}) is False


# ── artifact_validate ───────────────────────────────────────────

def test_artifact_validate_reject_file_missing(tmp_path):
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "artifact_validate": {"checks": [
                   {"id": "f1", "type": "file_exists",
                    "path": str(tmp_path / "nope.txt")}]}}
    out = et(payload)
    assert out["code"] == "reject"
    assert out["validate_result"]["pass"] is False
    assert any("文件不存在" in f["message"] for f in out["validate_result"]["failures"])
    assert out["new_task_state"] is None  # P1-1：非 success 不携带目标态


def test_artifact_validate_retry_budget(tmp_path):
    """failure_policy.max_retry 仅对 artifact_validate 有界重试，耗尽后维持失败结论。"""
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "artifact_validate": {"checks": [
                   {"id": "f1", "type": "file_exists",
                    "path": str(tmp_path / "nope.txt")}]},
               "failure_policy": {"max_retry": 2, "retry_delay_ms": 0}}
    out = et(payload)
    assert out["code"] == "reject"
    assert out["failure_info"]["executed_retry"] == 2


def test_artifact_validate_pass(tmp_path):
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "artifact_validate": {"checks": [
                   {"id": "f1", "type": "file_exists", "path": _tmp_file(tmp_path)}]}}
    out = et(payload)
    assert out["code"] == "success"
    assert out["validate_result"]["pass"] is True


# ── state_intercept ─────────────────────────────────────────────

def test_state_intercept_block_bad_pair():
    payload = {"trace_id": _tid(), "artifact": {"state": "PENDING"},
               "state_intercept": {"current_state": "PENDING", "target_state": "DEPLOY",
                                   "allowed_pairs": [{"from": "PENDING",
                                                      "to": "PRD_REVIEW"}]}}
    out = et(payload)
    assert out["code"] == "block"
    assert "不在 allowed_pairs" in out["failure_info"]["error_msg"]
    assert out["new_task_state"] is None


def test_state_intercept_success():
    payload = {"trace_id": _tid(), "artifact": {"state": "PENDING"},
               "state_intercept": {"current_state": "PENDING", "target_state": "PRD_REVIEW",
                                   "allowed_pairs": [{"from": "PENDING",
                                                      "to": "PRD_REVIEW"}]}}
    out = et(payload)
    assert out["code"] == "success"
    assert out["new_task_state"] == "PRD_REVIEW"


# ── gate_guard ──────────────────────────────────────────────────

def test_gate_guard_acl_block():
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "gate_guard": {"acl": ["agent-a"], "target_agent_id": "agent-b"}}
    out = et(payload)
    assert out["code"] == "block"
    assert "不在 ACL" in out["failure_info"]["error_msg"]


def test_gate_guard_rate_limit_kernel_measured():
    """服务端权威计量：ET 报 0 伪造无效，内核 60s 滑窗实测夹紧（第 2 次必拦）。"""
    key = f"agent-{uuid.uuid4().hex[:8]}"  # 独立 key 隔离模块级滑窗
    base = {"artifact": {"k": "v"},
            "gate_guard": {"rate_limit": 2, "rate_current": 0,
                           "target_agent_id": key}}
    out1 = et({"trace_id": _tid(), **base})
    assert out1["code"] == "success"  # 第 1 次：实测=1 < 2
    out2 = et({"trace_id": _tid(), **base})
    assert out2["code"] == "block"    # 第 2 次：实测=2 >= 2，报低穿透失败
    assert "内核 60s 滑窗实测 2" in out2["failure_info"]["error_msg"]


# ── resource_control ────────────────────────────────────────────

def test_resource_control_token_over_limit():
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "resource_control": {"token_limit": 100, "token_used": 150}}
    out = et(payload)
    assert out["code"] == "block"
    meter = out["resource"]["metering"]["token"]
    assert meter["reported"] == 150 and meter["kernel_ledger"] == 150
    assert "内核台账夹紧" in out["failure_info"]["error_msg"]


def test_resource_control_lowball_report_clamped():
    """单调高水位台账：同身份报低（重置计数器式伪造）被夹回台账值。"""
    ident = f"principal-{uuid.uuid4().hex[:8]}"
    p1 = {"trace_id": _tid(), "artifact": {},
          "audit_meta": {"principal": ident},
          "resource_control": {"token_limit": 10 ** 9, "token_used": 500}}
    assert et(p1)["code"] == "success"  # 台账记 500
    p2 = {"trace_id": _tid(), "artifact": {},
          "audit_meta": {"principal": ident},
          "resource_control": {"token_limit": 100, "token_used": 1}}
    out = et(p2)
    assert out["code"] == "block"  # max(1, 500)=500 >= 100
    assert "内核台账夹紧" in out["failure_info"]["error_msg"]


# ── 抢占式超时 / error 通道 ──────────────────────────────────────

def test_preemptive_timeout_zero_budget(tmp_path):
    """2026-08-22 抢占式超时：预算耗尽钩子不再执行，确定性判 timeout。"""
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "resource_control": {"hook_timeout_ms": 0},
               "artifact_validate": {"checks": [
                   {"id": "f1", "type": "file_exists", "path": _tmp_file(tmp_path)}]}}
    out = et(payload)
    assert out["code"] == "timeout"
    assert "超时" in out["failure_info"]["error_msg"]


def test_error_channel_hmac_without_secret(monkeypatch):
    """P3-1：hmac 签发缺 AGENT_ENGINE_SECRET → 内核异常通道 code=error。"""
    monkeypatch.delenv("AGENT_ENGINE_SECRET", raising=False)
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "content_issue": {"sign": True, "sign_algo": "hmac-sha256"}}
    out = et(payload)
    assert out["code"] == "error"
    assert "AGENT_ENGINE_SECRET" in out["failure_info"]["error_msg"]


# ── failure_policy fallback / delivery transform ────────────────

def test_failure_policy_fallback_rewrites_delivery(tmp_path):
    """阻断 ≠ 死掉：fallback_target 兜底改写投递目标；非 success 不投递 payload。"""
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "artifact_validate": {"checks": [
                   {"id": "f1", "type": "file_exists",
                    "path": str(tmp_path / "nope.txt")}]},
               "failure_policy": {"fallback_target": "manual_queue"},
               "delivery": {"next_handler": "normal_handler", "mode": "single"}}
    out = et(payload)
    assert out["code"] == "reject"
    assert out["delivery"]["next_handler"] == "manual_queue"
    assert out["delivery"]["payload"] is None


def test_delivery_transform_include_mask():
    payload = {"trace_id": _tid(),
               "artifact": {"k1": "v1", "k2": "v2", "secret_field": "s3cret"},
               "content_issue": {"sign": True, "sign_algo": "sha256"},
               "delivery": {"next_handler": "h", "mode": "single",
                            "output_transform": {
                                "include_fields": ["k1", "secret_field"],
                                "mask_fields": ["secret_field"]}}}
    out = et(payload)
    assert out["code"] == "success"
    data = out["delivery"]["payload"]
    assert set(data.keys()) == {"k1", "secret_field"}
    assert data["secret_field"] == "***"


# ── 任务生命周期（隔离库） ───────────────────────────────────────

def test_task_lifecycle_complete():
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    payload = {"trace_id": _tid(), "artifact": {"k": "v"},
               "task": {"action": "complete", "task_id": task_id,
                        "evidence": {"output_file": "result.json"},
                        "targets": ["dsh"]}}
    out = et(payload)
    assert out["code"] == "success"
    tr = out["task_result"]
    assert tr["code"] == "success" and tr["to_state"] == "completed"
    assert tr["bridge"][0]["status"] == "skipped"  # 无注册 adapter：skipped 不阻塞
    from engine.state_store import SqliteStateStore
    state, ver = SqliteStateStore().get_state(task_id)
    assert state == "completed" and ver >= 1


def test_task_complete_requires_evidence():
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    payload = {"trace_id": _tid(), "artifact": {},
               "task": {"action": "complete", "task_id": task_id, "evidence": {}}}
    out = et(payload)
    assert out["code"] == "reject"
    # 语义注记：task 块失败发生在 failure_info 计算之后，失败理由在 task_result.reason
    assert out["failure_info"] is None
    assert "非空 evidence" in out["task_result"]["reason"]
