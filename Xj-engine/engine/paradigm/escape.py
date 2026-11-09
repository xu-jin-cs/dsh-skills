"""事后逃逸检测：已放行的模板在下游执行时出现范式不匹配。

三条规则（规格 2 条 + 1 条兜底）：
  E1 轻范式（单轮 / ReAct）出现反思回路 → 逃逸
  E2 单轮被拆成多 Agent（distinctAgentId > 1）→ 逃逸
  E3 声明 Reflexion 但运行时没有循环（maxIterations 缺失/<=0）→ 逃逸

本模块只判定并留痕；"暂停当前 Agent / 推送指导大师"由平台侧执行（见 actions）。
"""
from __future__ import annotations

LIGHT = {"single_tool_call", "react"}


def detect(declared: str, facts: dict) -> dict:
    """facts 可含：maxIterations、distinctAgentId、nodes、loopPurpose。"""
    alerts: list[dict] = []
    it = facts.get("maxIterations")
    purpose = facts.get("loopPurpose")
    agents = facts.get("distinctAgentId", 1)

    if declared in LIGHT and (purpose == "reflection" or (isinstance(it, int) and it > 0 and purpose != "tool_iteration")):
        alerts.append({"code": "ESCAPE_LIGHT_WITH_REFLECTION",
                       "message": f"声明 {declared}（轻范式）但运行时出现反思回路"
                                  f"（maxIterations={it}, purpose={purpose}）"})
    if declared == "single_tool_call" and isinstance(agents, int) and agents > 1:
        alerts.append({"code": "ESCAPE_SINGLE_SPLIT_MULTI",
                       "message": f"声明单轮工具调用但运行时拆成 {agents} 个 Agent"})
    if declared == "reflexion" and (not isinstance(it, int) or it <= 0):
        alerts.append({"code": "ESCAPE_REFLEXION_UNBOUNDED",
                       "message": f"声明 Reflexion 但运行时无有效循环上界（maxIterations={it}）"})

    return {"assetKey": facts.get("assetKey", ""), "declaredParadigm": declared,
            "escaped": bool(alerts), "alerts": alerts,
            "actions": (["pause_agent", "push_to_guide_master", "feedback_to_matcher"]
                        if alerts else [])}
