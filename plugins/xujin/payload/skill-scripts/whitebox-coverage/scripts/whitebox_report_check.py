#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whitebox_report_check.py — 白盒 Markdown 报告核心数字 ↔ JSON 证据一致性机械校验
（gate-switch spec: whitebox_report_consistency.json 的 script_exit 被包装脚本，2026-08-16 D 域批量开关化）

对齐 whitebox-coverage/SKILL.md「终判与报告」L108：
  数据来源全部数字取自 test-master-report.json 与 evidence/tdd/coverage.json，禁止凭记忆填数。

比对口径（核心四数）：
  用例总数   MD「(测试)用例总数|总用例(数)」   ↔ master.summary.total
  通过率     MD「通过率|pass_rate」%           ↔ master.summary.pass_rate（缺省则 passed/total 现算）
  缺陷数     MD「(发现)?(Bug|缺陷)总数」        ↔ len(master.defects)
  覆盖率     MD「总行覆盖(率)?|行覆盖率」等      ↔ coverage.totals.line_pct / branch_pct
             （coverage 来源：--coverage 显式 > {project}/evidence/tdd/coverage.json >
              master.coverage.final.totals；三处皆无则覆盖率项 SKIP 并输出说明）

判定：某指标 JSON 侧有值而 MD 未写出 → 违例（报告缺核心数字，六段结构不完整）；
     MD 有值而 JSON 无 → 违例（凭记忆填数嫌疑）；两侧都有 → 计数必须相等，百分比容差 --tolerance。
退出码：0=全过 / 2=有违例 / 3=输入不足。纯 stdlib。

用法：
  whitebox_report_check.py --project <项目根>            # 标准布局自动定位
  whitebox_report_check.py --report <md> --master <json> [--coverage <json>]
"""
import argparse
import glob
import json
import os
import re
import sys

TOL_DEFAULT = 0.5  # 百分比容差（百分点）


def _num_after(text, labels, unit_allow=r"[%％]?"):
    """在文本中找 标签 后的第一个数字（允许表格管道/空白/冒号间隔）。"""
    for lab in labels:
        m = re.search(lab + r"[^\d\-]{0,40}(-?\d+(?:\.\d+)?)\s*" + unit_allow, text)
        if m:
            return float(m.group(1))
    return None


def _dig(obj, *paths):
    for p in paths:
        cur = obj
        ok = True
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and isinstance(cur, (int, float)) and not isinstance(cur, bool):
            return float(cur)
    return None


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="白盒报告核心数字 ↔ JSON 证据一致性校验")
    ap.add_argument("--project", help="项目根（标准布局自动定位 report/master/coverage）")
    ap.add_argument("--report", help="Markdown 报告路径（覆盖 --project 定位）")
    ap.add_argument("--master", help="test-master-report.json 路径")
    ap.add_argument("--coverage", help="evidence/tdd/coverage.json 路径")
    ap.add_argument("--tolerance", type=float, default=TOL_DEFAULT)
    args = ap.parse_args()

    report = args.report
    master = args.master
    coverage = args.coverage
    if args.project:
        p = args.project
        if not report:
            cands = sorted(glob.glob(os.path.join(p, "*白盒测试报告*.md")),
                           key=os.path.getmtime, reverse=True)
            report = cands[0] if cands else None
        master = master or os.path.join(p, "test-master-report.json")
        coverage = coverage or os.path.join(p, "evidence", "tdd", "coverage.json")

    missing = [n for n, v in (("report", report), ("master", master))
               if not v or not os.path.isfile(v)]
    if missing:
        print(f"[whitebox_report] CLARIFY: 输入缺失 {missing}"
              f"（report={report} master={master}）", file=sys.stderr)
        sys.exit(3)

    try:
        md = open(report, encoding="utf-8").read()
        mst = load_json(master)
    except Exception as e:
        print(f"[whitebox_report] CLARIFY: 解析失败 {e}", file=sys.stderr)
        sys.exit(3)

    # JSON 侧取数
    summary = mst.get("summary") or {}
    j_total = _dig(summary, "total")
    j_pass = _dig(summary, "pass_rate")
    if j_pass is None:
        t, pd = _dig(summary, "total"), _dig(summary, "passed")
        if t and pd is not None and t > 0:
            j_pass = round(pd / t * 100, 1)
    j_defects = mst.get("defects")
    j_defects = float(len(j_defects)) if isinstance(j_defects, list) else None

    cov_src = None
    cov = None
    if coverage and os.path.isfile(coverage):
        cov_src, cov = coverage, load_json(coverage)
    elif isinstance(mst.get("coverage"), dict):
        cov_src, cov = "master.coverage", mst["coverage"]
    j_line = j_branch = None
    if cov:
        j_line = _dig(cov, "totals.line_pct", "final.totals.line_pct")
        j_branch = _dig(cov, "totals.branch_pct", "final.totals.branch_pct")

    # MD 侧取数
    md_total = _num_after(md, [r"(?:测试)?用例总数", r"总用例(?:数)?"])
    md_pass = _num_after(md, [r"通过率", r"pass[_ ]?rate"])
    md_defects = _num_after(md, [r"(?:发现\s*)?(?:Bug|缺陷)\s*总数", r"缺陷数"])
    md_line = _num_after(md, [r"总行覆盖(?:率)?", r"行覆盖率"])
    md_branch = _num_after(md, [r"总分支覆盖(?:率)?", r"分支覆盖率"])

    violations, compared, notes = [], 0, []

    def check(name, md_v, j_v, is_pct):
        nonlocal compared
        if j_v is None and md_v is None:
            notes.append(f"{name}: 双侧皆无，SKIP")
            return
        if j_v is None:
            violations.append(f"{name}: MD={md_v} 但 JSON 无此字段（凭记忆填数嫌疑）")
            return
        if md_v is None:
            violations.append(f"{name}: JSON={j_v} 但报告未写出（核心数字缺失）")
            return
        compared += 1
        if is_pct:
            if abs(md_v - j_v) > args.tolerance:
                violations.append(f"{name}: MD={md_v}% vs JSON={j_v}% 超容差 {args.tolerance}")
        else:
            if int(md_v) != int(j_v):
                violations.append(f"{name}: MD={int(md_v)} vs JSON={int(j_v)} 不一致")

    check("用例总数", md_total, j_total, False)
    check("通过率", md_pass, j_pass, True)
    check("缺陷数", md_defects, j_defects, False)
    if j_line is None and j_branch is None:
        notes.append("覆盖率: 无 coverage 来源（evidence/tdd/coverage.json 与 master.coverage 皆缺），SKIP")
    else:
        check("行覆盖率", md_line, j_line, True)
        check("分支覆盖率", md_branch, j_branch, True)

    print(f"[whitebox_report] report={os.path.basename(report)} master={os.path.basename(master)}"
          f" cov_src={cov_src} 比对指标={compared}")
    for n in notes:
        print(f"[whitebox_report] NOTE {n}")
    if violations:
        for v in violations:
            print(f"[whitebox_report] VIOLATION {v}")
        print(f"[whitebox_report] FAIL 违例 {len(violations)} 项")
        sys.exit(2)
    if compared == 0:
        print("[whitebox_report] CLARIFY: 无可比对指标", file=sys.stderr)
        sys.exit(3)
    print("[whitebox_report] PASS 报告核心数字与 JSON 证据一致")
    sys.exit(0)


if __name__ == "__main__":
    main()
