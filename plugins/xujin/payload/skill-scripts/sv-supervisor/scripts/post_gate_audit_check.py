#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
post_gate_audit_check.py — POST_GATE_AUDIT 复核报告机械校验器（纯 stdlib，2026-08-16 REFORM-GATE 裁定）

防「复核结论无证据锚点 / 锚点行号漂移 / 抽样先于复核颠倒 / 复核率虚报」。
复核报告出口前必跑（经 gate-switch spec post_gate_audit.json），任一违例 exit 1。
复核结论的语义合理性不属本闸，仍归 sv 软层（禁止开关化）。

校验项（任一失败 → violations 列出原因，exit 1）：
  1. 契约闸：report 可解析为 JSON，必填字段非空——
     audit_id、generated_at（ISO8601，报告生成时间）、sample（抽样对象）、
     findings[]（允许空数组但字段必须存在）、review_ratio、coverage_verdict 对象。
  2. 锚点闸：每条 finding 必须带 evidence_refs ≥1；每个 ref 含
     case_id + file + line + line_digest。机械校验：
       - file 在 case-root 下真实存在（禁止越出 case-root）；
       - line ∈ [1, 文件总行数]（不越界）；
       - line_digest 与该文件该行内容摘要匹配（防行号漂移）。
     【line_digest 算法（与本脚本保持一致的唯一口径）】：
       取文件第 line 行原始文本（去掉行尾换行符 \\n/\\r\\n，不去空白），
       UTF-8 编码后计算 sha1，取 hexdigest 前 8 位（小写十六进制字符串）。
       即：hashlib.sha1(line_text.encode("utf-8")).hexdigest()[:8]
  3. 抽样闸：sample 四元组字段齐全（seed/pool_hash/algo_version/timestamp），
     sample.sample_size / sample.pool_size 为非负整数且 sample_size ≤ pool_size，
     且 sample.timestamp 早于 report.generated_at（抽样必须先于复核结论）。
  4. 比率闸：review_ratio ∈ (0,1]；实际比率 = sample.sample_size / sample.pool_size，
     实际比率不得低于声明 review_ratio 的 95%（欠抽 >5% 即虚报，超抽不罚）；
     sample.exhaustive == true（池总量小于样本量下限被全量抽取）时免除此项。
  5. 覆盖闸：coverage_verdict 对象必填 verdict、gate_line_ref（门禁线定义出处）、
     blind_spot_note（盲区分析，去空白后 ≥20 字）。
  6. 勾稽闸（2026-08-16 REFORM-GATE 判A·方案1：复核结论语义本体中可枚举部分机械化）：
     findings[].claim 为可选字段，出现即强校验——
       - claim_type 必须命中枚举（coverage_verdict/severity_rating/
         evidence_sufficiency/boundary_omission），未知类型即违例（防自由发挥）；
       - coverage_verdict：必填 actual/threshold（数值）、direction（gte|lte）、
         verdict（pass|fail）；勾稽 verdict 与数值比较结果必须一致；
         且声明的 actual 数值必须出现在本 finding 至少一条锚点行原文中
         （数值可追溯，防"锚点为真但数字是编的"）；
       - severity_rating：severity ∈ critical|high|medium|low + rationale ≥10 字；
         与 finding.severity（若存在）必须一致（报告内自洽）；
       - evidence_sufficiency：required_refs 正整数，勾稽实际锚点数 ≥ 声明数；
       - boundary_omission：finding.verdict（若存在）必须为 fail
         （报遗漏即不得判通过）。
     解读合理性本体（数值之外的分析是否到位）仍留 sv 软层，禁止开关化。

用法：
  python3 post_gate_audit_check.py --report <复核报告JSON> --case-root <用例库根目录>

输出：单行 JSON {"pass": bool, "violations": [{"gate", "detail"}, ...]}
退出码：0=全过（A）/ 1=有违例（B）/ 3=输入信号不足（CLARIFY）。

留痕（rules/05_test_quality_system.md:110 复核率留痕义务的写入方）：
  每次校验结束向 ~/.agents/logs/post_gate_audit.jsonl 写入一行 JSON，
  字段 {ts, audit_id, pool_size, sample_size, review_ratio,
  anchor_invalid_rate, verdict, pool_hash}，供 :111 DRIFT_ALERT 告警取数。
  留痕写入失败不翻转门禁判定，仅以 stderr WARN 暴露。

  幂等语义（2026-08-16 幂等治理裁定）：audit_id 是一次审计（一份复核报告）
  的唯一标识（rules/05:103 契约必填字段）。同 audit_id 重跑（判 B 修复后重扳
  或重复执行）是「同一审计的重复执行」而非新事件——覆盖既有同 audit_id 行
  （保留最新记录，含修复后更新的 verdict），行数不随重跑膨胀，时序不被重复
  行污染（05:111 「连续 3 次偏低 / 骤降 >50%」以独立审计次数计）。
  audit_id 缺失或为空的报告（契约违例）不参与去重，一律追加留痕。
  测试隔离：env POST_GATE_AUDIT_LOG 可覆盖留痕路径（默认 ~/.agents/logs/...）。
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

EXIT_A, EXIT_B, EXIT_CLARIFY = 0, 1, 3
RATIO_TOLERANCE = 0.05  # 实际比率允许低于声明比率的相对容差
BLIND_SPOT_MIN_LEN = 20
AUDIT_LOG = os.environ.get("POST_GATE_AUDIT_LOG") or os.path.expanduser("~/.agents/logs/post_gate_audit.jsonl")

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$")


def parse_ts(s):
    """解析 ISO8601 时间戳为 datetime；失败返回 None。"""
    if not isinstance(s, str) or not ISO_RE.match(s.strip()):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    # 兼容 +0800 无冒号形式
    if re.search(r"[+-]\d{4}$", t):
        t = t[:-2] + ":" + t[-2:]
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def line_digest(line_text):
    """唯一口径：sha1(行原始文本去行尾换行, utf-8).hexdigest()[:8]。"""
    return hashlib.sha1(line_text.encode("utf-8")).hexdigest()[:8]


def resolve(case_root, rel):
    """解析 ref.file 到 case-root 下；返回 (真实路径, 是否越界)。"""
    root_real = os.path.realpath(case_root)
    cand = rel if os.path.isabs(rel) else os.path.join(root_real, rel)
    cand_real = os.path.realpath(cand)
    inside = cand_real == root_real or cand_real.startswith(root_real + os.sep)
    return cand_real, inside


def check_contract(report):
    violations = []
    for field in ("audit_id", "generated_at", "review_ratio"):
        v = report.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            violations.append({"gate": "契约闸", "detail": "必填字段缺失或为空: %s" % field})
    if not isinstance(report.get("sample"), dict):
        violations.append({"gate": "契约闸", "detail": "sample 缺失或不是对象（需含抽样四元组+样本清单）"})
    if not isinstance(report.get("findings"), list):
        violations.append({"gate": "契约闸", "detail": "findings 缺失或不是数组"})
    if not isinstance(report.get("coverage_verdict"), dict):
        violations.append({"gate": "契约闸", "detail": "coverage_verdict 缺失或不是对象"})
    gen = parse_ts(report.get("generated_at"))
    if report.get("generated_at") is not None and gen is None:
        violations.append({"gate": "契约闸",
                           "detail": "generated_at 不是合法 ISO8601 时间戳: %r" % report.get("generated_at")})
    return violations, gen


def check_anchors(report, case_root):
    violations = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return violations  # 契约闸已报
    for i, f in enumerate(findings):
        fid = f.get("finding_id", "<findings[%d]>" % i) if isinstance(f, dict) else "<findings[%d]>" % i
        if not isinstance(f, dict):
            violations.append({"gate": "锚点闸", "detail": "%s 不是对象" % fid})
            continue
        refs = f.get("evidence_refs")
        if not isinstance(refs, list) or len(refs) < 1:
            violations.append({"gate": "锚点闸",
                               "detail": "%s evidence_refs 缺失或为空，无锚点结论视为未复核" % fid})
            continue
        for j, ref in enumerate(refs):
            tag = "%s evidence_refs[%d]" % (fid, j)
            if not isinstance(ref, dict):
                violations.append({"gate": "锚点闸", "detail": "%s 不是对象" % tag})
                continue
            for k in ("case_id", "file", "line", "line_digest"):
                if k not in ref or ref[k] is None or (isinstance(ref[k], str) and not ref[k].strip()):
                    violations.append({"gate": "锚点闸", "detail": "%s 缺字段: %s" % (tag, k)})
                    break
            else:
                path, inside = resolve(case_root, str(ref["file"]))
                if not inside:
                    violations.append({"gate": "锚点闸", "detail": "%s 文件路径越出 case-root: %s" % (tag, ref["file"])})
                    continue
                if not os.path.isfile(path):
                    violations.append({"gate": "锚点闸", "detail": "%s 文件不存在: %s" % (tag, ref["file"])})
                    continue
                try:
                    with open(path, encoding="utf-8", errors="ignore") as fh:
                        lines = fh.read().splitlines()
                except OSError as e:
                    violations.append({"gate": "锚点闸", "detail": "%s 文件读取失败: %s" % (tag, e)})
                    continue
                try:
                    n = int(ref["line"])
                except (TypeError, ValueError):
                    violations.append({"gate": "锚点闸", "detail": "%s line 非整数: %r" % (tag, ref["line"])})
                    continue
                if not (1 <= n <= len(lines)):
                    violations.append({"gate": "锚点闸",
                                       "detail": "%s 行号越界: %s:%d（文件共 %d 行）" % (tag, ref["file"], n, len(lines))})
                    continue
                actual = line_digest(lines[n - 1])
                if str(ref["line_digest"]).strip().lower() != actual:
                    violations.append({"gate": "锚点闸",
                                       "detail": "%s line_digest 不匹配（行号漂移或内容变更）: %s:%d 声明 %s 实际 %s"
                                                 % (tag, ref["file"], n, ref["line_digest"], actual)})
    return violations


def check_sample(report, gen_ts):
    violations = []
    sample = report.get("sample")
    if not isinstance(sample, dict):
        return violations  # 契约闸已报
    for k in ("seed", "pool_hash", "algo_version", "timestamp"):
        v = sample.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            violations.append({"gate": "抽样闸", "detail": "sample 四元组字段缺失或为空: %s" % k})
    st = parse_ts(sample.get("timestamp"))
    if sample.get("timestamp") is not None and st is None:
        violations.append({"gate": "抽样闸",
                           "detail": "sample.timestamp 不是合法 ISO8601 时间戳: %r" % sample.get("timestamp")})
    if st is not None and gen_ts is not None and not (st < gen_ts):
        violations.append({"gate": "抽样闸",
                           "detail": "sample.timestamp(%s) 不早于 report.generated_at(%s)，抽样必须先于复核结论"
                                     % (sample.get("timestamp"), report.get("generated_at"))})
    for k in ("pool_size", "sample_size"):
        v = sample.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            violations.append({"gate": "抽样闸", "detail": "sample.%s 缺失或非非负整数: %r" % (k, v)})
    ps, ss = sample.get("pool_size"), sample.get("sample_size")
    if isinstance(ps, int) and isinstance(ss, int) and ps > 0 and ss > ps:
        violations.append({"gate": "抽样闸", "detail": "sample.sample_size(%d) > pool_size(%d)" % (ss, ps)})
    samples_list = sample.get("samples")
    if not isinstance(samples_list, list) or not samples_list:
        violations.append({"gate": "抽样闸", "detail": "sample.samples 样本清单缺失或为空"})
    elif isinstance(ss, int) and len(samples_list) != ss:
        violations.append({"gate": "抽样闸",
                           "detail": "sample.samples 条数(%d) 与 sample_size(%d) 不一致" % (len(samples_list), ss)})
    return violations


def check_ratio(report):
    violations = []
    rr = report.get("review_ratio")
    if not isinstance(rr, (int, float)) or isinstance(rr, bool):
        violations.append({"gate": "比率闸", "detail": "review_ratio 非数值: %r" % rr})
        return violations
    if not (0 < rr <= 1):
        violations.append({"gate": "比率闸", "detail": "review_ratio 必须 ∈ (0,1]，实际 %s" % rr})
        return violations
    sample = report.get("sample")
    if not isinstance(sample, dict):
        return violations
    if sample.get("exhaustive") is True:
        return violations  # 池总量小于下限被全量抽取，免比率偏差判定
    ps, ss = sample.get("pool_size"), sample.get("sample_size")
    if isinstance(ps, int) and isinstance(ss, int) and ps > 0:
        actual = ss / ps
        floor = rr * (1 - RATIO_TOLERANCE)
        if actual < floor:
            violations.append({"gate": "比率闸",
                               "detail": "实际比率 %.4f(%d/%d) 低于声明 review_ratio %.4f 的 95%% 下限 %.4f，比率虚报"
                                         % (actual, ss, ps, rr, floor)})
    return violations


def check_coverage_verdict(report):
    violations = []
    cv = report.get("coverage_verdict")
    if not isinstance(cv, dict):
        return violations  # 契约闸已报
    for k in ("verdict", "gate_line_ref"):
        v = cv.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            violations.append({"gate": "覆盖闸", "detail": "coverage_verdict.%s 缺失或为空" % k})
    note = cv.get("blind_spot_note")
    if not isinstance(note, str) or len(note.strip()) < BLIND_SPOT_MIN_LEN:
        violations.append({"gate": "覆盖闸",
                           "detail": "coverage_verdict.blind_spot_note 缺失或去空白后 < %d 字（实际 %s 字）"
                                     % (BLIND_SPOT_MIN_LEN,
                                        len(note.strip()) if isinstance(note, str) else "N/A")})
    return violations


CLAIM_TYPES = ("coverage_verdict", "severity_rating", "evidence_sufficiency", "boundary_omission")
SEVERITIES = ("critical", "high", "medium", "low")


def _anchor_lines(finding, case_root):
    """取 finding 全部合法锚点行的原文（供勾稽闸数值追溯复用）。"""
    texts = []
    refs = finding.get("evidence_refs")
    if not isinstance(refs, list):
        return texts
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        try:
            path, inside = resolve(case_root, str(ref.get("file", "")))
            if not inside or not os.path.isfile(path):
                continue
            n = int(ref.get("line"))
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
            if 1 <= n <= len(lines):
                texts.append(lines[n - 1])
        except (TypeError, ValueError, OSError):
            continue
    return texts


def check_claims(report, case_root):
    """勾稽闸：findings[].claim 可选，出现即强校验（机械可判部分）。"""
    violations = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return violations  # 契约闸已报
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        claim = f.get("claim")
        if claim is None:
            continue  # 可选字段，不带不罚
        fid = f.get("finding_id", "<findings[%d]>" % i)
        if not isinstance(claim, dict):
            violations.append({"gate": "勾稽闸", "detail": "%s claim 不是对象" % fid})
            continue
        ct = claim.get("claim_type")
        if ct not in CLAIM_TYPES:
            violations.append({"gate": "勾稽闸",
                               "detail": "%s claim.claim_type 非法: %r（枚举: %s）"
                                         % (fid, ct, "/".join(CLAIM_TYPES))})
            continue
        tag = "%s claim[%s]" % (fid, ct)
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
                if not any(str(actual) in t for t in _anchor_lines(f, case_root)):
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 声明数值 %s 未出现在所引锚点行原文（数值不可追溯）"
                                                 % (tag, actual)})
        elif ct == "severity_rating":
            sev = claim.get("severity")
            if sev not in SEVERITIES:
                violations.append({"gate": "勾稽闸", "detail": "%s.severity 非法: %r" % (tag, sev)})
            rat = claim.get("rationale")
            if not isinstance(rat, str) or len(rat.strip()) < 10:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.rationale 缺失或去空白后 <10 字（定级必须给依据）" % tag})
            fsev = f.get("severity")
            if sev in SEVERITIES and fsev is not None and fsev != sev:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s 自洽矛盾: finding.severity=%s 与 claim.severity=%s 不一致"
                                             % (tag, fsev, sev)})
        elif ct == "evidence_sufficiency":
            req = claim.get("required_refs")
            if not isinstance(req, int) or isinstance(req, bool) or req < 1:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.required_refs 非正整数: %r" % (tag, req)})
            else:
                refs = f.get("evidence_refs")
                n = len(refs) if isinstance(refs, list) else 0
                if n < req:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 勾稽矛盾: 声明需 %d 条证据，实际锚点仅 %d 条"
                                                 % (tag, req, n)})
        elif ct == "boundary_omission":
            fv = f.get("verdict")
            if fv is not None and fv != "fail":
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s 勾稽矛盾: 报告边界遗漏却判 verdict=%s（遗漏即不得判通过）"
                                             % (tag, fv)})
    return violations


def append_audit_log(report, violations):
    """rules/05:110 留痕义务写入方：向 AUDIT_LOG 写入一行审计记录。

    幂等：audit_id 非空字符串时，同 audit_id 行被本记录覆盖（同一审计重跑
    不增行、更新为最新结果）；audit_id 缺失/为空一律追加。
    """
    sample = report.get("sample")
    sample = sample if isinstance(sample, dict) else {}
    findings = report.get("findings")
    findings = findings if isinstance(findings, list) else []
    total_refs = 0
    for f in findings:
        if isinstance(f, dict) and isinstance(f.get("evidence_refs"), list):
            total_refs += len(f["evidence_refs"])
    anchor_viol = sum(1 for v in violations if v.get("gate") == "锚点闸")
    if total_refs > 0:
        anchor_invalid_rate = round(min(anchor_viol, total_refs) / total_refs, 4)
    else:
        anchor_invalid_rate = 1.0 if anchor_viol else 0.0
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "audit_id": report.get("audit_id"),
        "pool_size": sample.get("pool_size"),
        "sample_size": sample.get("sample_size"),
        "review_ratio": report.get("review_ratio"),
        "anchor_invalid_rate": anchor_invalid_rate,
        "verdict": "A" if not violations else "B",
        "pool_hash": sample.get("pool_hash"),
    }
    aid = record["audit_id"]
    dedup = isinstance(aid, str) and bool(aid.strip())
    new_line = json.dumps(record, ensure_ascii=False)
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        lines = []
        if os.path.isfile(AUDIT_LOG):
            with open(AUDIT_LOG, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        kept, replaced = [], False
        for ln in lines:
            if dedup and ln.strip():
                try:
                    old = json.loads(ln)
                except json.JSONDecodeError:
                    old = None
                if isinstance(old, dict) and old.get("audit_id") == aid:
                    if not replaced:
                        kept.append(new_line)
                        replaced = True
                    continue  # 同一审计的历史重复行一并清除
            kept.append(ln)
        if not replaced:
            kept.append(new_line)
        tmp = AUDIT_LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("".join(ln + "\n" for ln in kept))
        os.replace(tmp, AUDIT_LOG)
        if replaced:
            print("NOTE: post_gate_audit.jsonl 幂等覆盖 audit_id=%s"
                  "（同一审计重跑，更新为最新记录，行数不变）" % aid, file=sys.stderr)
    except OSError as e:
        print("WARN: post_gate_audit.jsonl 留痕写入失败: %s" % e, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="POST_GATE_AUDIT 复核报告机械校验器（契约/锚点/抽样/比率/覆盖/勾稽 六闸）")
    ap.add_argument("--report", required=True, help="复核报告 JSON 路径")
    ap.add_argument("--case-root", required=True, help="用例库根目录")
    args = ap.parse_args()

    if not os.path.isfile(args.report):
        print(json.dumps({"pass": False, "error": "report 不存在: %s" % args.report}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    if not os.path.isdir(args.case_root):
        print(json.dumps({"pass": False, "error": "case-root 不存在: %s" % args.case_root}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    try:
        with open(args.report, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(json.dumps({"pass": False, "error": "report JSON 读取/解析失败: %s" % e}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    if not isinstance(report, dict):
        print(json.dumps({"pass": False, "error": "report 顶层必须为对象"}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    violations, gen_ts = check_contract(report)
    violations.extend(check_anchors(report, args.case_root))
    violations.extend(check_sample(report, gen_ts))
    violations.extend(check_ratio(report))
    violations.extend(check_coverage_verdict(report))
    violations.extend(check_claims(report, args.case_root))

    append_audit_log(report, violations)

    # 单行输出：gate_switch script_exit 取 tail[-1] 作违例详情
    print(json.dumps({"pass": not violations, "violations": violations}, ensure_ascii=False))
    sys.exit(EXIT_A if not violations else EXIT_B)


if __name__ == "__main__":
    main()
