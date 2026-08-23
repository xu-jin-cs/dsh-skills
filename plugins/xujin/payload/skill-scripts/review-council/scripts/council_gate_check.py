#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
council_gate_check.py — review-council 三闸机械校验器（纯 stdlib，2026-08-15 裁定）

防「体检意见的证据锚点 file:line 凭空编造」。报告交付前必跑，任一违例 exit 1。

三闸（对齐 review-council/SKILL.md「门禁（三闸）」段）：
  1. 证据闸：逐条 finding 的 evidence 必须含可解析锚点——
     file:line 形式：文件在 project 下真实存在 且 行号 ∈ [1, 总行数]；
     裸文件形式（无行号，如 "03_数据链路图.md 第2节"）：文件在 project 下真实存在。
     锚点缺失 / 文件不存在 / 行号越界 → violation。
     （锚点行号「内容相关性」不属本闸，仍归软层抽查。）
  2. 细则闸：severity ∈ {P0, P1} 的 finding 必须有非空 rules 字段（字符串长度 ≥ 20）。
  3. 覆盖闸：findings 必须覆盖九维方向（清单硬编码自 SKILL.md 九维表）。
     缺维 → violation；允许 finding 数为 0 的维以占位条目占位：
     {"direction": "<维度>", "severity": "no_issue"}（或 status="no_issue" / severity="不适用"）。
     占位条目免证据闸/细则闸，仅计入覆盖。

findings JSON 契约（report-<date>.json，机读）：顶层为 finding 数组，
或含 "findings" 数组字段的对象。finding 字段见 SKILL.md 03 节。

用法：
  python3 council_gate_check.py --findings <report-*.json> --project <被检项目路径>

输出：单行 JSON {"pass": bool, "total_findings": int,
               "violations": [{"finding_id", "gate", "detail"}, ...]}
退出码：0=全过（A）/ 1=有违例（B）/ 3=输入信号不足（CLARIFY）。
"""
import argparse
import json
import os
import re
import sys

# 九维清单硬编码自 review-council/SKILL.md「02 专家分诊」九维表（改 SKILL.md 需同步此处）
NINE_DIMENSIONS = [
    "代码质量",
    "功能设计合理性",
    "可拓展性",
    "底层规则严谨性",
    "性能风险",
    "读写准确性",
    "幻觉与精度",
    "数据膨胀",
    "界面美观",
]

NO_ISSUE_MARKERS = ("no_issue", "n/a", "不适用", "无问题")

# file:line 锚点：token 必须是路径样——含 '/' 或以已知代码/文档扩展名结尾——
# 冒号后行号为纯整数。'2.6:1' 类十进制比值（'.6' 非白名单扩展名、token 无 '/'）不得命中。
_ANCHOR_EXTS = ("py", "md", "json", "yaml", "yml", "js", "ts", "tsx", "jsx",
                "sh", "sql", "html", "css", "vue")
ANCHOR_RE = re.compile(r"([0-9A-Za-z_./\-\u4e00-\u9fff]+?\.[A-Za-z0-9]+):(\d+)")
# 裸文件回退：空白分隔的 token 中带扩展名者
BARE_PATH_RE = re.compile(r"^[0-9A-Za-z_./\-\u4e00-\u9fff]+?\.[A-Za-z0-9]+$")
_BASENAME_RE = re.compile(r"^[0-9A-Za-z_\-\u4e00-\u9fff]+\.([A-Za-z0-9]+)$")


def _is_anchor_path(token):
    """路径样前置过滤：basename 须为 name.ext 形态，且 token 含 '/' 或扩展名在白名单内。
    排除 '2.6'（'.6' 非扩展名、无 '/'）、'/'（basename 为空）等伪锚点。"""
    base = token.rsplit("/", 1)[-1]
    m = _BASENAME_RE.match(base)
    if not m:
        return False
    return "/" in token or m.group(1).lower() in _ANCHOR_EXTS

EXIT_A, EXIT_B, EXIT_CLARIFY = 0, 1, 3

_line_count_cache = {}


def _line_count(path):
    if path not in _line_count_cache:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                _line_count_cache[path] = len(f.read().splitlines())
        except OSError:
            _line_count_cache[path] = None
    return _line_count_cache[path]


# basename 兜底搜索：限深、排除重型/派生目录
_SEARCH_EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "dist", "build"}
_SEARCH_MAX_DEPTH = 6
_basename_cache = {}


def _basename_search(project_real, basename):
    """在 project 下递归按 basename 兜底搜索，返回命中真实路径列表（限深+排除目录）。"""
    key = (project_real, basename)
    if key in _basename_cache:
        return _basename_cache[key]
    hits = []
    for root, dirs, files in os.walk(project_real):
        dirs[:] = [d for d in dirs if d not in _SEARCH_EXCLUDE_DIRS]
        rel_root = os.path.relpath(root, project_real)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        if depth >= _SEARCH_MAX_DEPTH:
            dirs[:] = []
        if basename in files:
            hits.append(os.path.join(root, basename))
    _basename_cache[key] = hits
    return hits


def _resolve(project, rel):
    """把锚点路径解析到 project 下；返回 (真实路径, 是否越出 project)。
    project 根直接拼接失败（文件不存在）且 rel 为相对路径时，做递归 basename 兜底：
    唯一命中 → 解析到该路径；多命中（歧义）→ 取最短路径（层级最浅者最可能为正主）；
    零命中 → 维持原候选（不存在，由调用方判违例）。"""
    project_real = os.path.realpath(project)
    cand = rel if os.path.isabs(rel) else os.path.join(project_real, rel)
    cand_real = os.path.realpath(cand)
    inside = cand_real == project_real or cand_real.startswith(project_real + os.sep)
    if inside and not os.path.isfile(cand_real) and not os.path.isabs(rel):
        hits = _basename_search(project_real, os.path.basename(rel))
        if len(hits) == 1:
            cand_real = os.path.realpath(hits[0])
        elif len(hits) > 1:
            # 多命中歧义：按任务裁定取最短路径
            cand_real = os.path.realpath(min(hits, key=len))
    return cand_real, inside


def check_evidence(finding, project):
    """证据闸：返回 violation detail 列表（空=通过）。"""
    fid = finding.get("finding_id", "<无 finding_id>")
    ev = finding.get("evidence")
    if not isinstance(ev, str) or not ev.strip():
        return [{"finding_id": fid, "gate": "证据闸",
                 "detail": "evidence 为空或缺失，禁止无证据锚点的意见"}]
    anchors = [(rel, n) for rel, n in ANCHOR_RE.findall(ev) if _is_anchor_path(rel)]
    if anchors:
        bad = []
        for rel, lineno in anchors:
            path, inside = _resolve(project, rel)
            if not inside:
                bad.append("%s:%s（路径越出 project）" % (rel, lineno))
            elif not os.path.isfile(path):
                bad.append("%s:%s（文件不存在）" % (rel, lineno))
            else:
                total = _line_count(path)
                n = int(lineno)
                if total is None or not (1 <= n <= total):
                    bad.append("%s:%s（行号越界，文件共 %s 行）" % (rel, lineno, total))
        if bad:
            return [{"finding_id": fid, "gate": "证据闸",
                     "detail": "锚点失效: " + "; ".join(bad)}]
        return []
    # 无 file:line 锚点 → 裸文件回退（SKILL.md 允许 "报告.md 第N节" 形式，机械层只能验文件存在）
    for token in ev.split():
        if BARE_PATH_RE.match(token) and _is_anchor_path(token):
            path, inside = _resolve(project, token)
            if inside and os.path.isfile(path):
                return []
    return [{"finding_id": fid, "gate": "证据闸",
             "detail": "evidence 无可解析锚点（既无有效 file:line 也无 project 下真实文件）: %r" % ev}]


def check_rules(finding):
    """细则闸：P0/P1 必须有非空 rules（≥20 字符）。"""
    sev = str(finding.get("severity", "")).upper()
    if sev not in ("P0", "P1"):
        return []
    rules = finding.get("rules")
    fid = finding.get("finding_id", "<无 finding_id>")
    if not isinstance(rules, str) or len(rules.strip()) < 20:
        return [{"finding_id": fid, "gate": "细则闸",
                 "detail": "severity=%s 但 rules 缺失/非字符串/长度<20（实际 %s 字符）"
                           % (sev, len(rules.strip()) if isinstance(rules, str) else "N/A")}]
    return []


def _is_placeholder(finding):
    """覆盖占位条目：无问题/不适用 标记，免证据闸与细则闸。"""
    sev = str(finding.get("severity", "")).strip().lower()
    status = str(finding.get("status", "")).strip().lower()
    return sev in NO_ISSUE_MARKERS or status in NO_ISSUE_MARKERS


def _direction_matches(direction, dim):
    """方向名归一匹配：相等/互含/前 4 字相同（兼容 "底层规则一致性"≈"底层规则严谨性"）。"""
    d = re.sub(r"\s+", "", str(direction or ""))
    if not d:
        return False
    return d == dim or dim in d or d in dim or d[:4] == dim[:4]


def check_coverage(findings):
    """覆盖闸：九维每维至少一条 finding 或 no_issue 占位。"""
    missing = []
    for dim in NINE_DIMENSIONS:
        if not any(_direction_matches(f.get("direction"), dim) for f in findings):
            missing.append(dim)
    if missing:
        return [{"finding_id": "<coverage>", "gate": "覆盖闸",
                 "detail": "缺维: %s（允许以 severity=no_issue 占位条目补齐）" % "、".join(missing)}]
    return []


def load_findings(path):
    """接受顶层数组或含 findings 数组的对象。返回 (findings列表, 错误消息)。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, "findings JSON 读取/解析失败: %s" % e
    if isinstance(data, list):
        findings = data
    elif isinstance(data, dict) and isinstance(data.get("findings"), list):
        findings = data["findings"]
    else:
        return None, "findings JSON 契约不符：顶层需为数组或含 findings 数组的对象"
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            return None, "findings[%d] 不是对象" % i
    return findings, None


def main():
    ap = argparse.ArgumentParser(description="review-council 三闸机械校验器（证据闸/细则闸/覆盖闸）")
    ap.add_argument("--findings", required=True, help="report-*.json 路径")
    ap.add_argument("--project", required=True, help="被检项目路径")
    args = ap.parse_args()

    if not os.path.isfile(args.findings):
        print(json.dumps({"pass": False, "error": "findings 不存在: %s" % args.findings},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)
    if not os.path.isdir(args.project):
        print(json.dumps({"pass": False, "error": "project 不存在: %s" % args.project},
                         ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    findings, err = load_findings(args.findings)
    if err:
        print(json.dumps({"pass": False, "error": err}, ensure_ascii=False))
        sys.exit(EXIT_CLARIFY)

    violations = []
    real_count = 0
    for f in findings:
        if _is_placeholder(f):
            continue  # 占位条目只参与覆盖闸
        real_count += 1
        violations.extend(check_evidence(f, args.project))
        violations.extend(check_rules(f))
    violations.extend(check_coverage(findings))

    result = {"pass": not violations,
              "total_findings": real_count,
              "violations": violations}
    # 单行输出：gate_switch script_exit 取 tail[-1] 作违例详情
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(EXIT_A if not violations else EXIT_B)


if __name__ == "__main__":
    main()
