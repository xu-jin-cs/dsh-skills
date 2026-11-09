"""模型底座 · 分层路由状态机（纯函数，无网络调用）。

2026-11-09 用户裁定：把「三模型各司其职」落成标准状态机执行路径——
工具路由小模型 → 简单判断低成本直出 / 复杂上抛 → 主推理模型 → 校验模型独立裁判
→ 通过放行 / 结构化打回定位重试；超时·报错·配额耗尽 → 沿降级链自动切换。

边界声明（必须如实）：
  - 本模块只做**决策**（选哪个档、下一步是什么），不调用任何模型、不读网络。
  - 真实模型调用仍由既有组件承担（平台侧 `LLMClient.model_for(tier)` 的 fast/primary 档、
    既有超时配置）；宿主执行器的接线属后续改造，本模块不假装已接入。
  - 依赖的声明来自资产 `observe.modelPolicy`；校验在
    `engine.observe.contract_loader._validate_model_policy`，本模块只消费已校验的声明。

状态：input → router → (direct | primary) → verify → (pass | rework→primary | blocked)
                 任何一步 failure(timeout/error/quota_exhausted) → degrade(下一模型) → … → exhausted
"""
from __future__ import annotations

COMPLEXITY_RANK = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}
TRIGGERS = ("timeout", "error", "quota_exhausted")
STATES = ("input", "router", "direct", "primary", "verify", "pass", "rework", "degrade", "blocked")


def _rank(complexity: str) -> int:
    if complexity not in COMPLEXITY_RANK:
        raise ValueError(f"非法复杂度 {complexity!r}（支持 {sorted(COMPLEXITY_RANK)}）")
    return COMPLEXITY_RANK[complexity]


def _boundary(policy: dict, tier: str) -> int:
    try:
        return _rank(policy["tiers"][tier]["maxComplexity"])
    except KeyError as e:
        raise ValueError(f"modelPolicy 缺 tiers.{tier}.maxComplexity") from e


def decide_route(*, policy: dict, complexity: str, tool_intent: bool,
                 confidence: float) -> dict:
    """路由小模型判定后：低成本直出，还是上抛主推理。

    - 复杂度超出 router 能力边界 → 强制上抛（弱模型不碰复杂规划）
    - 无工具意图 → 直出
    - 置信度低于 minConfidence → 上抛（宁可多花钱，不赌小模型）
    """
    rank = _rank(complexity)
    if rank > _boundary(policy, "router"):
        return {"state": "router", "target": "primary", "tier": "primary",
                "reason": f"复杂度 {complexity} 超 router 能力边界 "
                          f"{policy['tiers']['router']['maxComplexity']}，强制上抛"}
    if not tool_intent:
        return {"state": "router", "target": "direct", "tier": "router",
                "reason": "无工具意图，低成本直出"}
    min_conf = float(policy["tiers"]["router"].get("minConfidence", 0.6))
    if confidence < min_conf:
        return {"state": "router", "target": "primary", "tier": "primary",
                "reason": f"router 置信度 {confidence:.2f} < {min_conf}，上抛主推理"}
    return {"state": "router", "target": "direct", "tier": "router",
            "reason": "简单判断可直出"}


def on_verify(*, policy: dict, verdict: str, rework_count: int) -> dict:
    """校验模型（独立裁判）裁决后：放行 / 结构化打回 / 熔断。"""
    if verdict == "pass":
        return {"state": "pass", "action": "release", "reworkCount": rework_count}
    max_rework = int(policy["verify"]["maxRework"])
    if rework_count >= max_rework:
        return {"state": "blocked", "action": "blocked", "reworkCount": rework_count,
                "reason": f"已返工 {rework_count} 次达上限 {max_rework}，转人工"}
    return {"state": "rework", "action": "rework", "reworkCount": rework_count + 1,
            "feedbackFormat": policy["verify"]["feedback"],
            "reason": "校验未通过，按结构化缺陷清单回主推理重试"}


def on_failure(*, policy: dict, trigger: str, chain_index: int = 0) -> dict:
    """超时/报错/配额耗尽：沿降级链切到下一个模型；链尽按 onExhausted 收口。"""
    if trigger not in TRIGGERS:
        raise ValueError(f"非法降级触发 {trigger!r}（支持 {list(TRIGGERS)}）")
    chain = list(policy["degrade"]["chain"])
    if chain_index + 1 < len(chain):
        nxt = chain[chain_index + 1]
        return {"state": "degrade", "action": "degrade", "model": nxt,
                "chainIndex": chain_index + 1, "trigger": trigger,
                "reason": f"{trigger} 触发降级：{chain[chain_index]} → {nxt}"}
    return {"state": "degrade", "action": policy["degrade"]["onExhausted"], "model": None,
            "chainIndex": chain_index, "trigger": trigger,
            "reason": f"降级链已用尽（{trigger}），按 onExhausted="
                      f"{policy['degrade']['onExhausted']} 收口"}


def simulate(*, policy: dict, complexity: str, tool_intent: bool, confidence: float,
             verify_verdicts: list[str] | None = None,
             failures: list[str] | None = None) -> dict:
    """把一次调用走完整条路径（无 LLM），供单测与评审复算。

    verify_verdicts：每轮校验结论（"pass"/"fail"），默认 ["pass"]
    failures：主推理阶段依次遇到的失败触发（"timeout"/"error"/"quota_exhausted"）
    """
    steps: list[dict] = [{"state": "input", "complexity": complexity}]
    r = decide_route(policy=policy, complexity=complexity,
                     tool_intent=tool_intent, confidence=confidence)
    steps.append(r)
    if r["target"] == "direct":
        return {"steps": steps, "final": "direct", "model": policy["tiers"]["router"]["model"]}

    chain_index = 0
    steps.append({"state": "primary", "model": policy["degrade"]["chain"][0]})
    for trig in (failures or []):
        d = on_failure(policy=policy, trigger=trig, chain_index=chain_index)
        steps.append(d)
        if d["action"] == "degrade":
            chain_index = d["chainIndex"]
            steps.append({"state": "primary", "model": d["model"]})
            continue
        return {"steps": steps, "final": d["action"], "model": d["model"]}

    rework = 0
    # 注意：空列表 ≠ 未提供。[] 表示"没有拿到任何校验裁决"→ 不得默认放行；
    # 只有 None（未指定）才用默认单轮 pass。
    verdicts = ["pass"] if verify_verdicts is None else list(verify_verdicts)
    for verdict in verdicts:
        v = on_verify(policy=policy, verdict=verdict, rework_count=rework)
        steps.append(v)
        if v["action"] == "release":
            return {"steps": steps, "final": "pass",
                    "model": policy["degrade"]["chain"][chain_index]}
        if v["action"] == "blocked":
            return {"steps": steps, "final": "blocked",
                    "model": policy["degrade"]["chain"][chain_index]}
        rework = v["reworkCount"]
        steps.append({"state": "primary", "model": policy["degrade"]["chain"][chain_index],
                      "reason": "结构化打回重试"})
    # 兜底：未给出裁决视为未通过，不假装通过
    return {"steps": steps, "final": "blocked",
            "model": policy["degrade"]["chain"][chain_index],
            "reason": "缺少校验裁决，按未通过处理（禁止默认放行）"}
