#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
council_reverify_claims_check.py — review-council 对抗复核 verdict 勾稽校验器
（纯 stdlib，2026-08-16 GENERALIZE-GATE 泛化克隆·路A council_reverify）

骨架真源：sv-supervisor/scripts/post_gate_audit_check.py 的 check_claims（勾稽闸）。
枚举与勾稽规则原样复制，禁止增删 claim_type；唯一适配点（基线允许）：
  - 锚点行取数方式：reverify-*.json 的锚点不是结构化 evidence_refs，而是
    verdict 条目 reason/correction 文本内联的 file:line（可带 -end 行段）——
    解析复用同目录 council_gate_check.py 的 ANCHOR_RE/_is_anchor_path/_resolve，
    按 project 根解析后读取锚点行原文，供 coverage_verdict 数值追溯；
  - 字段映射：finding→verdict 条目；finding.verdict 的 fail 语义映射为
    reverify verdict 的中文枚举（pass 等价集 = {"pass", "成立"}）。

冻结规则（claim 为可选字段：不带不罚，出现即强校验）：
  - claim_type 四枚举：coverage_verdict / severity_rating /
    evidence_sufficiency / boundary_omission，未知类型即违例；
  - coverage_verdict：actual/threshold 数值 + direction(gte|lte) +
    verdict(pass|fail)，verdict 必须与数值比较一致；actual 必须出现在
    本条 verdict 至少一个锚点行原文中（数值可追溯）；
  - severity_rating：severity ∈ critical|high|medium|low + rationale ≥10 字 +
    与 verdict 条目 severity（若存在）自洽；
  - evidence_sufficiency：解析到的实际锚点数 ≥ required_refs；
  - boundary_omission：报遗漏即 verdict 不得为 pass 等价（成立/pass）。

reverify-*.json 契约（真实格式，见 SKILL.md 06 节）：
  顶层为 verdict 条目数组：{"finding_id", "verdict": "成立/部分成立/不成立",
  "reason", "correction"}；兼容含 findings/verdicts/entries 数组的对象。

用法（gate-switch script_exit 包装，glob 到最新 reverify-*.json）：
  python3 council_reverify_claims_check.py \
      --reverify-glob "<project>/council/reverify-*.json" --project <project>

输出：单行 JSON {"pass": bool, "reverify_file": str, "entries": int,
               "violations": [{"gate", "detail"}, ...]}
退出码：0=全过（A）/ 1=有违例（B）/ 3=输入信号不足（CLARIFY，如无匹配文件）。
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from council_gate_check import ANCHOR_RE, _is_anchor_path, _resolve  # noqa: E402

EXIT_A, EXIT_B, EXIT_CLARIFY = 0, 1, 3

CLAIM_TYPES = ("coverage_verdict", "severity_rating", "evidence_sufficiency", "boundary_omission")
SEVERITIES = ("critical", "high", "medium", "low")
# 字段映射（基线允许点）：reverify verdict 中文枚举中「不得判通过」的 pass 等价集
PASS_EQUIV = ("pass", "成立")

# file:line 锚点（复用 council_gate_check 口径），允许 :13-14 行段写法
RANGE_RE = re.compile(ANCHOR_RE.pattern + r"(?:-(\d+))?")
MAX_RANGE_SPAN = 50  # 行段防滥用上限

_ANCHOR_SOURCE_FIELDS = ("reason", "correction", "evidence")


def parse_anchors(text):
    """从文本解析 (rel_path, line_start, line_end) 锚点列表。"""
    out = []
    for rel, a, b in RANGE_RE.findall(text or ""):
        if not _is_anchor_path(rel):
            continue
        n1 = int(a)
        n2 = int(b) if b else n1
        if n2 < n1:
            n1, n2 = n2, n1
        if n2 - n1 > MAX_RANGE_SPAN:
            n2 = n1 + MAX_RANGE_SPAN
        out.append((rel, n1, n2))
    return out


def _entry_anchor_blob(entry):
    return "\n".join(str(entry.get(k) or "") for k in _ANCHOR_SOURCE_FIELDS)


def entry_anchor_count(entry):
    """条目内联文本中解析到的锚点数（evidence_sufficiency 勾稽取数）。"""
    return len(parse_anchors(_entry_anchor_blob(entry)))


def anchor_lines(entry, project):
    """取条目全部可解析锚点行的原文（coverage_verdict 数值追溯取数）。"""
    texts = []
    for rel, n1, n2 in parse_anchors(_entry_anchor_blob(entry)):
        path, inside = _resolve(project, rel)
        if not inside or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n in range(n1, min(n2, len(lines)) + 1):
            texts.append(lines[n - 1])
    return texts


def check_claims(entries, project):
    """勾稽闸（骨架原样克隆）：verdict 条目 claim 可选，出现即强校验。"""
    violations = []
    for i, f in enumerate(entries):
        if not isinstance(f, dict):
            continue
        claim = f.get("claim")
        if claim is None:
            continue  # 可选字段，不带不罚
        fid = f.get("finding_id", "<entries[%d]>" % i)
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
                if not any(str(actual) in t for t in anchor_lines(f, project)):
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
                                   "detail": "%s 自洽矛盾: verdict.severity=%s 与 claim.severity=%s 不一致"
                                             % (tag, fsev, sev)})
        elif ct == "evidence_sufficiency":
            req = claim.get("required_refs")
            if not isinstance(req, int) or isinstance(req, bool) or req < 1:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s.required_refs 非正整数: %r" % (tag, req)})
            else:
                n = entry_anchor_count(f)
                if n < req:
                    violations.append({"gate": "勾稽闸",
                                       "detail": "%s 勾稽矛盾: 声明需 %d 条证据，实际锚点仅 %d 条"
                                                 % (tag, req, n)})
        elif ct == "boundary_omission":
            fv = f.get("verdict")
            if fv is not None and fv in PASS_EQUIV:
                violations.append({"gate": "勾稽闸",
                                   "detail": "%s 勾稽矛盾: 报告边界遗漏却判 verdict=%s（遗漏即不得判通过/成立）"
                                             % (tag, fv)})
    return violations


def load_entries(path):
    """读取 reverify-*.json：顶层数组，或含 findings/verdicts/entries 数组的对象。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, "reverify JSON 读取/解析失败: %s" % e
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        entries = None
        for k in ("findings", "verdicts", "entries"):
            if isinstance(data.get(k), list):
                entries = data[k]
                break
        if entries is None:
            return None, "reverify JSON 契约不符：顶层需为数组或含 findings/verdicts/entries 数组的对象"
    else:
        return None, "reverify JSON 契约不符：顶层需为数组或对象"
    for i, f in enumerate(entries):
        if not isinstance(f, dict):
            return None, "entries[%d] 不是对象" % i
    return entries, None


def main():
    ap = argparse.ArgumentParser(description="review-council 对抗复核 verdict 勾稽校验器（claim 四枚举）")
    ap.add_argument("--reverify-glob", required=True,
                    help="reverify-*.json 的 glob 模式，取 mtime 最新一份校验")
    ap.add_argument("--project", required=True, help="被检项目路径（锚点解析根）")
    args = ap.parse_args()

    if not os.path.isdir(args.project):
        print(json.dumps({"pass": False, "error": "project 不存在: %s" % args.project},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    matches = glob.glob(args.reverify_glob)
    if not matches:
        print(json.dumps({"pass": False, "error": "glob 无匹配: %s" % args.reverify_glob},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    target = max(matches, key=os.path.getmtime)

    entries, err = load_entries(target)
    if err:
        print(json.dumps({"pass": False, "reverify_file": target, "error": err},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    violations = check_claims(entries, args.project)
    result = {"pass": not violations,
              "reverify_file": target,
              "entries": len(entries),
              "violations": violations}
    # 单行输出：gate_switch script_exit 取 tail[-1] 作违例详情
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(EXIT_A if not violations else EXIT_B)


if __name__ == "__main__":
    main()
