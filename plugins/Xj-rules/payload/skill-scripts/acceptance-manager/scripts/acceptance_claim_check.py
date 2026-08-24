#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
acceptance_claim_check.py — 验收结论 claim 勾稽校验器（GENERALIZE-GATE 泛化克隆 · 路B acceptance_verdict）

骨架真源：sv-supervisor/scripts/post_gate_audit_check.py 的 check_claims（2026-08-16 冻结版）。
克隆纪律：枚举四件套与勾稽规则原样复制，禁止增删 claim_type、禁止加新原语。

规则（验收结论文档/JSON 若带 claim 字段即强校验，不带不罚）：
  - claim 挂载点（字段名映射）：acceptance_report.details[].claim
    （对应骨架 findings[].claim；顶层无 acceptance_report 包装时取顶层对象本身）
  - claim_type 四枚举：coverage_verdict / severity_rating /
    evidence_sufficiency / boundary_omission，未知类型即违例
  - coverage_verdict：actual/threshold 数值 + direction(gte|lte) + verdict(pass|fail)，
    verdict 必须与数值比较一致；
    【本路唯一适配点】骨架的"锚点行数值追溯"改为对 test-master-report.json 的
    数值勾稽——claim.report_field（点路径，如 summary.passed / coverage.final.tiers.P0.line_pct）
    声明 actual 取自报告哪个字段，机械勾稽 actual 必须与报告该字段真实数值一致；
  - severity_rating：severity ∈ critical|high|medium|low + rationale ≥10 字 +
    与 detail.severity（若存在，字段名映射自 finding.severity）自洽；
  - evidence_sufficiency：required_refs 正整数，勾稽 detail.evidence_refs
    （字段名映射自 finding.evidence_refs，缺省计 0）条数 ≥ 声明数；
  - boundary_omission：detail.result（若存在，字段名映射自 finding.verdict）
    必须为 FAIL（报遗漏即不得判通过）。
解读合理性本体（数值之外的分析是否到位）仍留软层，禁止开关化。

用法：
  python3 acceptance_claim_check.py --project <项目根路径>
  python3 acceptance_claim_check.py --verdict <验收结论JSON路径> --report <test-master-report.json路径>

  路径候选集（2026-08-17 修复三方路径错位，FIX-acceptance）：
  显式路径（--verdict/--report）存在即优先采用；否则按 --project 在候选集内
  按优先级探测，首个命中即采用：
    verdict 候选集（SKILL.md:242 标准布局 → 根目录兼容位）：
      1. deliverables/STEP-13_验收/acceptance_report.json
      2. acceptance_report.json
    report 候选集（归档标准布局 → test-executor 产出位【test-executor/SKILL.md:405】
    → 根目录兼容位）：
      1. deliverables/STEP-10_全量测试/test-master-report.json
      2. evidence/test-master-report.json
      3. test-master-report.json

  【fail-closed】verdict 全候选缺失即判 B（违例明细列出全部已尝试路径），
  禁止"文件不存在=无 claim 可校=判 A"的静默跳过（原 :177-181 fail-open 缺陷）。
  report 全候选缺失判 CLARIFY（勾稽数据源不足，exit≠0 同样阻断，非放行）。

输出：单行 JSON {"pass": bool, "violations": [{"gate", "detail"}, ...],
                 "verdict_path": str|null, "report_path": str|null}
退出码：0=全过（A）/ 1=有违例（B）/ 3=输入信号不足（CLARIFY）。
"""
import argparse
import json
import os
import sys

EXIT_A, EXIT_B, EXIT_CLARIFY = 0, 1, 3

CLAIM_TYPES = ("coverage_verdict", "severity_rating", "evidence_sufficiency", "boundary_omission")
SEVERITIES = ("critical", "high", "medium", "low")

# 路径候选集（按优先级；2026-08-17 FIX-acceptance 统一三方路径约定）
VERDICT_CANDIDATES = (
    "deliverables/STEP-13_验收/acceptance_report.json",  # SKILL.md:242 标准布局
    "acceptance_report.json",                            # 根目录兼容位
)
REPORT_CANDIDATES = (
    "deliverables/STEP-10_全量测试/test-master-report.json",  # 归档标准布局（SKILL.md:253 示例）
    "evidence/test-master-report.json",                       # test-executor 产出位（其 SKILL.md:405）
    "test-master-report.json",                                # 根目录兼容位
)

_MISS = object()


def resolve_path(explicit, project, candidates):
    """显式路径存在即优先；否则在 project 下按候选集优先级探测。
    返回 (命中路径或 None, 已尝试路径列表)。"""
    tried = []
    if explicit:
        tried.append(explicit)
        if os.path.isfile(explicit):
            return explicit, tried
    if project:
        for rel in candidates:
            p = os.path.join(project, rel)
            tried.append(p)
            if os.path.isfile(p):
                return p, tried
    return None, tried


def dig(obj, dotted):
    """按 a.b.c 点路径取值（兼容数组下标），缺失返回 _MISS。"""
    cur = obj
    for part in str(dotted).split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return _MISS
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISS
    return cur


def check_claims(verdict_doc, report):
    """勾稽闸：details[].claim 可选，出现即强校验（枚举与规则同冻结骨架）。"""
    violations = []
    body = verdict_doc.get("acceptance_report") if isinstance(verdict_doc.get("acceptance_report"), dict) else verdict_doc
    details = body.get("details")
    if not isinstance(details, list):
        return violations  # 无 details 即无 claim 挂载点，不带不罚
    for i, d in enumerate(details):
        if not isinstance(d, dict):
            continue
        claim = d.get("claim")
        if claim is None:
            continue  # 可选字段，不带不罚
        did = d.get("check_item", "<details[%d]>" % i)
        if not isinstance(claim, dict):
            violations.append({"gate": "勾稽闸", "detail": "%s claim 不是对象" % did})
            continue
        ct = claim.get("claim_type")
        if ct not in CLAIM_TYPES:
            violations.append({"gate": "勾稽闸",
                               "detail": "%s claim.claim_type 非法: %r（枚举: %s）"
                                         % (did, ct, "/".join(CLAIM_TYPES))})
            continue
        tag = "%s claim[%s]" % (did, ct)
        if ct == "coverage_verdict":
            actual, threshold = claim.get("actual"), claim.get("threshold")
            direction, verdict = claim.get("direction"), claim.get("verdict")
            nums_ok = True
            for k, v in (("actual", actual), ("threshold", threshold)):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    violations.append({"gate": "勾稽闸", "detail": "%s.%s 非数值: %r" % (tag, k, v)})
                    nums_ok = False
            if direction not in ("gte", "lte"):
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.direction 必须为 gte/lte: %r" % (tag, direction)})
            if verdict not in ("pass", "fail"):
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.verdict 必须为 pass/fail: %r" % (tag, verdict)})
            if nums_ok and direction in ("gte", "lte") and verdict in ("pass", "fail"):
                ok = actual >= threshold if direction == "gte" else actual <= threshold
                if (verdict == "pass") != ok:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 数值勾稽矛盾: actual=%s threshold=%s(%s) 却判 %s"
                                                 % (tag, actual, threshold, direction, verdict)})
            # 适配点：锚点行数值追溯 → 对 test-master-report.json 的数值勾稽
            field = claim.get("report_field")
            if not isinstance(field, str) or not field.strip():
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.report_field 缺失（须声明 actual 取自 test-master-report.json 的点路径字段）" % tag})
            elif nums_ok:
                rv = dig(report, field.strip())
                if rv is _MISS:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 声明数值 %s 不可勾稽: test-master-report.json 无字段 %s"
                                                 % (tag, actual, field)})
                elif not isinstance(rv, (int, float)) or isinstance(rv, bool) or rv != actual:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 声明数值 %s 与 test-master-report.json 字段 %s 实际值 %r 不一致（数值不可追溯）"
                                                 % (tag, actual, field, rv)})
        elif ct == "severity_rating":
            sev = claim.get("severity")
            if sev not in SEVERITIES:
                violations.append({"gate": "勾稽闸", "detail": "%s.severity 非法: %r" % (tag, sev)})
            rat = claim.get("rationale")
            if not isinstance(rat, str) or len(rat.strip()) < 10:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.rationale 缺失或去空白后 <10 字（定级必须给依据）" % tag})
            dsev = d.get("severity")
            if sev in SEVERITIES and dsev is not None and dsev != sev:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s 自洽矛盾: detail.severity=%s 与 claim.severity=%s 不一致"
                                             % (tag, dsev, sev)})
        elif ct == "evidence_sufficiency":
            req = claim.get("required_refs")
            if not isinstance(req, int) or isinstance(req, bool) or req < 1:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.required_refs 非正整数: %r" % (tag, req)})
            else:
                refs = d.get("evidence_refs")
                n = len(refs) if isinstance(refs, list) else 0
                if n < req:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 勾稽矛盾: 声明需 %d 条证据，实际锚点仅 %d 条"
                                                 % (tag, req, n)})
        elif ct == "boundary_omission":
            dv = d.get("result")
            if dv is not None and str(dv).strip().lower() != "fail":
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s 勾稽矛盾: 报告边界遗漏却判 result=%s（遗漏即不得判通过）"
                                             % (tag, dv)})
    return violations


def main():
    ap = argparse.ArgumentParser(description="验收结论 claim 勾稽校验器（四枚举原样克隆 · 数值勾稽 test-master-report.json · fail-closed 路径候选集）")
    ap.add_argument("--verdict", help="验收结论 JSON 显式路径（存在即优先；缺失则回退 --project 候选集）")
    ap.add_argument("--report", help="test-master-report.json 显式路径（存在即优先；缺失则回退 --project 候选集）")
    ap.add_argument("--project", help="项目根路径（按候选集探测 verdict/report 标准布局）")
    args = ap.parse_args()

    if not args.project and not (args.verdict and args.report):
        print(json.dumps({"pass": False,
                          "error": "输入不足：须给 --project，或同时给 --verdict 与 --report 显式路径"},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    report_path, report_tried = resolve_path(args.report, args.project, REPORT_CANDIDATES)
    if report_path is None:
        print(json.dumps({"pass": False,
                          "error": "report 全候选缺失（勾稽数据源不足）",
                          "tried": report_tried}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    try:
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"pass": False, "error": "report JSON 读取/解析失败: %s" % e,
                          "report_path": report_path}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    if not isinstance(report, dict):
        print(json.dumps({"pass": False, "error": "report 顶层必须为对象",
                          "report_path": report_path}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    verdict_path, verdict_tried = resolve_path(args.verdict, args.project, VERDICT_CANDIDATES)
    if verdict_path is None:
        # fail-closed（2026-08-17 FIX-acceptance）：验收结论缺失即判 B，
        # 禁止 fail-open 静默跳过（原缺陷：文件不存在直接判 A，勾稽闸形同虚设）
        violations = [{"gate": "勾稽闸",
                       "detail": "验收结论 acceptance_report.json 全候选缺失（fail-closed：缺失即判 B），"
                                 "已尝试: %s" % " | ".join(verdict_tried)}]
        print(json.dumps({"pass": False, "violations": violations,
                          "verdict_path": None, "report_path": report_path}, ensure_ascii=False))
        sys.exit(EXIT_B)
    try:
        with open(verdict_path, encoding="utf-8") as f:
            verdict_doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"pass": False, "error": "verdict JSON 读取/解析失败: %s" % e,
                          "verdict_path": verdict_path}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    if not isinstance(verdict_doc, dict):
        print(json.dumps({"pass": False, "error": "verdict 顶层必须为对象",
                          "verdict_path": verdict_path}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    violations = check_claims(verdict_doc, report)
    # 单行输出：gate_switch script_exit 取 tail[-1] 作违例详情
    print(json.dumps({"pass": not violations, "violations": violations,
                      "verdict_path": verdict_path, "report_path": report_path}, ensure_ascii=False))
    sys.exit(EXIT_A if not violations else EXIT_B)


if __name__ == "__main__":
    main()
