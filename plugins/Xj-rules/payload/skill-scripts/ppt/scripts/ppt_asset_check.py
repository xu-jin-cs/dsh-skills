#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_asset_check.py — ppt 主链素材三禁令合并核验脚本（gate-switch spec ppt_asset_gate.json 的 script_exit 后端）

合并 SKILL.md 三处素材类禁令（原语表达不足的部分收进本脚本，纯 stdlib）：
  L137  flow_allow=false 判定前必须先跑 ppt_spider.py 下载补齐
        → $OFFICEPLUS_ASSETS_ROOT/docs/spider_asset_library.json 存在且 mtime 新于运行起点参照
          （ppt_spider.py main 每次运行无条件 merge_library 重写库 JSON，mtime 即"跑过"的机械证据）
  L268  页面装饰插画 audit：decoration_spec.elements[].asset_path 逐个 file_exists；
        null/文件缺失计缺口，缺口须登记 00_asset_audit.json.shape_fallback_registry 且全表 ≤3 处
  L471  方案含 style_label 时 <run>/00_style_reference.md 必须存在，且文首（前 10 行）
        标注「复刻模板来源」

用法：
  python3 ppt_asset_check.py --run-dir <run_dir> [--style-label <label>]

退出码：0 = 全过（A）；1 = 有违例（B，stdout JSON 的 violations 即理由）；2 = 参数/输入错误。
素材根目录取环境变量 OFFICEPLUS_ASSETS_ROOT（缺省 /Users/xujin/Desktop/桌面归档汇总/不常用文件夹/2026-08-23/officeplus_ppt_assets），
与 ppt_spider.py 口径一致；A/B 实测可用 env 指向 fixtures。
"""
import argparse
import glob
import json
import os
import sys

STYLE_REF_HEAD_LINES = 10
STYLE_REF_MARK = "复刻模板来源"
MAX_SHAPE_FALLBACK = 3


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _run_start_ref(run_dir):
    """运行起点参照：优先 input_source/input.txt（首节点上下文，运行起点写入），
    其次 00_quality_standard.md（节点01 首产物），兜底 run_dir 直属最早 mtime 常规文件。"""
    for cand in (os.path.join(run_dir, "input_source", "input.txt"),
                 os.path.join(run_dir, "00_quality_standard.md")):
        if os.path.isfile(cand):
            return cand
    files = [p for p in glob.glob(os.path.join(run_dir, "*")) if os.path.isfile(p)]
    if files:
        return min(files, key=os.path.getmtime)
    return None


def check_spider_first(run_dir, audit, assets_root, violations, passed):
    """L137：flow_allow=false 时，spider 库 mtime 必须新于运行起点。"""
    if not isinstance(audit, dict) or audit.get("flow_allow") is not False:
        passed.append("L137 spider 先行：flow_allow!=false，免核")
        return
    ref = _run_start_ref(run_dir)
    if not ref:
        violations.append("L137: flow_allow=false 但无法确定运行起点参照（input_source/input.txt 等缺失）")
        return
    lib = os.path.join(assets_root, "docs", "spider_asset_library.json")
    if not os.path.isfile(lib):
        violations.append(
            "L137: flow_allow=false 但 spider 库不存在 %s（判定前必须先跑 ppt_spider.py）" % lib)
        return
    if os.path.getmtime(lib) > os.path.getmtime(ref):
        passed.append("L137 spider 先行：库 mtime 新于运行起点参照 %s" % os.path.basename(ref))
    else:
        violations.append(
            "L137: flow_allow=false 但 spider 库 %s 不新于运行起点参照 %s（本运行未先跑 ppt_spider.py 下载补齐）"
            % (lib, ref))


def _resolve_asset(asset_path, run_dir, assets_root):
    """asset_path 候选落点：绝对路径原样；相对路径依次相对 run_dir、assets_root、cwd。"""
    if os.path.isabs(asset_path):
        return [asset_path]
    return [os.path.join(run_dir, asset_path),
            os.path.join(assets_root, asset_path),
            asset_path]


def check_decoration_audit(run_dir, audit, assets_root, violations, passed):
    """L268：decoration_spec.elements[].asset_path 逐个 file_exists；缺口须登记且 ≤3。"""
    scheme = _load_json(os.path.join(run_dir, "00_scheme_selected.json")) or \
        _load_json(os.path.join(run_dir, "extracted_scheme.json"))
    elements = (((scheme or {}).get("decoration_spec") or {}).get("elements")) or []
    if not elements:
        passed.append("L268 装饰 audit：decoration_spec.elements 为空，免核")
        return
    registry = ((audit or {}).get("shape_fallback_registry")) or []
    registry_blob = json.dumps(registry, ensure_ascii=False)
    if len(registry) > MAX_SHAPE_FALLBACK:
        violations.append(
            "L268: shape_fallback_registry 登记 %d 处超过单套上限 %d" % (len(registry), MAX_SHAPE_FALLBACK))
    gaps, ok_n = [], 0
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            continue
        name = el.get("name") or el.get("type") or "elements[%d]" % i
        asset_path = el.get("asset_path")
        exists = bool(asset_path) and any(
            os.path.isfile(c) for c in _resolve_asset(asset_path, run_dir, assets_root))
        if exists:
            ok_n += 1
        elif name in registry_blob or (asset_path and asset_path in registry_blob):
            passed.append("L268 装饰缺口已登记 shape 兜底：%s" % name)
        else:
            gaps.append(name)
    if gaps:
        violations.append(
            "L268: 装饰插画 asset_path 缺失/文件不存在且未登记 shape_fallback_registry：%s" % "、".join(gaps))
    if ok_n:
        passed.append("L268 装饰 audit：%d 项 asset_path 文件存在" % ok_n)


def check_style_reference(run_dir, style_label, violations, passed):
    """L471：style_label 存在时 00_style_reference.md 存在 + 文首来源标注。"""
    if not style_label:
        scheme = _load_json(os.path.join(run_dir, "00_scheme_selected.json")) or {}
        style_label = scheme.get("style_label")
    if not style_label:
        passed.append("L471 style_reference：无 style_label，免核")
        return
    ref = os.path.join(run_dir, "00_style_reference.md")
    if not os.path.isfile(ref):
        violations.append(
            "L471: 方案含 style_label=%r 但 %s 不存在（核心步骤7 强制蒸馏龙骨档案）" % (style_label, ref))
        return
    with open(ref, encoding="utf-8", errors="ignore") as f:
        head = [next(f, "") for _ in range(STYLE_REF_HEAD_LINES)]
    if any(STYLE_REF_MARK in line for line in head):
        passed.append("L471 style_reference：存在且文首含「%s」标注" % STYLE_REF_MARK)
    else:
        violations.append(
            "L471: %s 文首 %d 行无「%s」来源标注" % (ref, STYLE_REF_HEAD_LINES, STYLE_REF_MARK))


def main():
    ap = argparse.ArgumentParser(description="ppt 素材三禁令合并核验（ppt_asset_gate 后端）")
    ap.add_argument("--run-dir", required=True, help="运行目录 run_dir")
    ap.add_argument("--style-label", default=None, help="可选：覆盖 00_scheme_selected.json 的 style_label")
    args = ap.parse_args()

    run_dir = os.path.abspath(os.path.expanduser(args.run_dir))
    assets_root = os.environ.get("OFFICEPLUS_ASSETS_ROOT",
                                 "/Users/xujin/Desktop/桌面归档汇总/不常用文件夹/2026-08-23/officeplus_ppt_assets")
    violations, passed = [], []
    if not os.path.isdir(run_dir):
        print(json.dumps({"ok": False, "violations": ["run_dir 不存在: %s" % run_dir]},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    audit = _load_json(os.path.join(run_dir, "00_asset_audit.json"))
    check_spider_first(run_dir, audit, assets_root, violations, passed)
    check_decoration_audit(run_dir, audit, assets_root, violations, passed)
    check_style_reference(run_dir, args.style_label, violations, passed)

    print(json.dumps({"gate": "ppt_asset_gate", "run_dir": run_dir, "ok": not violations,
                      "violations": violations, "passed": passed},
                     ensure_ascii=False, indent=2))
    # 末行单行结论：gate_switch script_exit 取 stdout 末行作为 B 档理由，必须自含
    print("VIOLATIONS: " + " | ".join(violations) if violations else "ALL_CHECKS_PASSED")
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
