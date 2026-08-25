"""
测试四门禁独立域 ET 模块（39 Agent 引擎替换专项 U6，2026-08-17 落地）。

设计稿：docs/test_gates_et_design.md（方案B为体 + 方案A为用）：
  - 本模块（ET 层）持有全部业务规则：编号正则 / 三要素 / action 白名单 /
    豁免断言集 / 隔离角色语义 / B3 目录枚举与 total_steps 条件策略，
    并负责 FS 枚举与条件预计算分流（API/UI 用例分流、弱断言过滤）；
  - 裁决全部由内核 8 个通用 check 原语执行（kernel.py，零业务常量）；
  - 批次签发货走 content_issue 唯一入口：签名原文 canonical({trace_id,
    artifact, state_meta})，验签走 et_sign.verify_issue；签发算法用内核
    content_issue 现有默认（母体裁定④，不新造、不显式指定 sign_algo）。

旧模块 backend/engine/test_gates.py 与 backend/engine/signer.py 已退役，
归档于 _backups/20260817_legacy_engine_retirement/（RISK-20260817-03）。

expression 已永久移除：本模块不含、也不生成任何条件表达式检查；
条件型语义一律由「ET 预计算分流 + 内核通用原语」表达。
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from .et_contract import ETContract

# ═══════════════════════════════════════════════════════════════
# 业务规则常量（ET 层持有，与旧 test_gates.py 逐字节等价盘活）
# ═══════════════════════════════════════════════════════════════

# Q4：用例编号正则（旧 CASE_ID_RE 原文）
CASE_ID_PATTERN = r"^TC-[A-Z0-9-]+-\d{3,}(-[A-Z]+)?$"

# Q4：三要素（旧 THREE_ELEMENTS）
THREE_ELEMENTS = ("source_node", "source_branch", "test_methods")

# Q4：UI step action 白名单（旧 ACTION_WHITELIST，11 项）
ACTION_WHITELIST = [
    "goto", "click", "input", "select", "wait",
    "assert_text", "assert_visible", "assert_not_visible", "assert_value", "assert_url",
    "refresh",
]

# Q4：无需 expected_value 的断言动作（旧 _NO_EXPECTED_ASSERTS）
NO_EXPECTED_ASSERTS = frozenset({"assert_visible", "assert_not_visible"})

# 批次签发默认状态跃迁（对齐设计稿 §4.1 示例：FULL_TEST → CODE_REVIEW）
DEFAULT_BATCH_FROM_STATE = "FULL_TEST"
DEFAULT_BATCH_TO_STATE = "CODE_REVIEW"
BATCH_VERDICT = "BATCH_REVIEWED"


def _trace_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class TestGatesET(ETContract):
    """测试四门禁 ET：把门禁输入装配成标准 Payload，裁决交内核。

    四个域入口：
      case_format_payload(cases)                        —— Q4 用例格式门禁
      evidence_chain_payload(evidence_dir)              —— B3 证据链门禁
      cross_isolation_payload(designer, executor)       —— 交叉执行隔离
      sign_batch_payload(instance_id, batch_id, ...)    —— 批次签发（content_issue）
    """

    def build_payload(self, gate: str | None = None, **kw: Any) -> dict[str, Any]:
        """按门禁名分发到对应域入口（ETContract 契约实现）。"""
        dispatch = {
            "case_format": self.case_format_payload,
            "evidence_chain": self.evidence_chain_payload,
            "cross_isolation": self.cross_isolation_payload,
            "sign_batch": self.sign_batch_payload,
        }
        if gate not in dispatch:
            raise ValueError(f"未知测试门禁: {gate!r}（可选: {sorted(dispatch)}）")
        return dispatch[gate](**kw)

    # ═══════════════════════════════════════════════════════════
    # 门禁① Q4 用例格式
    # ═══════════════════════════════════════════════════════════

    def case_format_payload(
        self, cases: list[dict[str, Any]], trace_id: str | None = None
    ) -> dict[str, Any]:
        """Q4：编号格式 / 用例去重 / 三要素 / steps 非空 / action 白名单 / 弱断言。

        ET 职责（设计稿 §3.1）：
          - caseId → case_id 字段别名归一化（业务知识，放 ET）；
          - API/UI 用例预计算分流（request is not None → api_cases，否则 ui_cases）；
          - 弱断言过滤：需强断言的 assert 步骤（剔除 NO_EXPECTED_ASSERTS）
            注入 ui_assert_steps，expected_value 归一化为 strip 后字符串
            （等价旧逻辑 ``not str(expected_value or "").strip()``）。
        裁决（内核原语）：逐项正则 / 去重 / 必填非空 / 嵌套通配枚举。
        """
        norm_cases: list[dict[str, Any]] = []
        api_cases: list[dict[str, Any]] = []
        ui_cases: list[dict[str, Any]] = []
        ui_assert_steps: list[dict[str, Any]] = []

        for idx, case in enumerate(cases):
            c = dict(case)
            cid = str(c.get("case_id") or c.get("caseId") or "")
            c["case_id"] = cid
            c.pop("caseId", None)
            norm_cases.append(c)
            if c.get("request") is not None:
                api_cases.append(c)
                continue
            ui_cases.append(c)
            for si, step in enumerate(c.get("steps") or []):
                action = step.get("action", "") if isinstance(step, dict) else ""
                if action.startswith("assert_") and action not in NO_EXPECTED_ASSERTS:
                    ui_assert_steps.append({
                        "case_id": cid or f"#{idx}",
                        "step_no": si + 1,
                        "action": action,
                        "expected_value": str(step.get("expected_value") or "").strip(),
                    })

        return {
            "trace_id": trace_id or _trace_id("q4-fmt"),
            "artifact": {
                "cases": norm_cases,
                "ui_cases": ui_cases,
                "ui_assert_steps": ui_assert_steps,
                "api_cases": api_cases,
            },
            "artifact_validate": {"checks": [
                {"id": "Q4-ID-FORMAT", "type": "items_regex", "items_path": "cases",
                 "field": "case_id", "pattern": CASE_ID_PATTERN,
                 "message": "用例编号格式非法（TC-XX-NNN）"},
                {"id": "Q4-ID-UNIQUE", "type": "items_unique", "items_path": "cases",
                 "field": "case_id", "message": "用例编号重复"},
                {"id": "Q4-THREE-ELEMENTS", "type": "items_required_fields",
                 "items_path": "cases", "fields": list(THREE_ELEMENTS),
                 "nonempty": True, "message": "三要素缺失"},
                {"id": "Q4-STEPS-NONEMPTY", "type": "items_required_fields",
                 "items_path": "ui_cases", "fields": ["steps"],
                 "nonempty": True, "message": "steps 为空"},
                {"id": "Q4-ACTION-WHITELIST", "type": "items_enum",
                 "items_path": "ui_cases", "field": "steps[].action",
                 "values": list(ACTION_WHITELIST), "message": "action 不在白名单"},
                {"id": "Q4-WEAK-ASSERT", "type": "items_required_fields",
                 "items_path": "ui_assert_steps", "fields": ["expected_value"],
                 "nonempty": True, "message": "弱断言: expected_value 为空"},
                {"id": "Q4-API-REQUEST", "type": "items_required_fields",
                 "items_path": "api_cases", "fields": ["request.method", "request.path"],
                 "nonempty": True, "message": "API 用例 request 缺 method/path"},
                {"id": "Q4-API-EXPECTED", "type": "items_required_fields",
                 "items_path": "api_cases", "fields": ["expected"],
                 "nonempty": True, "message": "API 用例弱断言: expected 为空"},
            ]},
            "failure_policy": {"fallback_target": "test-lead", "alert_on_block": True},
            "audit_meta": {"principal": "test-lead", "audit_tags": ["case-format", "test-gates"]},
        }

    # ═══════════════════════════════════════════════════════════
    # 门禁② B3 证据链
    # ═══════════════════════════════════════════════════════════

    def evidence_chain_payload(
        self, evidence_dir: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        """B3：manifest 存在可解析 / 截图数==步骤数 / 哈希防复用 / audit.log。

        信任模型（设计稿 §3.2）：FS 枚举由本 ET 做，但计数、哈希、字段三类
        裁决性读取全部由内核独立重执行，ET 少报目录会被 dir_glob_count
        内核复核识破。

        total_steps 语义（母体裁定③，功能等价旧 B3）：ET 预解析 manifest，
        仅对声明了 total_steps 的用例目录生成计数对账 check；缺失则跳过
        该子项（其余子项照查），与旧门禁行为逐点等价。
        """
        root = os.path.abspath(os.path.expanduser(evidence_dir))
        checks: list[dict[str, Any]] = []
        case_dirs: list[str] = []

        if not os.path.isdir(root):
            checks.append({
                "id": "B3-DIR-EXISTS", "type": "dir_glob_count",
                "path": root, "pattern": "*", "min": 0,
                "message": f"证据目录不存在: {evidence_dir}",
            })
        else:
            # 证据非空：内核亲自 glob 复核 manifest 总数（防 ET 谎报空目录）
            checks.append({
                "id": "B3-NOT-EMPTY", "type": "dir_glob_count",
                "path": root, "pattern": "**/manifest.json", "min": 1,
                "message": "未发现任何 manifest.json（证据为空）",
            })
            for dirpath, _dirs, files in os.walk(root):
                if "manifest.json" not in files:
                    continue
                name = os.path.basename(dirpath)
                case_dirs.append(os.path.relpath(dirpath, root))
                manifest_path = os.path.join(dirpath, "manifest.json")
                checks.append({
                    "id": f"B3-MANIFEST-{name}", "type": "json_field",
                    "path": manifest_path, "fields": ["case_id"],
                    "message": "manifest 缺失或解析失败",
                })
                manifest = None
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                except Exception:
                    manifest = None  # 解析失败由上面的 json_field 原语裁决
                if isinstance(manifest, dict) and manifest.get("total_steps") is not None:
                    checks.append({
                        "id": f"B3-SHOT-COUNT-{name}", "type": "dir_file_count_eq_json",
                        "path": dirpath, "suffix": ".png",
                        "json_file": "manifest.json", "json_field": "total_steps",
                        "message": "截图数 != 步骤数（跳步）",
                    })
                checks.append({
                    "id": f"B3-HASH-{name}", "type": "dir_file_hash_unique",
                    "path": dirpath, "suffix": ".png", "algo": "md5",
                    "message": "截图 md5 复用（疑似伪造）",
                })
                checks.append({
                    "id": f"B3-AUDIT-{name}", "type": "file_exists",
                    "path": os.path.join(dirpath, "audit.log"),
                    "message": "缺 audit.log",
                })

        return {
            "trace_id": trace_id or _trace_id("b3-ev"),
            "artifact": {"evidence_dir": root, "case_dirs": case_dirs},
            "artifact_validate": {"checks": checks},
            "failure_policy": {"fallback_target": "test-lead", "alert_on_block": True},
            "audit_meta": {"principal": "test-lead", "audit_tags": ["evidence-chain", "test-gates"]},
        }

    # ═══════════════════════════════════════════════════════════
    # 门禁③ 交叉执行隔离
    # ═══════════════════════════════════════════════════════════

    def cross_isolation_payload(
        self, designer: str, executor: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        """交叉执行隔离：designer 非空且 == executor 即违例（ignore_empty 保留旧放行语义）。"""
        return {
            "trace_id": trace_id or _trace_id("xiso"),
            "artifact": {"designer": designer, "executor": executor},
            "artifact_validate": {"checks": [{
                "id": "XISO-DISTINCT", "type": "fields_distinct",
                "field_a": "designer", "field_b": "executor", "ignore_empty": True,
                "message": "设计者与执行者相同，违反交叉执行隔离",
            }]},
            "failure_policy": {"fallback_target": "test-lead", "alert_on_block": True},
            "audit_meta": {"principal": "test-lead", "audit_tags": ["cross-isolation", "test-gates"]},
        }

    # ═══════════════════════════════════════════════════════════
    # 门禁④ 批次签发（content_issue 唯一入口）
    # ═══════════════════════════════════════════════════════════

    def sign_batch_payload(
        self,
        instance_id: str,
        batch_id: str,
        operator: str,
        case_count: int | None = None,
        from_state: str = DEFAULT_BATCH_FROM_STATE,
        to_state: str = DEFAULT_BATCH_TO_STATE,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """批次签发：批次作为 artifact，content_issue 签发（设计稿 §3.4 / §4.1）。

        签名原文 = canonical({trace_id, artifact, state_meta})，覆盖批次全文
        （旧五元组签名不含 artifact 内容，新语义防批次内容替换）；
        签发算法用内核 content_issue 现有默认（母体裁定④），不显式指定 sign_algo。
        验签：et_sign.verify_issue(artifact, issue_meta, trace_id, state_meta)。
        """
        artifact: dict[str, Any] = {
            "artifact_type": "test_batch",
            "batch_id": batch_id,
            "instance_id": instance_id,
            "operator": operator,
            "verdict": BATCH_VERDICT,
        }
        if case_count is not None:
            artifact["case_count"] = case_count
        return {
            "trace_id": trace_id or _trace_id("sign"),
            "artifact": artifact,
            "state_intercept": {
                "current_state": from_state,
                "allowed_pairs": [{"from": from_state, "to": to_state}],
                "target_state": to_state,
                "state_meta": {"batch_id": batch_id, "operator": operator},
            },
            "content_issue": {"sign": True},
            "audit_meta": {"principal": operator, "audit_tags": ["sign-batch", "test-gates"]},
        }
