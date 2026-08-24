"""Xj-engine standalone 版 skills shim。

原 skills shim 依赖外部测试技能服务私有业务模块。
独立版不包含该业务实现；需要测试技能服务的接入方请自行实现对应接口。
"""

from __future__ import annotations

__all__ = [
    "execute_all_test_skills",
    "skill_defect_classification",
    "skill_interface_contract",
    "skill_smoke_business_logic",
    "skill_test_gap_analysis",
    "skill_ui_interaction_boundary",
    "skill_whitebox_code_scan",
]


def _unavailable(*_args, **_kwargs):
    raise ImportError(
        "Xj-engine standalone 不包含外部测试技能服务业务模块；"
        "请接入自己的测试技能服务后替换本 stub。"
    )


execute_all_test_skills = _unavailable
skill_defect_classification = _unavailable
skill_interface_contract = _unavailable
skill_smoke_business_logic = _unavailable
skill_test_gap_analysis = _unavailable
skill_ui_interaction_boundary = _unavailable
skill_whitebox_code_scan = _unavailable
