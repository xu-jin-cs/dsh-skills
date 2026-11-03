"""nodes 冻结层回归测试（2026-11-04 双法合流裁定 B 方案执行件）。

守护对象（见 engine/flow/nodes/nodes.py 头部冻结声明）：
  1. ALL_NODES 注册表金样本——图执行通道的"燃料清单"，逐键机械比对，
     防双副本漂移在引擎仓内静默发生；
  2. 宿主 2026-09-27 环1 三处修复的源级钉死（regen_flag / PMNode._calc_rate /
     deepcopy）——冻结前提是"已修 bug 不被冻成永久资产"；
  3. custom_agent HOST-ONLY 降级语义——无宿主环境 custom_agent_node=None 合法。
"""
from pathlib import Path

import pytest

from engine.flow.nodes import (
    ALL_NODES, NodeFn, custom_agent_node, custom_agent_subgraph,
)

NODES_SOURCE = Path(__file__).resolve().parents[1] / "engine" / "flow" / "nodes" / "nodes.py"

# 金样本（2026-11-04 实测全量 29 键）：冻结基线，增删键须显式改本清单并过评审
GOLDEN_KEYS = {
    "be", "code_review", "dpm", "executor", "fe", "gov_compress", "gov_infer",
    "gov_input", "gov_output", "gov_restore", "gov_snapshot", "ops",
    "parallel_aggregator", "parallel_dispatcher", "pause", "pm", "pm_confirm",
    "qa", "resume", "retro", "self_heal_flow", "self_heal_gate",
    "self_heal_output", "self_heal_root", "spm", "supervisor", "sv", "tcd",
    "ui_designer",
}


def test_all_nodes_golden_registry():
    """ALL_NODES 与金样本逐键全等：多键/少键/改名即失败。"""
    assert set(ALL_NODES.keys()) == GOLDEN_KEYS, (
        f"注册表漂移: 多={set(ALL_NODES.keys()) - GOLDEN_KEYS}, "
        f"少={GOLDEN_KEYS - set(ALL_NODES.keys())}"
    )


def test_all_nodes_values_callable():
    """每个注册项可调用或显式降级 None（HOST-ONLY 并行件无宿主降级=设计内语义，
    nodes.py:28 注释；坏项会让备用通道构图期失能）。"""
    for key, node in ALL_NODES.items():
        assert node is None or callable(node), (
            f"注册项 [{key}] 非法: {node!r}（既不可调用也非显式降级 None）"
        )


def test_custom_agent_host_only_degradation():
    """无宿主环境降级语义合法：None 或可调用，二者之一，禁止抛错穿透。"""
    assert custom_agent_node is None or callable(custom_agent_node)
    assert custom_agent_subgraph is None or callable(custom_agent_subgraph)


def test_ring1_fix_regen_flag_assigned():
    """环1修复①：regen_flag 必须先赋值后使用（赋值1 + 重试写标记3 + 清除2）。"""
    src = NODES_SOURCE.read_text(encoding="utf-8")
    assert src.count("regen_flag") >= 6, (
        "regen_flag 出现数异常——赋值或重试写标记回填被回退"
    )
    assert "regen_flag = os.path.join(temp_dir" in src, "regen_flag 赋值行缺失"


def test_ring1_fix_pm_calc_rate_no_self_ref():
    """环1修复②：staticmethod 内禁止 self._calc_rate（NameError 源，行级非注释检查）。"""
    src = NODES_SOURCE.read_text(encoding="utf-8")
    offenders = [
        line for line in src.splitlines()
        if "self._calc_rate" in line and not line.strip().startswith("#")
    ]
    assert not offenders, f"self._calc_rate 回退——smoke_test 分支必崩: {offenders}"


def test_ring1_fix_deepcopy_checklist():
    """环1修复③：CHECKLIST_TEMPLATE 必须深拷贝（防模块级共享模板跨任务串数据）。"""
    src = NODES_SOURCE.read_text(encoding="utf-8")
    assert "copy.deepcopy(CHECKLIST_TEMPLATE)" in src, "deepcopy 修复回退"
    assert "checklist = dict(CHECKLIST_TEMPLATE)" not in src, "浅拷贝残留"


def test_freeze_declaration_present():
    """冻结声明在场且管辖范围显式（双副本漂移的仓内留痕锚点）。"""
    src = NODES_SOURCE.read_text(encoding="utf-8")
    assert "FROZEN-2026-11-04" in src and "管辖范围" in src
    assert "单向自宿主回填" in src
