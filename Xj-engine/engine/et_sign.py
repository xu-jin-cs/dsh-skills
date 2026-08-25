"""
ET 签发验签辅助（P2-3 / P3-1）。

签名原文规则（内核 content_issue 与本模块共用同一份实现，禁止分叉）：
    canonical({
        "trace_id":   trace_id,
        "artifact":   artifact,
        "state_meta": {"current_state": ..., "target_state": ...}  # 取自 state_intercept spec，无则 {}
    })
canonical = json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)

支持 algo：sha256（纯哈希）/ hmac-sha256（密钥哈希）。

密钥（P3-1，2026-08-19 去私有化根治）：hmac-sha256 密钥只从环境变量
AGENT_ENGINE_SECRET 读取；不再内置任何回落密钥（密钥随代码分发 = 签名人人可伪造）。
缺 env 时 default_secret() 直接 raise SecretMissingError——生产由启动预检门禁
scripts/check_engine_secret.sh 强制注入，本地开发须自行 export。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

SECRET_ENV_KEY = "AGENT_ENGINE_SECRET"


class SecretMissingError(RuntimeError):
    """AGENT_ENGINE_SECRET 未注入：hmac-sha256 签发/验签不可用（不再提供内置回落）。"""


def default_secret() -> bytes:
    """解析内核默认密钥：仅读 env，缺省即抛 SecretMissingError。"""
    env = os.environ.get(SECRET_ENV_KEY)
    if not env:
        raise SecretMissingError(
            f"缺少环境变量 {SECRET_ENV_KEY}：hmac-sha256 签发必须显式注入密钥"
            "（生产由 check_engine_secret.sh 预检强制；本地开发请自行 export）。"
        )
    return env.encode("utf-8")


def canonical_sign_source(
    trace_id: str, artifact: Any, state_meta: dict | None = None
) -> str:
    """签名原文：canonical({trace_id, artifact, state_meta})。"""
    return json.dumps(
        {
            "trace_id": trace_id,
            "artifact": artifact,
            "state_meta": state_meta or {},
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def compute_signature(
    artifact: Any,
    trace_id: str,
    state_meta: dict | None = None,
    algo: str = "sha256",
    secret: str | bytes | None = None,
) -> str:
    """按统一规则计算签名。algo ∈ sha256 / hmac-sha256。"""
    canonical = canonical_sign_source(trace_id, artifact, state_meta)
    if algo == "hmac-sha256":
        key: bytes
        if secret:
            key = secret.encode("utf-8") if isinstance(secret, str) else secret
        else:
            key = default_secret()
        return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if algo == "sha256":
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    raise ValueError(f"不支持的签名算法: {algo}")


def verify_issue(
    artifact: Any,
    issue_meta: dict[str, Any],
    trace_id: str,
    state_meta: dict | None = None,
    secret: str | bytes | None = None,
) -> bool:
    """
    验签：按 content_issue 同一规则重算签名并与 issue_meta["signature"] 比对。

    - artifact     ：签发后的交付物（须与签发时逐字节等价，含 watermark 注入后的形态
                     取决于调用方传入的是否为 signed_artifact —— 与签发侧保持一致即可）
    - issue_meta   ：内核出参 issue_meta（需含 algo / signature）
    - trace_id     ：本次链路追踪 ID（换 trace_id 即验签失败）
    - state_meta   ：{"current_state", "target_state"}，取自 state_intercept spec，无则 None/{}
    - secret       ：hmac-sha256 密钥；缺省走 default_secret()（仅读 env，
                     未注入 AGENT_ENGINE_SECRET 时验签失败返回 False）
    """
    if not isinstance(issue_meta, dict):
        return False
    algo = issue_meta.get("algo", "sha256")
    signature = issue_meta.get("signature")
    if not signature or algo not in ("sha256", "hmac-sha256"):
        return False
    try:
        expected = compute_signature(
            artifact, trace_id, state_meta=state_meta, algo=algo, secret=secret
        )
    except Exception:
        return False
    return hmac.compare_digest(expected, str(signature))
