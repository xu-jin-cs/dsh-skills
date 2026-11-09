"""observe 控制机制 · **唯一决策实现（引擎侧）**。

用户 2026-11-08 裁定：「一种机制，不要散落各个位置；节点控制和状态同步统一用
workflow.json 或引擎，或混合」→ 本项目取**混合但边界单一**：

  声明 = 资产 `workflow.json` 的 `observe.control`（每种动作由谁执行）
  机制 = 本文件（能否控制 / 走哪条通道 / 什么模式）—— 唯一决策点
  适配 = backend 只做 HTTP + DB；宿主脚本只做"到节点边界叫一次"

禁止：在 backend / 客户端脚本里再写一份"能不能暂停/能不能重跑"的判断。
"""
from __future__ import annotations

from .progress import derive_progress  # noqa: F401  便于调用方一次 import 齐

PAUSE_CHANNELS = {"boundary-block", "sigstop"}
RERUN_CHANNELS = {"session-resume", "flow-run"}
LIVE_STATUSES = ("running", "paused", "waiting_input")


def pause_plan(control: dict | None, nodes: list[dict] | None, task_status: str) -> dict:
    """返回 {allowed, channel, reason}。**纯函数，无副作用**。"""
    ch = (control or {}).get("pause")
    if ch not in PAUSE_CHANNELS:
        # 区分「没声明」与「声明了不提供」——两者给出不同的下一步建议
        head = ("该资产未声明暂停通道（observe.control.pause 缺省）" if ch is None
                else f"该资产声明了不提供暂停（observe.control.pause={ch!r}）")
        return {"allowed": False, "channel": ch,
                "reason": f"{head}；支持 {sorted(PAUSE_CHANNELS)}"}
    if task_status not in LIVE_STATUSES:
        return {"allowed": False, "channel": ch, "reason": f"任务状态 {task_status}，不可暂停"}
    nodes = nodes or []
    if nodes and not any((n.get("capabilities") or {}).get("supportPause") is True for n in nodes):
        return {"allowed": False, "channel": ch,
                "reason": "该资产未声明任何可暂停节点（capabilities.supportPause=false）"}
    return {"allowed": True, "channel": ch, "reason": ""}


def rerun_plan(control: dict | None, nodes: list[dict] | None,
               target_node_id: str, task_status: str,
               session_id: str = "", launcher_ready: bool = True,
               consumer_dead: bool = False) -> dict:
    """返回 {allowed, channel, mode, reason}。

    mode：
      continue  —— 任务仍在跑/暂停中，向阻塞中的执行体下发"从该节点接回"
      resume    —— 任务已结束，对**绑定的 zcode 会话**续跑（channel=session-resume）
      flow-run  —— 已结束，交给引擎 flow 从目标节点重跑（channel=flow-run）
    """
    ch = (control or {}).get("rerun")
    if ch not in RERUN_CHANNELS:
        return {"allowed": False, "channel": ch, "mode": None,
                "reason": f"该资产未在 workflow.json 声明重跑通道"
                          f"（observe.control.rerun={ch!r}，支持 {sorted(RERUN_CHANNELS)}）"}
    nodes = nodes or []
    target = next((n for n in nodes if n.get("nodeId") == target_node_id), None)
    if nodes and target is None:
        return {"allowed": False, "channel": ch, "mode": None,
                "reason": f"节点不存在：{target_node_id}"}
    if target is not None and (target.get("capabilities") or {}).get("supportRerun") is not True:
        return {"allowed": False, "channel": ch, "mode": None,
                "reason": f"节点「{target.get('title') or target_node_id}」未声明可重跑"
                          f"（capabilities.supportRerun=false）"}
    # consumer_dead=True 表示暂停阻塞窗口已到点、宿主进程已退出：此时"继续"没有消费者，
    # 必须走会话续跑，否则目标节点会永久停在 waiting_input（2026-11-08 评审 P0）。
    if task_status in LIVE_STATUSES and not consumer_dead:
        return {"allowed": True, "channel": ch, "mode": "continue", "reason": ""}
    if ch == "session-resume":
        if not session_id:
            return {"allowed": False, "channel": ch, "mode": None,
                    "reason": "该任务没有绑定 zcode 会话 id，无法对应到指定会话；"
                              "请在 ZCode 里重新触发该技能（会重新绑定）"}
        return {"allowed": True, "channel": ch, "mode": "resume", "reason": ""}
    # flow-run
    if not launcher_ready:
        return {"allowed": False, "channel": ch, "mode": None,
                "reason": "引擎轨未就绪：未配置 SCI_RUNNER_CMD，无法拉起 flow"}
    return {"allowed": True, "channel": ch, "mode": "flow-run", "reason": ""}


RETRYABLE = {"timeout", "transient", "resource"}
NON_RETRYABLE = {"validation", "permission", "business"}


def retry_plan(node: dict, *, attempt: int, error_class: str,
               policy: dict | None = None) -> dict:
    """⑥ 重试决策（纯函数，唯一实现）：能不能重试、退避多久、由谁执行。

    引擎只出决策；真正重试由宿主按计划执行（2026-11-10 用户裁定）。
    """
    rp = policy or (node.get("retryPolicy") or {})
    caps = node.get("capabilities") or {}
    if not isinstance(rp, dict):
        rp = {}
    default_max = 1 if caps.get("supportRerun") is True else 0
    max_retries = rp.get("maxRetries", default_max)
    if not isinstance(max_retries, int) or max_retries < 0:
        max_retries = 0
    max_retries = min(max_retries, 5)                       # 全局硬顶
    retryable = set(rp.get("retryableErrors") or RETRYABLE)
    non = set(rp.get("nonRetryableErrors") or NON_RETRYABLE)
    if error_class in non or (retryable and error_class not in retryable and
                              error_class not in RETRYABLE):
        return {"allowed": False, "action": "escalate", "attempt": attempt,
                "reason": f"错误类别 {error_class!r} 不可重试（转人工/重跑）"}
    if error_class not in RETRYABLE and error_class not in retryable:
        return {"allowed": False, "action": "escalate", "attempt": attempt,
                "reason": f"未知错误类别 {error_class!r}，不自动重试"}
    if attempt > max_retries:
        return {"allowed": False, "action": "exhausted", "attempt": attempt,
                "maxRetries": max_retries,
                "reason": f"重试已用尽（attempt={attempt} > maxRetries={max_retries}）"}

    bo = rp.get("backoff") or {}
    btype = bo.get("type", "none")
    if btype == "fixed":
        delay = int(bo.get("baseMs", 500))
    elif btype == "exponential":
        base = int(bo.get("baseMs", 500))
        cap = int(bo.get("capMs", 30000))
        delay = min(base * (2 ** max(0, attempt - 1)), cap)
    else:
        delay = 0
    return {"allowed": True, "action": "retry", "attempt": attempt + 1,
            "delayMs": delay, "backoff": btype, "maxRetries": max_retries,
            "channel": "host", "reason": f"{error_class} 可重试（第 {attempt + 1} 次）"}


def asset_caps(control: dict | None, nodes: list[dict] | None) -> dict:
    """**UI 置灰用的能力布尔**（唯一派生）。

    前端只读 `pause` / `rerun` 两个布尔，不再自己比对枚举值
    （避免前端成为控制枚举的第二份副本）。
    """
    ctl = control or {}
    nodes = nodes or []
    return {
        "pause": (ctl.get("pause") in PAUSE_CHANNELS
                  and any((n.get("capabilities") or {}).get("supportPause") is True for n in nodes)),
        "rerun": (ctl.get("rerun") in RERUN_CHANNELS
                  and any((n.get("capabilities") or {}).get("supportRerun") is True for n in nodes)),
    }
