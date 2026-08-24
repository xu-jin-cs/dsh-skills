#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_selfcheck.py — test-case-designer Step 5 自检清单机械化校验器（纯 stdlib，2026-08-15）

本源抽象：Step 5 自检清单 18 项中"机械可判"的子集落地为 0/1 校验，剥夺
"扫一眼就声明自检通过"的手写判定权；纯语义项不判，标注 semantic_deferred 留软层。

用法：
  python3 case_selfcheck.py --cases <用例JSON路径> [--schema <.api-schema.json路径>]

输入兼容：
  - execution-list.json（顶层 "cases" 数组）
  - .api-test-cases.json（schema 3.1，顶层 "cases" 数组）
  - 顶层直接为用例数组的 JSON

机械校验项（12 项）：
  per-case:
    1. source_node 非空
    2. source_branch 非空
    3. test_methods 非空且取值 ⊆ {BV,EC,DL,SC,EX,CP,IS}
    4. scene_type ∈ 7 类枚举（normal/exception/auth/dependency/service_error/compat/security）
    5. source_branch == scene_type（声明了 scene_type 的用例逐条成立）
    6. expected 非空（含 expected/request 字段的用例）
    7. 含 steps_desc 的异步用例 smoke 必须为 false（异步禁 smoke）
    8. mock_injected == true ⇒ scene_type == service_error
    9. 确认分支用例必有配对取消分支（按 case_name/title 的「-确认分支/-取消分支」配对计数）
  file-level:
    10. smoke 标记数 ∈ [5,8]（cases 中 smoke==true 计数；有 smoke_cases 列表时取列表长度）
    11. 7 类测试点方法全覆盖：全集 test_methods ∪ ⊇ {BV,EC,DL,SC,EX,CP,IS}
    12. --schema 提供时：用例 module 三级（major/minor/feature）与契约 endpoints[].module 逐字一致

输出：JSON {pass, total_cases, checks, violations[{case_id, check, detail}], semantic_deferred}
退出码：0=全过；1=存在违例；2=输入/解析错误。

语义项（不判，留 test-lead 软层）：等价类充分性、断言强弱、场景合理性、按钮全量覆盖、
闭环复原（删除/关闭/还原步骤）、无冗余用例等——机械不可判，见 semantic_deferred。
"""
import argparse
import json
import sys

VALID_METHODS = {"BV", "EC", "DL", "SC", "EX", "CP", "IS"}
SCENE_TYPES = {"normal", "exception", "auth", "dependency",
               "service_error", "compat", "security"}
SMOKE_MIN, SMOKE_MAX = 5, 8

SEMANTIC_DEFERRED = [
    "等价类充分性（有效/无效类划分是否足够）",
    "断言强弱（期望是否具体到可判，弱断言剔除）",
    "场景合理性（测试点与业务场景匹配度）",
    "按钮全量覆盖（页面所有可交互元素 vs 用例覆盖，需 UI 资产对照）",
    "闭环复原（逆向删除/弹窗关闭/配置还原步骤完整性）",
    "无冗余用例（语义级重复判定）",
]


def _nonempty(v):
    return v is not None and v != "" and v != [] and v != {}


def load_cases(path):
    """加载用例 JSON，返回 (cases_list, error)。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, f"用例 JSON 解析失败: {e}"
    if isinstance(data, list):
        cases = data
    elif isinstance(data, dict) and isinstance(data.get("cases"), list):
        cases = data["cases"]
    else:
        return None, "用例 JSON 结构非法：顶层需为数组或含 \"cases\" 数组的对象"
    if not all(isinstance(c, dict) for c in cases):
        return None, "cases 数组中存在非对象元素"
    return cases, None


def load_schema_modules(path):
    """加载 .api-schema.json，返回 (module 三级元组集合, error)。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, f"schema JSON 解析失败: {e}"
    endpoints = data.get("endpoints") if isinstance(data, dict) else None
    if not isinstance(endpoints, list):
        return None, "schema 结构非法：缺少 \"endpoints\" 数组"
    mods = set()
    for ep in endpoints:
        m = (ep or {}).get("module") or {}
        if all(m.get(k) for k in ("major", "minor", "feature")):
            mods.add((m["major"], m["minor"], m["feature"]))
    return mods, None


def case_label(c, idx):
    return c.get("case_id") or f"<case[{idx}]>"


def case_name_of(c):
    return c.get("case_name") or c.get("title") or ""


def run_checks(cases, schema_modules):
    """执行全部机械校验，返回 violations 列表 [{case_id, check, detail}]。"""
    v = []
    FILE = "<file>"

    # ---- per-case 校验 ----
    confirm_bases, cancel_bases = {}, {}
    for i, c in enumerate(cases):
        cid = case_label(c, i)

        # 1-3. 三要素逐条非空
        if not _nonempty(c.get("source_node")):
            v.append({"case_id": cid, "check": "source_node_nonempty",
                      "detail": "三要素缺失：source_node 为空或未填"})
        if not _nonempty(c.get("source_branch")):
            v.append({"case_id": cid, "check": "source_branch_nonempty",
                      "detail": "三要素缺失：source_branch 为空或未填"})
        tm = c.get("test_methods")
        if not _nonempty(tm):
            v.append({"case_id": cid, "check": "test_methods_nonempty",
                      "detail": "三要素缺失：test_methods 为空或未填"})
        elif not isinstance(tm, list) or not set(tm) <= VALID_METHODS:
            bad = sorted(set(tm) - VALID_METHODS) if isinstance(tm, list) else tm
            v.append({"case_id": cid, "check": "test_methods_valid",
                      "detail": f"test_methods 含非法取值 {bad}，合法集 {sorted(VALID_METHODS)}"})

        # 4. scene_type 枚举
        st = c.get("scene_type")
        if st is not None and st not in SCENE_TYPES:
            v.append({"case_id": cid, "check": "scene_type_enum",
                      "detail": f"scene_type={st!r} 不在 7 类枚举 {sorted(SCENE_TYPES)}"})

        # 5. source_branch == scene_type
        if st is not None and c.get("source_branch") != st:
            v.append({"case_id": cid, "check": "source_branch_eq_scene_type",
                      "detail": f"source_branch={c.get('source_branch')!r} != scene_type={st!r}"})

        # 6. expected 非空（含 expected/request 字段的用例）
        if "expected" in c or "request" in c:
            if not _nonempty(c.get("expected")):
                v.append({"case_id": cid, "check": "expected_nonempty",
                          "detail": "expected 为空或缺失（期望空泛的弱断言用例不计入覆盖）"})

        # 7. 异步禁 smoke：含 steps_desc 的异步用例 smoke 必须为 false
        if _nonempty(c.get("steps_desc")) and c.get("smoke") is True:
            v.append({"case_id": cid, "check": "async_no_smoke",
                      "detail": "异步用例（含 steps_desc）禁止标 smoke: true（冒烟求快，异步天然慢）"})

        # 8. mock_injected ⇒ service_error
        if c.get("mock_injected") is True and c.get("scene_type") != "service_error":
            v.append({"case_id": cid, "check": "mock_implies_service_error",
                      "detail": f"mock_injected=true 但 scene_type={c.get('scene_type')!r}，"
                                f"mock 用例仅允许出现在 service_error 场景"})

        # 9 配对计数：收集确认/取消分支基名
        name = case_name_of(c)
        for tag, bucket in (("确认分支", confirm_bases), ("取消分支", cancel_bases)):
            if tag in name:
                base = name.replace(tag, "").rstrip("-— ")
                bucket.setdefault(base, []).append(cid)

    # 9. 确认/取消成对（按 case_name 配对计数）
    for base, ids in confirm_bases.items():
        if base not in cancel_bases:
            v.append({"case_id": ids[0], "check": "confirm_cancel_pair",
                      "detail": f"确认分支用例 {ids} 无配对取消分支（基名 {base!r}）"})
    for base, ids in cancel_bases.items():
        if base not in confirm_bases:
            v.append({"case_id": ids[0], "check": "confirm_cancel_pair",
                      "detail": f"取消分支用例 {ids} 无配对确认分支（基名 {base!r}）"})

    # ---- file-level 校验 ----

    # 10. smoke 标记数 ∈ [5,8]
    smoke_ids = [case_label(c, i) for i, c in enumerate(cases) if c.get("smoke") is True]
    v_smoke = len(smoke_ids)
    if not (SMOKE_MIN <= v_smoke <= SMOKE_MAX):
        v.append({"case_id": FILE, "check": "smoke_count_range",
                  "detail": f"smoke 标记数={v_smoke}，不在 [{SMOKE_MIN},{SMOKE_MAX}] 区间"
                            f"（标记用例: {smoke_ids}）"})

    # 11. 7 类测试点方法全覆盖
    used = set()
    for c in cases:
        tm = c.get("test_methods")
        if isinstance(tm, list):
            used |= set(tm)
    missing = sorted(VALID_METHODS - used)
    if missing:
        v.append({"case_id": FILE, "check": "method_coverage_7",
                  "detail": f"7 类测试点方法未全覆盖，缺失: {missing}（已用: {sorted(used & VALID_METHODS)}）"})

    # 12. module 三级与契约逐字一致
    if schema_modules is not None:
        for i, c in enumerate(cases):
            cid = case_label(c, i)
            m = c.get("module")
            if m is None:
                continue  # 非 api 用例无 module，跳过
            if not isinstance(m, dict) or not all(_nonempty(m.get(k)) for k in ("major", "minor", "feature")):
                v.append({"case_id": cid, "check": "module_schema_match",
                          "detail": f"module 三级不完整: {m!r}（需 major/minor/feature 全非空）"})
                continue
            key = (m["major"], m["minor"], m["feature"])
            if key not in schema_modules:
                v.append({"case_id": cid, "check": "module_schema_match",
                          "detail": f"module {key} 与 .api-schema.json endpoints[].module 无逐字一致项"})
    return v


def main():
    ap = argparse.ArgumentParser(description="test-case-designer Step5 自检清单机械化校验器（纯 stdlib）")
    ap.add_argument("--cases", required=True, help="用例 JSON 路径（execution-list.json / .api-test-cases.json）")
    ap.add_argument("--schema", default=None, help=".api-schema.json 路径（提供时校验 module 三级逐字一致）")
    args = ap.parse_args()

    cases, err = load_cases(args.cases)
    if err:
        json.dump({"pass": False, "error": err}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        sys.exit(2)

    schema_modules = None
    if args.schema:
        schema_modules, err = load_schema_modules(args.schema)
        if err:
            json.dump({"pass": False, "error": err}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            sys.exit(2)

    violations = run_checks(cases, schema_modules)
    result = {
        "pass": not violations,
        "total_cases": len(cases),
        "checks": [
            "source_node_nonempty", "source_branch_nonempty",
            "test_methods_nonempty", "test_methods_valid",
            "scene_type_enum", "source_branch_eq_scene_type",
            "expected_nonempty", "async_no_smoke",
            "mock_implies_service_error", "confirm_cancel_pair",
            "smoke_count_range", "method_coverage_7",
        ] + (["module_schema_match"] if schema_modules is not None else []),
        "violations": violations,
        "semantic_deferred": SEMANTIC_DEFERRED,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
