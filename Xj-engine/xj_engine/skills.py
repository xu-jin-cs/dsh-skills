"""
[DEPRECATED] backend/engine/skills.py — 向后兼容过渡 shim（2026-08-17 FIX-engine-ops ③）。

真身已外迁至 backend/services/test_skills.py——该模块含私有业务硬编码
（14 态状态机 / 中文校验文案 / 测试分片规则），按"engine 层零业务常量、
私有规则禁止下沉引擎"裁定迁出 engine 层。

本 shim 仅为不打破存量 import（from backend.engine.skills import ...）保留，
import 时触发 DeprecationWarning；新代码请直接：
    from backend.services.test_skills import ...
本 shim 计划在确认无存量引用后删除。
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "backend.engine.skills 已废弃（deprecated），真身迁至 "
    "backend.services.test_skills；请更新 import，shim 将在确认无引用后删除",
    DeprecationWarning,
    stacklevel=2,
)

# 显式 re-export 全量公开接口（保持 from ... import X 逐名可用）
from backend.services.test_skills import (  # noqa: E402,F401
    execute_all_test_skills,
    skill_defect_classification,
    skill_interface_contract,
    skill_smoke_business_logic,
    skill_test_gap_analysis,
    skill_ui_interaction_boundary,
    skill_whitebox_code_scan,
)

__all__ = [
    "execute_all_test_skills",
    "skill_defect_classification",
    "skill_interface_contract",
    "skill_smoke_business_logic",
    "skill_test_gap_analysis",
    "skill_ui_interaction_boundary",
    "skill_whitebox_code_scan",
]
