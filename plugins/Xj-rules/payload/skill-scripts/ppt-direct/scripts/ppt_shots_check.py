#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_shots_check.py — ppt-direct 节点0 模板截图序号连续性核验（spec ppt_shots_seq.json 的 script_exit 后端）

SKILL.md 输入校验规则（L159）：page_*.png 数量 ≥3 且序号连续；不足或断档时记录缺失页码
并提示用户，禁止凭空编造页面。≥3 由 spec 的 glob_count 原语机考；本脚本负责序号连续性：
  - 提取 page_<N>.png 的 N（前导零归一），排序后必须等于 range(min, min+count)，断档即违例
  - 同一序号多种写法（page_1.png 与 page_01.png 并存）计命名冲突违例

用法：python3 ppt_shots_check.py --shots-dir <模板截图目录>
退出码：0 = 连续（A）；1 = 断档/冲突/数量不足（B，stdout JSON 的 violations 含缺失页码）；2 = 参数错误。
纯 stdlib。
"""
import argparse
import glob
import json
import os
import re
import sys

PAGE_RE = re.compile(r"^page_(\d+)\.png$", re.IGNORECASE)
MIN_SHOTS = 3


def main():
    ap = argparse.ArgumentParser(description="ppt-direct 模板截图序号连续性核验")
    ap.add_argument("--shots-dir", required=True, help="模板截图目录（page_*.png 所在）")
    args = ap.parse_args()

    shots_dir = os.path.abspath(os.path.expanduser(args.shots_dir))
    violations = []
    if not os.path.isdir(shots_dir):
        print(json.dumps({"ok": False, "violations": ["截图目录不存在: %s" % shots_dir]},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    nums = []
    for p in sorted(glob.glob(os.path.join(shots_dir, "page_*.png"))):
        m = PAGE_RE.match(os.path.basename(p))
        if m:
            nums.append(int(m.group(1)))
    if len(nums) != len(set(nums)):
        dup = sorted({n for n in nums if nums.count(n) > 1})
        violations.append("序号重复/命名不一致（同序号多种写法）：%s" % dup)
    uniq = sorted(set(nums))
    if len(uniq) < MIN_SHOTS:
        violations.append("page_*.png 仅 %d 张，不足 %d 张下限" % (len(uniq), MIN_SHOTS))
    if uniq:
        expected = list(range(uniq[0], uniq[0] + len(uniq)))
        missing = [n for n in expected if n not in uniq]
        if missing:
            violations.append(
                "序号断档，缺失页码：%s（实有 %d~%d，禁止凭空编造页面，须提示用户补齐）"
                % (missing, uniq[0], uniq[-1]))

    print(json.dumps({"gate": "ppt_shots_seq", "shots_dir": shots_dir,
                      "count": len(uniq), "sequence": uniq, "ok": not violations,
                      "violations": violations}, ensure_ascii=False, indent=2))
    # 末行单行结论：gate_switch script_exit 取 stdout 末行作为 B 档理由，必须自含
    print("VIOLATIONS: " + " | ".join(violations) if violations else "ALL_CHECKS_PASSED")
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
