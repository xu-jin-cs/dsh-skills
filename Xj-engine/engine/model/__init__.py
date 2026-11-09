"""模型底座：分层路由状态机（决策纯函数，不调用任何模型）。"""
from .router import (  # noqa: F401
    COMPLEXITY_RANK,
    STATES,
    TRIGGERS,
    decide_route,
    on_failure,
    on_verify,
    simulate,
)

__all__ = ["COMPLEXITY_RANK", "STATES", "TRIGGERS", "decide_route", "on_failure",
           "on_verify", "simulate"]
