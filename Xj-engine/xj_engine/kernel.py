"""
引擎内核 — et() 统一执行入口（2026-08-16 按参考契约重构）。

执行时序（引擎固定，ET 不可改）：
  resource_control 前置 → artifact_validate(扩展) → state_intercept
  → gate_guard → content_issue → delivery 装配

出参 code 语义：
  success —— 全部已声明钩子通过，可投递
  reject  —— artifact_validate 交付物校验未通过
  block   —— state_intercept / gate_guard / resource_control 拦截
  timeout —— hook_timeout_ms / global_timeout_ms 超时（2026-08-22 起为抢占式：
            钩子在守护线程执行，超时即刻裁决返回，卡死钩子可被兜住）
  error   —— 内核或 content_issue 执行异常

内核无写死业务规则：ACL、跃迁规则、配额、失败策略全部来自 ET 组装的 payload。
"""

from __future__ import annotations

import copy
import glob
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from backend.engine import audit as _audit
from backend.engine import task as _task
from backend.engine.et_contract import (
    ContractViolationError,
    validate_output,
    validate_payload,
)
from backend.engine.et_sign import default_secret, compute_signature

_logger = logging.getLogger(__name__)

# 内核签发密钥（P3-1：content_issue 未显式给 secret 时使用；
# 2026-08-19 去私有化：改为签名时刻惰性解析——import 期不再读 env/告警，
# 未注入 AGENT_ENGINE_SECRET 时由 et_sign.SecretMissingError 经内核异常通道返回 code=error）
def _kernel_secret() -> bytes:
    return default_secret()


# FIX-SECRET（2026-08-20）：debug payload_snapshot 落出前递归掩码敏感字段，
# 防止 content_issue.secret 等密钥明文随 _debug 回显泄露
def _mask_snapshot(obj: Any) -> Any:
    """递归掩码快照：dict 中键名为 secret 的字符串值替换为 [MASKED len=N]，其余原样保留。"""
    if isinstance(obj, dict):
        return {
            k: (f"[MASKED len={len(v)}]" if k == "secret" and isinstance(v, str)
                else _mask_snapshot(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_snapshot(v) for v in obj]
    return obj

# 固定钩子时序（artifact_validate 为平台扩展校验钩子，先于状态拦截）
HOOK_ORDER = ("artifact_validate", "state_intercept", "gate_guard", "content_issue")


def _exec_with_timeout(fn: Callable[[], None], timeout_ms: float) -> bool:
    """抢占式超时执行（2026-08-22 短板修复：超时非抢占式根治）。

    fn 在守护线程中运行，裁决线程最多等待 timeout_ms：
    - 按时完成 → 返回 True（fn 内异常原样回抛，走内核 error 通道）；
    - 超时 → 立即返回 False，不再等待钩子收尾，裁决立刻返回 code=timeout。

    语义明示（无法安全抢占的残余面）：Python 不能安全强杀线程，超时钩子
    线程以 daemon 形态被遗弃继续空转，但其产出（钩子内局部变量/返回值）
    不再被内核消费——卡死钩子无法绕过 hook_timeout_ms / global_timeout_ms，
    仅付出一个泄漏线程的代价。钩子均为内核内置纯函数（校验/签发/门禁），
    无外部副作用句柄，遗弃是安全的。
    """
    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 — 原样回抛裁决线程
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True, name="et-hook")
    t.start()
    t.join(timeout_ms / 1000.0)
    if t.is_alive():
        return False
    if "error" in box:
        raise box["error"]
    return True


# ═══════════════════════════════════════════════════════════════
# 服务端权威计量（2026-08-22 短板修复：配额 ET 自报可伪造根治）
#
# 原则：ET 上报的 rate_current/token_used/cost_used/concurrent_current
# 仅作参考输入，超限一律由内核侧判定：
#   - 并发：内核自测 et() 在飞请求数（gauge），真权威计量；
#   - 速率：内核按 key 自维护 60s 滑窗请求计数，真权威计量；
#   - token/cost：消耗发生在 ET 侧（LLM 计费），内核无独立计量源，
#     以「按身份单调高水位台账」夹紧——有效用量 = max(ET上报, 内核台账)，
#     台账只增不减：报低（含重置计数器式伪造）立即被夹回台账值，
#     报高只会自我封禁。残余限制：对「始终低报且从未触限」内核无法识别，
#     该面需平台层计费对账兜底（契约 description 已同步注明）。
# ═══════════════════════════════════════════════════════════════

_QUOTA_LOCK = threading.Lock()
_IN_FLIGHT = 0                              # 内核自测并发：当前 et() 在飞请求数
_RATE_WINDOW_SEC = 60.0                     # 速率滑窗（固定 60s）
_RATE_EVENTS: dict[str, deque] = {}         # key -> 请求时间戳滑窗（内核自计数）
_USAGE_LEDGER: dict[str, dict[str, float]] = {}  # identity -> token/cost 单调高水位台账


def _quota_identity(payload: dict[str, Any]) -> str:
    """配额台账身份：audit_meta.principal 优先，其次 tenant_id，兜底 anon。"""
    meta = payload.get("audit_meta") or {}
    return str(meta.get("principal") or meta.get("tenant_id") or "anon")


def _in_flight_acquire() -> None:
    global _IN_FLIGHT
    with _QUOTA_LOCK:
        _IN_FLIGHT += 1


def _in_flight_release() -> None:
    global _IN_FLIGHT
    with _QUOTA_LOCK:
        _IN_FLIGHT -= 1


def _kernel_concurrency() -> int:
    with _QUOTA_LOCK:
        return _IN_FLIGHT


def _kernel_rate(key: str) -> int:
    """记录本次请求并返回滑窗内请求数（内核侧自计数，ET 无法伪造）。"""
    now = time.monotonic()
    with _QUOTA_LOCK:
        dq = _RATE_EVENTS.setdefault(key, deque())
        cutoff = now - _RATE_WINDOW_SEC
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        return len(dq)


def _kernel_usage_clamp(identity: str, field: str, reported: float) -> float:
    """单调高水位夹紧：有效用量 = max(ET 上报, 内核台账)，台账只增不减。"""
    with _QUOTA_LOCK:
        ledger = _USAGE_LEDGER.setdefault(identity, {})
        effective = max(float(reported), ledger.get(field, 0.0))
        ledger[field] = effective
        return effective


def _emit_hook_audit(
    hook: str,
    trace_id: str,
    decision: str,
    rule_hits: list | None = None,
    reason: str = "",
    elapsed_ms: float = 0.0,
) -> None:
    """四钩子判定审计落库（P2-6 接线，2026-08-17 短板2改造）。

    - 仅在审计存储已绑定（main.py lifespan set_engine）时落库；
      未绑定（内核单元测试直跑）直接跳过，避免测试流量污染生产库。
    - 落库异常仅告警不阻断裁决——审计是旁路留痕，不反向影响门禁判定。
    """
    if not _audit.is_bound():
        return
    try:
        _audit.emit_hook_event(
            hook, trace_id,
            decision=decision, rule_hits=rule_hits or [], reason=reason,
            extra={"hook": hook, "elapsed_ms": elapsed_ms},
        )
    except Exception as exc:  # noqa: BLE001 — 旁路审计不得阻断裁决
        _logger.warning("hook [%s] 审计落库失败（裁决不受影响）: %s", hook, exc)


# ═══════════════════════════════════════════════════════════════
# artifact 点号路径工具
# ═══════════════════════════════════════════════════════════════

def _get_path(obj: Any, dotted: str, default: Any = None) -> Any:
    """点号路径解析；支持 `a[].b` 一层嵌套通配（2026-08-17 U6 扩展）。

    - 普通段：逐层下钻 dict，缺键返回 default（与原语义逐字节等价）。
    - 通配段 `key[]`：当前层须为含 key 的 dict 且值为 list；
      通配为末段时返回该 list 本体，否则对列表每项递归解析剩余路径，
      返回每项结果组成的 list（项内缺键得 default）。
    """
    return _resolve_path(obj, dotted.split("."), default)


def _resolve_path(cur: Any, parts: list[str], default: Any) -> Any:
    if not parts:
        return cur
    part = parts[0]
    if part.endswith("[]"):
        key = part[:-2]
        if not isinstance(cur, dict) or key not in cur:
            return default
        seq = cur[key]
        if not isinstance(seq, list):
            return default
        rest = parts[1:]
        if not rest:
            return seq
        return [_resolve_path(item, rest, default) for item in seq]
    if isinstance(cur, dict) and part in cur:
        return _resolve_path(cur[part], parts[1:], default)
    return default


# ═══════════════════════════════════════════════════════════════
# artifact_validate：交付物校验（平台扩展钩子）
# ═══════════════════════════════════════════════════════════════

def _check_required_fields(check: dict, artifact: Any) -> tuple[bool, str]:
    fields = check.get("fields") or []
    text_source = check.get("text_source")
    if text_source:
        text = str(_get_path(artifact, text_source, ""))
        missing = [f for f in fields if f not in text]
    elif isinstance(artifact, dict):
        missing = [f for f in fields if f not in artifact]
    else:
        missing = fields
    return (not missing), (f"缺少必要字段: {', '.join(missing)}" if missing else "")


def _check_file_exists(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    if not os.path.isfile(path):
        return False, f"文件不存在或不是文件: {path}"
    if os.path.getsize(path) == 0:
        return False, f"文件为空（0 字节）: {path}"
    return True, ""


def _check_file_min_size(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    if not os.path.isfile(path):
        return False, f"文件不存在: {path}"
    size = os.path.getsize(path)
    min_size = check.get("min_size", 1)
    if size < min_size:
        return False, f"文件大小 {size}B 低于阈值 {min_size}B: {path}"
    return True, ""


def _check_json_field(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return False, f"JSON 解析失败: {path}（{exc}）"
    fields = check.get("fields") or []
    missing = [f for f in fields if not isinstance(data, dict) or f not in data]
    return (not missing), (f"JSON 缺少字段: {', '.join(missing)}" if missing else "")


def _check_regex(check: dict, artifact: Any) -> tuple[bool, str]:
    text = str(_get_path(artifact, check.get("text_source", ""), ""))
    if re.search(check.get("pattern", ""), text, re.MULTILINE) is None:
        return False, f"文本未命中必需模式: {check.get('pattern')}"
    return True, ""


def _check_min_ratio(check: dict, artifact: Any) -> tuple[bool, str]:
    try:
        num, den = float(check["numerator"]), float(check["denominator"])
    except (KeyError, TypeError, ValueError):
        return False, "min_ratio 参数非法（numerator/denominator 须为数值）"
    if den <= 0:
        return False, "min_ratio 分母必须为正数"
    ratio = num / den
    min_v = check.get("min", 0)
    return (ratio >= min_v), ("" if ratio >= min_v else f"比率 {ratio:.2%} 低于阈值 {min_v:.2%}")


# ═══════════════════════════════════════════════════════════════
# 通用扩展原语（2026-08-17 测试四门禁迁移专项 U6）
# 设计：docs/test_gates_et_design.md §3.5 —— 全部通用、零业务常量，
# 规则（正则/白名单/阈值/算法名）一律由 payload 注入。
# ═══════════════════════════════════════════════════════════════

_MISSING = object()  # 区别于 None 的"键缺失"哨兵


def _iter_items(check: dict, artifact: Any) -> list:
    """取 items_path 指向的数组；缺失/非数组一律按空数组处理（无项即无违例）。"""
    items = _get_path(artifact, check.get("items_path", ""), default=[])
    return items if isinstance(items, list) else []


def _check_items_regex(check: dict, artifact: Any) -> tuple[bool, str]:
    items = _iter_items(check, artifact)
    field = check.get("field", "")
    pattern = check.get("pattern", "")
    bad: list[str] = []
    for i, item in enumerate(items):
        value = _get_path(item, field, default="") if isinstance(item, dict) else ""
        text = "" if value is None else str(value)
        if re.search(pattern, text) is None:
            bad.append(f"#{i}[{field}]={text!r}")
    if bad:
        return False, f"{len(bad)} 项未命中正则 {pattern}: {'; '.join(bad)}"
    return True, ""


def _check_items_unique(check: dict, artifact: Any) -> tuple[bool, str]:
    items = _iter_items(check, artifact)
    field = check.get("field", "")
    seen: set[str] = set()
    dups: list[str] = []
    for item in items:
        value = _get_path(item, field) if isinstance(item, dict) else None
        if value is None or value == "":
            continue  # 空值不参与去重（缺失由其他原语裁决）
        key = str(value)
        if key in seen and key not in dups:
            dups.append(key)
        seen.add(key)
    if dups:
        return False, f"字段 {field} 存在重复值: {', '.join(dups)}"
    return True, ""


def _check_items_required_fields(check: dict, artifact: Any) -> tuple[bool, str]:
    items = _iter_items(check, artifact)
    fields = check.get("fields") or []
    nonempty = bool(check.get("nonempty"))
    problems: list[str] = []
    for i, item in enumerate(items):
        missing: list[str] = []
        for f in fields:
            value = _get_path(item, f, default=_MISSING) if isinstance(item, dict) else _MISSING
            if value is _MISSING or (nonempty and not value):
                missing.append(f)
        if missing:
            problems.append(f"#{i} 缺 {','.join(missing)}")
    if problems:
        return False, f"数组 {check.get('items_path', '')} 存在缺字段项: {'; '.join(problems)}"
    return True, ""


def _check_items_enum(check: dict, artifact: Any) -> tuple[bool, str]:
    items = _iter_items(check, artifact)
    field = check.get("field", "")
    values = check.get("values") or []
    bad: list[str] = []
    for i, item in enumerate(items):
        if "[]" in field:
            resolved = _get_path(item, field, default=_MISSING)
            if resolved is _MISSING:
                continue  # 通配序列缺失 → 无值可裁（空序列由其他原语裁决）
            seq = resolved if isinstance(resolved, list) else [resolved]
            for j, v in enumerate(seq):
                vv = "" if v is None else v
                if vv not in values:
                    bad.append(f"#{i}.{j}={vv!r}")
        else:
            v = _get_path(item, field, default=None) if isinstance(item, dict) else None
            vv = "" if v is None else v
            if vv not in values:
                bad.append(f"#{i}={vv!r}")
    if bad:
        return False, f"字段 {field} 存在枚举外取值: {'; '.join(bad)}"
    return True, ""


def _check_dir_glob_count(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    if not os.path.isdir(path):
        return False, f"目录不存在: {path}"
    pattern = check.get("pattern", "*")
    min_count = check.get("min", 1)
    count = len(glob.glob(os.path.join(path, pattern), recursive=True))
    if count < min_count:
        return False, f"目录匹配数 {count} 低于下限 {min_count}: {path}/{pattern}"
    return True, ""


def _check_dir_file_count_eq_json(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    if not os.path.isdir(path):
        return False, f"目录不存在: {path}"
    json_path = os.path.join(path, check.get("json_file", ""))
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return False, f"JSON 解析失败: {json_path}（{exc}）"
    json_field = check.get("json_field", "")
    expected = data.get(json_field) if isinstance(data, dict) else None
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return False, f"JSON 字段 {json_field} 缺失或非数值: {json_path}"
    suffix = check.get("suffix", "")
    count = sum(
        1 for name in os.listdir(path)
        if name.endswith(suffix) and os.path.isfile(os.path.join(path, name))
    )
    if count != expected:
        return False, f"目录文件数 {count} != 声明值 {expected}（{json_field}）: {path}"
    return True, ""


def _check_dir_file_hash_unique(check: dict, artifact: Any) -> tuple[bool, str]:
    path = os.path.abspath(os.path.expanduser(check.get("path", "")))
    if not os.path.isdir(path):
        return False, f"目录不存在: {path}"
    algo = check.get("algo", "md5")
    try:
        hashlib.new(algo)
    except (ValueError, TypeError) as exc:
        return False, f"不支持的哈希算法 {algo}: {exc}"
    suffix = check.get("suffix", "")
    files = sorted(
        name for name in os.listdir(path)
        if name.endswith(suffix) and os.path.isfile(os.path.join(path, name))
    )
    digests: set[str] = set()
    reused: list[str] = []
    for name in files:
        h = hashlib.new(algo)
        with open(os.path.join(path, name), "rb") as f:
            h.update(f.read())
        digest = h.hexdigest()
        if digest in digests:
            reused.append(name)
        digests.add(digest)
    if reused:
        return False, f"文件内容哈希复用（{algo}）: {', '.join(reused)}"
    return True, ""


def _check_fields_distinct(check: dict, artifact: Any) -> tuple[bool, str]:
    field_a = check.get("field_a", "")
    field_b = check.get("field_b", "")
    a = _get_path(artifact, field_a)
    b = _get_path(artifact, field_b)
    if check.get("ignore_empty") and (a in (None, "") or b in (None, "")):
        return True, ""
    if a == b:
        return False, f"字段 {field_a} 与 {field_b} 取值相同（{a!r}），违反相异约束"
    return True, ""


_VALIDATE_DISPATCH: dict[str, Callable[[dict, Any], tuple[bool, str]]] = {
    "required_fields": _check_required_fields,
    "file_exists": _check_file_exists,
    "file_min_size": _check_file_min_size,
    "json_field": _check_json_field,
    "regex": _check_regex,
    "min_ratio": _check_min_ratio,
    # 通用扩展原语（U6，零业务常量）
    "items_regex": _check_items_regex,
    "items_unique": _check_items_unique,
    "items_required_fields": _check_items_required_fields,
    "items_enum": _check_items_enum,
    "dir_glob_count": _check_dir_glob_count,
    "dir_file_count_eq_json": _check_dir_file_count_eq_json,
    "dir_file_hash_unique": _check_dir_file_hash_unique,
    "fields_distinct": _check_fields_distinct,
}


def _run_artifact_validate(spec: dict[str, Any], artifact: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for check in spec["checks"]:
        handler = _VALIDATE_DISPATCH[check["type"]]
        ok, reason = handler(check, artifact)
        item = {
            "id": check["id"],
            "type": check["type"],
            "passed": ok,
            "message": check.get("message") or reason,
        }
        results.append(item)
        if not ok:
            failures.append(item)
    return {"pass": not failures, "results": results, "failures": failures}


# ═══════════════════════════════════════════════════════════════
# state_intercept：状态拦截 & 跃迁
# ═══════════════════════════════════════════════════════════════

def _run_state_intercept(
    spec: dict[str, Any], artifact: Any
) -> tuple[bool, str | None, Any, str]:
    """
    返回 (passed, new_task_state, artifact', reason)。
    跃迁规则由 ET 预先编译注入：
      - allowed_pairs（推荐）：严格校验 (current_state, target_state) ∈ 对集合；
      - allow_transition（弱模式，未提供 allowed_pairs 时回退）：仅查 current ∈ 源集合。
    """
    current = spec.get("current_state")
    if current is None and isinstance(artifact, dict):
        current = artifact.get("state")
    target = spec.get("target_state")
    pairs = spec.get("allowed_pairs")
    if pairs is not None:
        pair_set = {(p.get("from"), p.get("to")) for p in pairs}
        if (current, target) not in pair_set:
            return False, None, artifact, (
                f"跃迁对 [{current} → {target}] 不在 allowed_pairs 合法集合内"
            )
    else:
        # 弱模式回退：只校验源状态，不校验目标（契约已标注不推荐）
        allow = spec.get("allow_transition")
        if allow is not None and current not in allow:
            return False, None, artifact, (
                f"源状态 [{current}] 不在允许跃迁集合 {allow}"
            )
    if spec.get("state_meta") and isinstance(artifact, dict):
        artifact = {**artifact, "state_meta": spec["state_meta"]}
    return True, target, artifact, f"{current} → {target} 合法"


# ═══════════════════════════════════════════════════════════════
# gate_guard：门禁准入
# ═══════════════════════════════════════════════════════════════

def _run_gate_guard(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("acl") is not None:
        target = spec.get("target_agent_id", "")
        if target not in spec["acl"]:
            return {"pass": False,
                    "reason": f"下游 Agent [{target}] 不在 ACL: {spec['acl']}"}
    if spec.get("rate_limit") is not None:
        # 服务端权威计量：内核按 key 自维护 60s 滑窗计数，ET 上报 rate_current
        # 仅作参考——有效速率 = max(ET上报, 内核实测)，报低无法穿透限流
        key = spec.get("target_agent_id") or spec.get("route") or "global"
        measured = _kernel_rate(key)
        reported = spec.get("rate_current")
        effective = max(reported if reported is not None else 0, measured)
        if effective >= spec["rate_limit"]:
            return {"pass": False,
                    "reason": (f"速率超限: {effective}/{spec['rate_limit']}"
                               f"（内核 60s 滑窗实测 {measured}，ET 上报 {reported}）")}
    if spec.get("route_whitelist") is not None:
        route = spec.get("route", "")
        if route not in spec["route_whitelist"]:
            return {"pass": False,
                    "reason": f"路由 [{route}] 不在白名单: {spec['route_whitelist']}"}
    return {"pass": True, "reason": ""}


# ═══════════════════════════════════════════════════════════════
# content_issue：内容签发 / 防篡改
# ═══════════════════════════════════════════════════════════════

def _content_fingerprint(artifact: Any) -> str:
    """内容指纹：sha256(canonical(artifact))[:12]，水印派生源（ENG-WM-ASYMM）。

    canonical 规则与 et_sign.canonical_sign_source 一致（sort_keys + 紧凑分隔符 +
    ensure_ascii=False）；artifact 须为注水印前形态（消费方对交付物先剔 _watermark 键）。
    """
    canonical = json.dumps(
        artifact, separators=(",", ":"), sort_keys=True,
        ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _run_content_issue(
    spec: dict[str, Any], artifact: Any, trace_id: str,
    state_spec: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """返回 (signed_artifact, issue_meta)。

    签名原文（P2-3）：canonical({trace_id, artifact, state_meta})，
    state_meta = {current_state, target_state} 取自 state_intercept spec，无则 {}。
    artifact 为注水印后的终态（ENG-WM-ASYMM：签名覆盖水印，交付物逐字节可验）。
    验签走 backend.engine.et_sign.verify_issue（同一规则重算）。
    """
    issue_meta: dict[str, Any] = dict(spec.get("attach_issue_meta") or {})
    signed = artifact

    if spec.get("sign"):
        algo = spec.get("sign_algo", "sha256")
        sign_state = (
            {
                "current_state": state_spec.get("current_state"),
                "target_state": state_spec.get("target_state"),
            }
            if state_spec else {}
        )
        secret = spec.get("secret")  # str | None；None 且 hmac 时走内核默认密钥（仅签名时刻惰性解析）
        if not secret and algo == "hmac-sha256":
            secret = _kernel_secret()  # 缺 AGENT_ENGINE_SECRET 在此 raise → 内核异常通道 code=error
        if spec.get("watermark"):
            # ENG-WM-ASYMM（2026-08-20 形态不对称根治）：水印先于签名注入。
            # 水印派生自内容指纹（与签名解耦，破除「签名覆盖最终形态 ↔ 水印含签名
            # 截段」循环依赖）；签名覆盖含水印终态 → verify_issue 对交付物逐字节可验，
            # 水印篡改即验签失败。消费方按同一规则（剔 _watermark 后重算指纹）比对。
            wm = f"wm:{trace_id}:{_content_fingerprint(artifact)}"
            if isinstance(signed, dict):
                signed = {**signed, "_watermark": wm}
            issue_meta["watermark"] = wm
        signature = compute_signature(
            signed, trace_id, state_meta=sign_state, algo=algo,
            secret=secret,
        )
        issue_meta.update({
            "algo": algo,
            "signature": signature,
            "issued_at": datetime.now(timezone.utc).isoformat(),
        })
    return signed, issue_meta


# ═══════════════════════════════════════════════════════════════
# resource_control：资源 & 配额前置检查
# ═══════════════════════════════════════════════════════════════

def _run_resource_control(spec: dict[str, Any], identity: str = "anon") -> dict[str, Any]:
    """资源/配额前置检查（服务端权威计量版，2026-08-22）。

    ET 自报值仅作参考输入，超限由内核侧判定：
    - 并发：有效并发 = max(ET上报, 内核在飞 gauge 实测)；
    - token/cost：有效用量 = max(ET上报, 内核按身份单调高水位台账)；
    出参附 metering 明细（reported/kernel/effective），伪造痕迹可审计。
    """
    violations: list[str] = []
    metering: dict[str, Any] = {}
    if spec.get("token_limit") is not None:
        reported = spec.get("token_used")
        effective = _kernel_usage_clamp(identity, "token", reported or 0)
        metering["token"] = {"reported": reported, "kernel_ledger": effective}
        if effective >= spec["token_limit"]:
            violations.append(f"token 超限: {effective}/{spec['token_limit']}"
                              f"（ET 上报 {reported}，内核台账夹紧）")
    if spec.get("max_concurrent") is not None:
        reported = spec.get("concurrent_current")
        measured = _kernel_concurrency()
        effective = max(reported if reported is not None else 0, measured)
        metering["concurrent"] = {"reported": reported, "kernel_measured": measured}
        if effective >= spec["max_concurrent"]:
            violations.append(
                f"并发超限: {effective}/{spec['max_concurrent']}"
                f"（内核实测 {measured}，ET 上报 {reported}）")
    if spec.get("cost_budget") is not None:
        reported = spec.get("cost_used")
        effective = _kernel_usage_clamp(identity, "cost", reported or 0)
        metering["cost"] = {"reported": reported, "kernel_ledger": effective}
        if effective >= spec["cost_budget"]:
            violations.append(f"成本超预算: {effective}/{spec['cost_budget']}"
                              f"（ET 上报 {reported}，内核台账夹紧）")
    if spec.get("model_allow_list"):
        model = spec.get("model", "")
        if model not in spec["model_allow_list"]:
            violations.append(f"模型 [{model}] 不在允许列表: {spec['model_allow_list']}")
    out: dict[str, Any] = {"pass": not violations, "violations": violations,
                           "priority": spec.get("priority", "normal")}
    if metering:
        out["metering"] = metering
    return out


# ═══════════════════════════════════════════════════════════════
# failure_policy / delivery
# ═══════════════════════════════════════════════════════════════

def _apply_failure_policy(
    policy: dict[str, Any] | None, error_msg: str,
    executed_retry: int = 0,
) -> dict[str, Any]:
    """阻断 ≠ 直接死掉：重试阶梯 / 兜底人工 / 补偿 / 告警，全部汇入 failure_info。

    说明：compensation_action 仅原样透传进 failure_info —— 执行主体是平台层
    （内核保持无状态，不执行任何回滚/撤销动作）；executed_retry 记录
    artifact_validate 钩子实际已执行的重试次数（仅该校验幂等可重试）。
    """
    info: dict[str, Any] = {"error_msg": error_msg}
    if policy:
        if policy.get("fallback_target"):
            info["fallback_target"] = policy["fallback_target"]
        if policy.get("max_retry") is not None:
            info["max_retry"] = policy["max_retry"]
            info["retry_delay_ms"] = policy.get("retry_delay_ms", 0)
            info["executed_retry"] = executed_retry
        if policy.get("compensation_action"):
            info["compensation_action"] = policy["compensation_action"]
        if policy.get("alert_on_block"):
            info["alert"] = True
            # ENG-007（2026-08-20 审计）：补 alert 的最小真实消费方——此前「阻断即告警」
            # 是幻觉承诺（alert=True 石沉大海）。平台级告警执行体暂以日志告警落地，
            # 接真实告警通道时替换本行即可。
            _logger.warning("ALERT_ON_BLOCK: %s", error_msg)
    return info


def _apply_delivery(
    spec: dict[str, Any], artifact: Any, code: str
) -> dict[str, Any]:
    """success 时产出投递载荷（可轻量裁剪/脱敏/字段过滤）；否则 payload 为 null。"""
    out: dict[str, Any] = {
        "next_handler": spec.get("next_handler"),
        "require_ack": bool(spec.get("require_ack", False)),
        "mode": spec.get("mode", "single"),
        "payload": None,
    }
    if code != "success":
        return out
    transform = spec.get("output_transform")
    data = artifact
    if transform and isinstance(artifact, dict):
        data = dict(artifact)
        if transform.get("include_fields"):
            data = {k: data[k] for k in transform["include_fields"] if k in data}
        if transform.get("exclude_fields"):
            data = {k: v for k, v in data.items() if k not in transform["exclude_fields"]}
        for field in transform.get("mask_fields", []):
            if isinstance(data.get(field), str):
                data[field] = "***"
    out["payload"] = data
    return out


# ═══════════════════════════════════════════════════════════════
# 内核唯一入口
# ═══════════════════════════════════════════════════════════════

def et(payload: dict[str, Any]) -> dict[str, Any]:
    """
    引擎内核统一入口。

    入参：符合 et_contract.PAYLOAD_SCHEMA 的标准 Payload（通常由 ET 实现类生成，
    也可是任何外部系统直接构造的 dict —— 内核只认契约）。

    出参：符合 et_contract.OUTPUT_SCHEMA 的标准出参。
    契约不通过时抛 ContractViolationError。
    """
    validate_payload(payload)
    _in_flight_acquire()  # 服务端权威并发计量：进入即在飞
    try:
        return _et_inner(payload)
    finally:
        _in_flight_release()


def _et_inner(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = copy.deepcopy(payload["artifact"])
    trace_id = payload["trace_id"]
    code = "success"
    error_msg = ""

    new_task_state: str | None = None
    gate_result: dict[str, Any] | None = None
    validate_result: dict[str, Any] | None = None
    resource_out: dict[str, Any] | None = None
    signed_artifact: Any = None
    issue_meta: dict[str, Any] | None = None
    hook_elapsed: dict[str, float] = {}
    task_result: dict[str, Any] | None = None

    rc = payload.get("resource_control") or {}
    hook_timeout_ms = rc.get("hook_timeout_ms")
    global_timeout_ms = rc.get("global_timeout_ms")
    t_start = time.monotonic()
    executed_retry = 0  # artifact_validate 实际已执行的重试次数（failure_policy 消费）

    # ── 前置：资源 & 配额（服务端权威计量：ET 自报仅作参考） ──
    if payload.get("resource_control"):
        resource_out = _run_resource_control(
            payload["resource_control"], identity=_quota_identity(payload))
        if not resource_out["pass"]:
            code = "block"
            error_msg = "; ".join(resource_out["violations"])

    # ── 固定钩子时序 ──
    if code == "success":
        for hook in HOOK_ORDER:
            spec = payload.get(hook)
            if spec is None:
                continue
            if global_timeout_ms and (time.monotonic() - t_start) * 1000 > global_timeout_ms:
                code = "timeout"
                error_msg = f"全局超时: 已超过 {global_timeout_ms}ms（hook [{hook}] 未执行）"
                break
            # ── 抢占式时限（2026-08-22 短板修复）：hook_timeout_ms 与
            # 全局剩余预算取小，超时即刻判 timeout，不再等钩子跑完 ──
            eff_timeout_ms: float | None = None
            if hook_timeout_ms is not None:
                eff_timeout_ms = float(hook_timeout_ms)
            if global_timeout_ms:
                remaining_ms = global_timeout_ms - (time.monotonic() - t_start) * 1000
                eff_timeout_ms = (min(eff_timeout_ms, remaining_ms)
                                  if eff_timeout_ms is not None else remaining_ms)

            def _invoke_hook() -> None:
                nonlocal code, error_msg, executed_retry, artifact
                nonlocal validate_result, new_task_state, gate_result
                nonlocal signed_artifact, issue_meta
                if hook == "artifact_validate":
                    # failure_policy 实执行：max_retry + retry_delay_ms 仅对本钩子
                    # 做有界重试（该校验幂等）；重试期间遵守 global_timeout_ms 上限
                    policy = payload.get("failure_policy") or {}
                    max_retry = policy.get("max_retry") or 0
                    retry_delay_s = (policy.get("retry_delay_ms") or 0) / 1000.0
                    while True:
                        validate_result = _run_artifact_validate(spec, artifact)
                        if validate_result["pass"] or executed_retry >= max_retry:
                            break
                        if global_timeout_ms and (
                            (time.monotonic() - t_start) * 1000
                            + retry_delay_s * 1000 > global_timeout_ms
                        ):
                            break  # 再等会越全局超时上限，停止重试，维持本次失败结论
                        if retry_delay_s:
                            time.sleep(retry_delay_s)
                        executed_retry += 1
                    if not validate_result["pass"]:
                        code = "reject"
                        error_msg = "; ".join(
                            f["message"] for f in validate_result["failures"])
                elif hook == "state_intercept":
                    ok, new_task_state, artifact, reason = _run_state_intercept(spec, artifact)
                    if not ok:
                        code = "block"
                        error_msg = reason
                elif hook == "gate_guard":
                    gate_result = _run_gate_guard(spec)
                    if not gate_result["pass"]:
                        code = "block"
                        error_msg = gate_result["reason"]
                elif hook == "content_issue":
                    signed_artifact, issue_meta = _run_content_issue(
                        spec, artifact, trace_id,
                        state_spec=payload.get("state_intercept"),
                    )

            t0 = time.monotonic()
            completed = True
            if eff_timeout_ms is not None and eff_timeout_ms <= 0:
                # 预算已耗尽：钩子不再执行，确定性判超时（0 预算场景无调度竞态）
                completed = False
            elif eff_timeout_ms is None:
                try:
                    _invoke_hook()
                except Exception as exc:  # 内核/签发异常
                    code = "error"
                    error_msg = f"hook [{hook}] 执行异常: {exc}"
            else:
                try:
                    completed = _exec_with_timeout(_invoke_hook, eff_timeout_ms)
                except Exception as exc:  # 内核/签发异常（工作线程原样回抛）
                    code = "error"
                    error_msg = f"hook [{hook}] 执行异常: {exc}"
            if not completed:
                code = "timeout"
                error_msg = (
                    f"hook [{hook}] 超时（抢占式）: 超过 "
                    f"{max(eff_timeout_ms or 0, 0):.0f}ms 预算未完成，"
                    f"钩子线程已遗弃（daemon），其产出不再被消费"
                )
            elapsed_ms = (time.monotonic() - t0) * 1000
            hook_elapsed[hook] = round(elapsed_ms, 3)

            if code == "success" and hook_timeout_ms is not None and elapsed_ms > hook_timeout_ms:
                # 兜底复检：正常已被抢占拦截，仅计时抖动时兜底，语义同前
                code = "timeout"
                error_msg = f"hook [{hook}] 超时: {elapsed_ms:.3f}ms > {hook_timeout_ms}ms"

            # ── 钩子判定审计落库（旁路，异常不阻断裁决） ──
            if code == "success":
                _emit_hook_audit(hook, trace_id, "pass",
                                 elapsed_ms=hook_elapsed[hook])
            else:
                if hook == "artifact_validate" and validate_result is not None:
                    hits = list(validate_result.get("failures") or [])
                elif hook == "gate_guard" and gate_result is not None:
                    hits = [{"message": gate_result.get("reason", "")}]
                else:
                    hits = []
                _emit_hook_audit(hook, trace_id, code, rule_hits=hits,
                                 reason=error_msg, elapsed_ms=hook_elapsed[hook])

            if code != "success":
                break

    # ── P1-1 状态脏写修复：非 success 出参不得携带目标态 ──
    if code != "success":
        new_task_state = None

    # ── 失败策略（阻断 ≠ 直接死掉） ──
    failure_info = (
        _apply_failure_policy(payload.get("failure_policy"), error_msg,
                              executed_retry=executed_retry)
        if code != "success" else None
    )

    # ── 任务生命周期动作（task_complete / task_cancel / task_archive） ──
    if code == "success" and payload.get("task"):
        task_result = _task.run_task_action(
            payload["task"], trace_id,
            artifact=artifact, signed_artifact=signed_artifact,
        )
        if task_result.get("code") != "success":
            code = task_result.get("code", "error")
            error_msg = task_result.get("reason", "task action failed")

    # ── 投递装配 ──
    delivery_out = (
        _apply_delivery(payload["delivery"], signed_artifact if signed_artifact is not None else artifact, code)
        if payload.get("delivery") else None
    )

    # ── failure_policy 实执行：fallback_target 改写投递目标（兜底分流） ──
    if (
        code in ("block", "reject")
        and delivery_out is not None
        and (payload.get("failure_policy") or {}).get("fallback_target")
    ):
        delivery_out["next_handler"] = payload["failure_policy"]["fallback_target"]

    out: dict[str, Any] = {
        "code": code,
        "trace_id": trace_id,
        "parent_trace_id": payload.get("parent_trace_id"),
        "new_task_state": new_task_state,
        "signed_artifact": signed_artifact,
        "gate_result": gate_result,
        "validate_result": (
            {"pass": validate_result["pass"], "results": validate_result["results"],
             "failures": validate_result["failures"]}
            if validate_result is not None else None
        ),
        "resource": resource_out,
        "issue_meta": issue_meta,
        "delivery": delivery_out,
        "failure_info": failure_info,
        "audit_meta": payload.get("audit_meta"),
        "task_result": task_result,
    }
    if payload.get("debug"):
        out["_debug"] = {
            "hook_elapsed_ms": hook_elapsed,
            "payload_snapshot": _mask_snapshot(payload),
        }
    return validate_output(out)
