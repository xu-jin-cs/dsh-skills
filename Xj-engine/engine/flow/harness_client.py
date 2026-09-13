"""
Harness HTTP 客户端 — LangGraph ↔ Agent-Harness 数据桥接。

职责：
  LangGraph 所有外部持久化通过本客户端以 HTTP 回调方式上报到 Harness。
  Harness 是唯一的持久化存证平台，LangGraph 不做直接数据库写入。

设计原则（来自全局融合方案）：
  1. 单一权威数据源：运行时唯一可信数据为 LangGraph State，Harness 仅做镜像备份
  2. 写入顺序：LangGraph 先更新本地 Checkpoint，再异步上报 Harness
  3. 统一事件标准：所有同步事件共用一套 JSON 格式
  4. 无网络依赖：Harness 不可用时静默降级，不阻塞 LangGraph 执行

统一事件 JSON 格式（Harness 单接口统一接收）：
  {
    "instance_id": "ins_001",
    "event_type": "STATE_TRANSITION | DELIVERABLE_SUBMIT | VIOLATION | TEST_RESULT",
    "from_status": "PRD_REVIEW",
    "to_status": "SMOKE_TEST",
    "operator": "spm",
    "payload": {},
    "timestamp": "2026-06-29 14:30:00"
  }
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, Any
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger("langgraph.harness")


class HarnessSyncError(Exception):
    """
    Harness 同步失败异常。
    上游（CallbackManager / step()）捕获此异常时：
      - 记录违规
      - 冻结流程实例
      - 阻止节点标注完成
    """
    pass


# 默认 Harness API 地址（可通过环境变量覆盖）
HARNESS_API_BASE = os.environ.get(
    "HARNESS_API_BASE",
    os.environ.get("XJFRAME_HARNESS_API", "http://127.0.0.1:8001/api"),
)


class HarnessClient:
    """
    Harness HTTP API 客户端。

    封装所有上报接口：
      - transition():      上报流程状态变更
      - add_deliverable():  上报交付物
      - report_violation(): 上报违规记录
      - report_test():      上报测试结果
      - import_full_flow(): 任务结束批量导入快照
    """

    def __init__(self, base_url: str = HARNESS_API_BASE):
        self.base_url = base_url.rstrip("/")
        self._session = None
        self._build_session()

    def _build_session(self):
        """创建可复用的 HTTP session"""
        if not HAS_REQUESTS:
            return
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "langgraph-harness-client/1.0",
        })
        # 默认超时：连接 5s，读取 10s
        self._session.timeout = (5, 10)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """
        统一 HTTP 请求入口。
        失败直接抛出 HarnessSyncError——不再静默降级。
        上游捕获此异常后应当阻断流程、冻结实例。
        """
        if not HAS_REQUESTS or self._session is None:
            raise HarnessSyncError("requests 库不可用，无法同步 Harness")

        url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            resp = self._session.request(method, url, **kwargs)
        except requests.ConnectionError as e:
            raise HarnessSyncError(f"Harness 连接失败 ({url}): {e}")
        except requests.Timeout as e:
            raise HarnessSyncError(f"Harness 超时 ({url}): {e}")
        except Exception as e:
            raise HarnessSyncError(f"Harness 请求异常 ({url}): {e}")

        if resp.ok:
            return resp.json() or {}

        raise HarnessSyncError(
            f"Harness API {method} {url} → {resp.status_code}: {resp.text[:300]}"
        )

    # ─── 事件上报 ───────────────────────────────────────────────

    def send_event(
        self,
        instance_id: str,
        event_type: str,
        operator: str = "system",
        from_status: str = "",
        to_status: str = "",
        payload: Optional[dict] = None,
    ) -> dict:
        """
        统一事件上报入口（Harness POST /api/events）。

        event_type 支持：
          NODE_HEARTBEAT / VIOLATION / TEST_RESULT 等通用事件。
        STATE_TRANSITION / DELIVERABLE_SUBMIT 请使用对应的专用方法。
        """
        event = {
            "instance_id": instance_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "operator": operator,
            "payload": payload or {},
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self._request("POST", "/events", json=event)

    # ─── 流程状态变更 ───────────────────────────────────────────

    def transition(
        self,
        instance_id: str,
        to_state: str,
        operator: str = "system",
        comment: str = "",
    ) -> dict:
        """
        执行状态流转。
        直接调用 Harness instances API（非 send_event），确保经过 Guard 校验。
        """
        return self._request(
            "POST", f"/instances/{instance_id}/transition",
            json={
                "to_state": to_state,
                "operator": operator,
                "comment": comment,
            },
        )

    def freeze(
        self,
        instance_id: str,
        reason: str,
        operator: str = "sv-supervisor",
        violation_type: str = "MANUAL_FREEZE",
    ) -> dict:
        """
        冻结流程实例。
        直接调用 Harness freeze 端点（设置 is_frozen=True + 写入 Violation）。
        """
        return self._request(
            "POST", f"/instances/{instance_id}/freeze",
            json={
                "reason": reason,
                "operator": operator,
                "violation_type": violation_type,
            },
        )

    # ─── 交付物 ─────────────────────────────────────────────────

    def add_deliverable(
        self,
        instance_id: str,
        step: str,
        content_type: str,
        summary: str,
        agent_role: str = "",
        file_path: str = "",
    ) -> dict:
        """
        提交交付物到 Harness。
        直接调用 Harness deliverable 端点（含格式校验）。
        """
        return self._request(
            "POST", f"/instances/{instance_id}/deliverable",
            json={
                "step": step,
                "content_type": content_type,
                "summary": summary[:500],
                "operator": agent_role or "system",
                "agent_role": agent_role,
                "file_path": file_path,
            },
        )

    # ─── 违规记录 ───────────────────────────────────────────────

    def report_violation(
        self,
        instance_id: str,
        violation_type: str,
        description: str,
        operator: str = "system",
    ) -> dict:
        """上报违规到 Harness events 接口（写入 AuditLog）"""
        return self.send_event(
            instance_id=instance_id,
            event_type="VIOLATION",
            operator=operator,
            payload={
                "violation_type": violation_type,
                "description": description,
            },
        )

    # ─── 测试结果 ───────────────────────────────────────────────

    def report_test_result(
        self,
        instance_id: str,
        agent_role: str,
        skill_name: str,
        status: str,
        pass_count: int = 0,
        fail_count: int = 0,
        summary: str = "",
        report_data: Optional[dict] = None,
    ) -> dict:
        """上报测试结果到 Harness events 接口（写入 AuditLog）"""
        return self.send_event(
            instance_id=instance_id,
            event_type="TEST_RESULT",
            operator=agent_role,
            payload={
                "agent_role": agent_role,
                "skill_name": skill_name,
                "status": status,
                "passed_checks": pass_count,
                "failed_checks": fail_count,
                "summary": summary[:500],
                "report_data": report_data or {},
            },
        )

    # ─── 流程快照批量导入（任务结束） ──────────────────────────

    def import_full_flow(self, snapshot_json: dict) -> dict:
        """任务结束后一次性导入完整流程快照到 Harness"""
        return self._request("POST", "/projects/import", json=snapshot_json)

    # ─── 自愈事件上报（GOV-OUT-012） ────────────────────────────

    def report_self_heal_event(
        self,
        instance_id: str,
        rule_scope: str,
        rule_id: str,
        remediate_action: str = "",
        remediate_result: str = "success",
        violation_raw: str = "",
        operator: str = "自动自愈",
        flow_id: str = "",
        file_ref: str = "",
    ) -> dict:
        """
        上报自愈事件到 Harness 自愈网关（POST /api/self-heal/events）。

        对应《Harness 自愈模式》GOV-OUT-012：
        - SV 门禁拦截事件（阻断级）
        - 流程私有规则自愈事件
        - 全局输出治理格式化事件
        """
        return self._request(
            "POST", "/self-heal/events",
            json={
                "event_id": f"SHE-{datetime.now().strftime('%Y%m%d')}-{instance_id[:8] if instance_id else 'LGC'}",
                "task_id": instance_id,
                "flow_id": flow_id,
                "rule_scope": rule_scope,
                "rule_id": rule_id,
                "rule_source_file": f".claude/rules/{rule_scope}_rules.yaml",
                "violation_raw": violation_raw[:5000],
                "remediate_action": remediate_action,
                "remediate_result": remediate_result,
                "file_ref": file_ref,
                "operator": operator,
            },
        )

    # ─── 脉象事件上报（v1.1 — Harness Scale 三区） ────────────

    def report_pulse_event(
        self,
        instance_id: str,
        zone: str,
        metric_name: str,
        metric_value: float,
        pulse_position: str = "",
        tags: Optional[dict] = None,
    ) -> dict:
        """DEPRECATED（ENG-018，2026-08-20 审计）：/api/pulse/events 端点已删（零生产方零消费方），
        本函数留作脉象能力 backlog 参考，禁止新代码调用。
        上报脉象事件到 Harness（POST /api/pulse/events）。

        Harness Scale 三区：
          肾前 (kidney_front) — 流程调度健康度
          肾后 (kidney_back)   — 校验规则执行状态
          体液质量 (fluid_quality) — 元数据快照质量

        Args:
            instance_id: 流程实例 ID
            zone: 脉区 (kidney_front / kidney_back / fluid_quality)
            metric_name: 指标名
            metric_value: 指标值（归一化到 [0,1]）
            pulse_position: 脉象位置（cun/guan/chi，可选）
            tags: 附加标签
        """
        event = {
            "instance_id": instance_id,
            "zone": zone,
            "metric_name": metric_name,
            "metric_value": round(metric_value, 4),
            "pulse_position": pulse_position or "",
            "tags": tags or {},
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return self._request("POST", "/pulse/events", json=event)

    def report_pipeline_pulse(
        self,
        instance_id: str,
        from_state: str,
        to_state: str,
        is_healthy: bool,
        duration_seconds: float = 0.0,
    ) -> dict:
        """DEPRECATED（ENG-018，2026-08-20 审计）：/api/pulse/events 端点已删（零生产方零消费方），
        本函数留作脉象能力 backlog 参考，禁止新代码调用。
        肾前脉象 — 流程调度健康度。

        指标：
          - pipeline_health: 布尔→归一化值 (1.0/0.0)
          - transition_latency: 流转延迟(s)
        """
        tags = {
            "from_state": from_state,
            "to_state": to_state,
            "duration_seconds": int(duration_seconds),
        }
        return self.report_pulse_event(
            instance_id=instance_id,
            zone="kidney_front",
            metric_name="pipeline_health",
            metric_value=1.0 if is_healthy else 0.0,
            tags=tags,
        )

    def report_validation_pulse(
        self,
        instance_id: str,
        validator_name: str,
        passed: bool,
        details: str = "",
    ) -> dict:
        """DEPRECATED（ENG-018，2026-08-20 审计）：/api/pulse/events 端点已删（零生产方零消费方），
        本函数留作脉象能力 backlog 参考，禁止新代码调用。
        肾后脉象 — 校验规则执行状态。

        指标：
          - validation_pass_rate: 1.0 (通过) / 0.0 (失败)
        """
        return self.report_pulse_event(
            instance_id=instance_id,
            zone="kidney_back",
            metric_name="validation_pass_rate",
            metric_value=1.0 if passed else 0.0,
            tags={"validator": validator_name, "details": details[:200]},
        )

    def report_snapshot_pulse(
        self,
        instance_id: str,
        chunk_count: int,
        validity_ratio: float = 1.0,
        pulse_position: str = "",
    ) -> dict:
        """DEPRECATED（ENG-018，2026-08-20 审计）：/api/pulse/events 端点已删（零生产方零消费方），
        本函数留作脉象能力 backlog 参考，禁止新代码调用。
        体液质量脉象 — 元数据快照质量。

        指标：
          - snapshot_integrity: 快照完整性 (分片数/总片数)
          - data_validity_ratio: 数据有效比
        """
        return self.report_pulse_event(
            instance_id=instance_id,
            zone="fluid_quality",
            metric_name="snapshot_integrity",
            metric_value=validity_ratio,
            pulse_position=pulse_position,
            tags={"chunk_count": chunk_count},
        )

    # ─── 健康检查 ───────────────────────────────────────────────

    def health_check(self) -> bool:
        """检查 Harness 服务是否可用"""
        try:
            result = self._request("GET", "/health")
            return result.get("status") == "ok"
        except HarnessSyncError:
            return False


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_default_client: Optional[HarnessClient] = None


def get_harness_client() -> HarnessClient:
    """获取全局 HarnessClient 单例"""
    global _default_client
    if _default_client is None:
        _default_client = HarnessClient()
    return _default_client
