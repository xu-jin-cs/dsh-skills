#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""attached_plan.py — 计划闸/收益闸附身钩子族（attached_plan_hook，2026-08-22 块Q v3
用户终裁，REFORM-GATE 判A，块文件 ~/.agents/logs/reform_blocks/plan_gate_weld_20260822.md）。

v3 挂点终裁（覆盖 v1/v2）：
  ① 计划闸附身挂点 = todo_write 节点（插件通道⑤侧调用，清单含新任务才触发、重发豁免）
     ——不挂 problem_gate spec（v2 挂法已撤），本脚本仅作插件侧调用载体；
  ② 强制连锁 = plan_select.py chosen 输出后附身 [ATTACHED-REFORM] 义务块（--mode reform）；
  ③ 用户直给方案 → 单过收益闸，不触发本链（两条声明块均不注入）。

声明块：
  --mode plan（默认，插件 todo_write 附身用）：
    [ATTACHED-PLAN] 任务清单含新任务=方案形成中，须过计划闸：先生成 3 维度槽位候选池
    落盘 ~/.agents/logs/plan_select/POOL-<ts>.md 并扳 plan_select.py；
    单路径无选择须显式声明豁免理由。
  --mode reform（plan_select chosen 后强制连锁用）：
    [ATTACHED-REFORM] chosen 方案须填 reform 块过 reform_gate.json 判A后才执行；
    用户直给方案单过收益闸路径不触发本链。

附身执行非判定：恒 exit 0 不炸宿主；留痕 ~/.agents/logs/attached_plan.jsonl
（ts/hook/mode/host/desc）。
"""
import argparse
import datetime
import json
import os
import sys

ATTACHED_LOG = os.path.expanduser("~/.agents/logs/attached_plan.jsonl")
POOL_DIR = "~/.agents/logs/plan_select"

DECLARATIONS = {
    "plan": (
        "[ATTACHED-PLAN] 任务清单含新任务=方案形成中，须过计划闸：先生成 3 维度槽位候选池落盘 "
        f"{POOL_DIR}/POOL-<ts>.md 并扳 "
        "python3 ~/.agents/skills/plan-select/scripts/plan_select.py --pool <池文件>；"
        "单路径无选择须显式声明豁免理由"
        "（2026-08-22 块Q v3：挂点=todo_write 插件附身，清单含新任务才触发、重发豁免）"
    ),
    "reform": (
        "[ATTACHED-REFORM] chosen 方案须填 reform 块过 "
        "python3 ~/.agents/skills/reform_gate/scripts/gate_switch.py --spec "
        "~/.agents/skills/reform_gate/scripts/specs/reform_gate.json --set block=<块文件> 判A后才执行；"
        "用户直给方案单过收益闸路径不触发本链"
        "（2026-08-22 块Q v3 强制连锁：有计划闸必跟收益闸）"
    ),
}


def main():
    ap = argparse.ArgumentParser(description="计划闸/收益闸附身钩子（附身执行非判定，恒 exit 0）")
    ap.add_argument("--mode", choices=["plan", "reform"], default="plan",
                    help="plan=todo_write 插件附身声明；reform=plan_select chosen 后强制连锁")
    ap.add_argument("--host", default="plugin_todo_write", help="调用方标识（plugin_todo_write/plan_select/manual）")
    ap.add_argument("--block", default=None, help="关联块文件路径（留痕用）")
    ap.add_argument("--desc", default=None, help="任务/方案摘要（留痕用）")
    args = ap.parse_args()

    out = {
        "attached": True,
        "hook": "attached_plan_hook",
        "mode": args.mode,
        "host": args.host,
        "block": args.block,
        "desc": args.desc,
        "declaration": DECLARATIONS[args.mode],
        "note": "附身执行非判定：声明块机械注入，择优/收益判定权在 plan_select.py / reform_gate.json；"
                "豁免路径=用户直给方案单过收益闸（不触发本链）或显式声明单路径豁免理由（复盘期后查）",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    try:
        os.makedirs(os.path.dirname(ATTACHED_LOG), exist_ok=True)
        with open(ATTACHED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "hook": "attached_plan_hook", "mode": args.mode, "host": args.host,
                "block": args.block, "desc": args.desc,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0  # 恒 exit 0：附身执行非判定


if __name__ == "__main__":
    sys.exit(main())
