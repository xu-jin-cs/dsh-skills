#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dispatch_probe.py — parallel-dispatch 机械探针（2026-08-16 量纲裁定配套）

输入任务信号（文件数 / 无依赖单元数 / 耦合标记 / 批量标记 / 任务描述），
输出双维决策矩阵的机械判定结果 JSON：
  scale（规模轴档位）/ mechanism（数量轴机制）/ fanout（建议扇出数）/
  topology（拓扑标记）/ reasons（判定依据）/ clarify（弱信号时的澄清提示）

量纲唯一化：任务量只按文件数量评估，本脚本不接受也不输出任何小时/工时估算。

用法：
  python3 dispatch_probe.py --files 5 --units 4
  python3 dispatch_probe.py --files 12 --units 12 --coupled --desc "重构用户中心12个模块"
  python3 dispatch_probe.py --units 20 --batch
  python3 dispatch_probe.py --desc "顺便把A、B都改一下"        # 信号不足 → clarify
"""
import argparse
import json
import sys

LIGHT_MAX_FILES = 3      # ≤3 文件 → 免评估轻分身
ENGINE_MIN_FILES = 10    # >10 文件且定档 M/L → 引擎级
GROUP_MAX_UNITS = 9      # 6~9 → 分组扇出；≥10 → workflow


def decide(files, units, coupled, batch, desc):
    reasons = []
    clarify = None

    # ---- 弱信号检测：文件数与单元数都未知 → 强制澄清 ----
    if files is None and units is None:
        clarify = (
            "信号不足，无法机械判定。请澄清：① 本次涉及几个文件？"
            "② 可拆出几个无依赖独立单元？③ 是否存在跨模块契约/状态耦合？"
        )
        return {
            "scale": None,
            "mechanism": None,
            "fanout": None,
            "topology": None,
            "reasons": ["files 与 units 均未提供"],
            "clarify": clarify,
        }

    f = files if files is not None else units
    n = units if units is not None else files

    # ---- 规模轴（纯文件数 + 耦合标记）----
    if coupled:
        if f is not None and f > ENGINE_MIN_FILES:
            scale = "engine"
            reasons.append(
                f"存在契约/状态耦合且文件数 {f} > {ENGINE_MIN_FILES} → "
                "需 task_breakdown 定档；定档 M/L 则走引擎级分身机制"
            )
        else:
            scale = "breakdown"
            reasons.append("存在契约/状态耦合 → 需评估：先 task_breakdown 定档（不论文件数）")
    elif f is not None and f <= LIGHT_MAX_FILES:
        scale = "light"
        reasons.append(f"文件数 {f} ≤ {LIGHT_MAX_FILES} 且无耦合 → 免评估轻分身")
    elif f is not None and f > ENGINE_MIN_FILES:
        scale = "engine"
        reasons.append(
            f"文件数 {f} > {ENGINE_MIN_FILES} → 需 task_breakdown 定档；"
            "定档 M/L 则走引擎级分身机制"
        )
    else:
        scale = "breakdown"
        reasons.append(f"文件数 {f} > {LIGHT_MAX_FILES} → 需评估：先 task_breakdown 定档")

    # ---- 数量轴（无依赖独立单元数）----
    if n is None or n <= 1:
        mechanism = "sequential"
        fanout = 0
        topology = "sequential"
        reasons.append("无依赖单元数 ≤1 → 无并行对象，串行执行")
    elif batch or n >= 10:
        mechanism = "workflow"
        fanout = n
        topology = "parallel"
        reasons.append(
            ("批量同类" if batch else f"单元数 {n} ≥ 10")
            + " → 必须 workflow 脚本编排，禁止逐个人肉 spawn"
        )
    elif n <= 5:
        mechanism = "subagent"
        fanout = n
        topology = "parallel"
        reasons.append(f"单元数 {n} ∈ 2~5 → subagent 同一消息内一次性扇出")
    else:  # 6~9
        mechanism = "subagent_grouped"
        fanout = n
        topology = "parallel"
        reasons.append(f"单元数 {n} ∈ 6~9 → subagent 按角色分组扇出（同层 ≤{GROUP_MAX_UNITS}）")

    # ---- 耦合修正拓扑 ----
    if coupled and topology == "parallel":
        topology = "mixed"
        reasons.append("存在耦合 → 依赖链部分串行、无依赖部分并行（混合拓扑）")

    # ---- 单文件特例 ----
    if f == 1 and fanout > 1:
        mechanism = "sequential"
        fanout = 0
        topology = "sequential"
        reasons.append(
            "单文件特例：文件内多修改点不拆分身（文件级写冲突），"
            "串行处理或同消息并行多个 Edit（规则26）"
        )

    # ---- PARALLEL-GATE 声明生成 ----
    gate = None
    if fanout >= 1:
        mech_text = {"subagent": f"subagent×{fanout}",
                     "subagent_grouped": f"subagent×{fanout}(分组)",
                     "workflow": "workflow"}.get(mechanism, mechanism)
        gate = (f"[PARALLEL-GATE] 子任务数:{n} | 无依赖:{fanout} | "
                f"判定:parallel | 机制:{mech_text}")
    elif n is not None and n >= 2:
        gate = (f"[PARALLEL-GATE] 子任务数:{n} | 无依赖:0 | "
                "判定:sequential | 机制:串行(请在此补依赖链理由，留空即违规)")

    return {
        "scale": scale,
        "mechanism": mechanism,
        "fanout": fanout,
        "topology": topology,
        "reasons": reasons,
        "gate_declaration": gate,
        "clarify": clarify,
    }


def main():
    ap = argparse.ArgumentParser(description="parallel-dispatch 机械探针（量纲=文件数）")
    ap.add_argument("--files", type=int, default=None, help="涉及文件数量")
    ap.add_argument("--units", type=int, default=None, help="无依赖独立单元数（缺省=文件数）")
    ap.add_argument("--coupled", action="store_true", help="存在跨模块契约/状态耦合")
    ap.add_argument("--batch", action="store_true", help="批量同类操作（强制 workflow）")
    ap.add_argument("--desc", type=str, default="", help="任务描述（仅留痕，不参与判定）")
    args = ap.parse_args()

    result = decide(args.files, args.units, args.coupled, args.batch, args.desc)
    if args.desc:
        result["desc"] = args.desc
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
