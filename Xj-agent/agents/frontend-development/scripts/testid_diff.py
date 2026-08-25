#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
testid_diff.py — frontend data-testid 锚点集合差机械检查器（2026-08-15 裁定，gate-switch 实证族配套）

拆解"声称全注入实际漏组件"事故：把 .ui-proto.json 可交互组件 id 集合与源码中
实际注入的 data-testid 值集合做差集，proto 有而源码无 → 未交付。

用法：
  testid_diff.py --src <前端源码目录> --proto <.ui-proto.json路径>

逻辑：
  - 源码侧：递归扫描 .js/.jsx/.ts/.tsx/.vue/.svelte/.html，正则提取全部
    data-testid="..." / '...' / {...} 字面量值集合。
  - proto 侧：递归遍历 JSON，凡 dict 含字符串 id 且（type ∈ 可交互类型白名单
    或 interactive 为真）→ 计入可交互组件 id 集合（按 proto 实际结构自适应，
    不假设层级路径）。
  - missing = proto_ids - src_ids；非空 → exit 1 输出 missing 清单；空 → exit 0。

输出 JSON {pass, checks[{name, ok, detail}], violations, missing, counts}。纯 stdlib。
"""
import argparse
import json
import os
import re
import sys

SRC_EXTS = (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html")

# 可交互组件类型白名单（小写比较；按 proto 实际取值自适应扩充的安全集）
INTERACTIVE_TYPES = {
    "button", "input", "select", "textarea", "checkbox", "radio", "switch",
    "slider", "modal-trigger", "modal_trigger", "trigger", "link", "dropdown",
    "tab", "menu-item", "menu_item", "form", "date-picker", "date_picker",
    "upload", "search", "pagination", "stepper", "toggle",
}

TESTID_RE = re.compile(
    r"""data-testid\s*=\s*(?:"([^"]+)"|'([^']+)'|\{\s*"([^"]+)"\s*\}|\{\s*'([^']+)'\s*\})""")


def collect_src_testids(src_dir):
    ids, files = set(), 0
    for root, _dirs, names in os.walk(src_dir):
        for n in names:
            if not n.lower().endswith(SRC_EXTS):
                continue
            p = os.path.join(root, n)
            try:
                text = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            files += 1
            for m in TESTID_RE.finditer(text):
                ids.add(next(g for g in m.groups() if g is not None))
    return ids, files


def collect_proto_ids(node, out):
    """递归遍历 JSON，自适应提取可交互组件 id。"""
    if isinstance(node, dict):
        cid = node.get("id")
        if isinstance(cid, str) and cid:
            ctype = node.get("type")
            interactive = node.get("interactive")
            if (isinstance(ctype, str) and ctype.lower() in INTERACTIVE_TYPES) \
                    or interactive is True:
                out.add(cid)
        for v in node.values():
            collect_proto_ids(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_proto_ids(v, out)


def main():
    ap = argparse.ArgumentParser(description="data-testid 锚点集合差机械检查器")
    ap.add_argument("--src", required=True, help="前端源码目录")
    ap.add_argument("--proto", required=True, help=".ui-proto.json 路径")
    args = ap.parse_args()

    checks, violations = [], []

    def rec(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            violations.append(f"{name}: {detail}")

    if not os.path.isdir(args.src):
        rec("src_exists", False, f"{args.src} 不是目录")
        return finish(checks, violations, [], {})
    rec("src_exists", True, args.src)
    if not os.path.isfile(args.proto):
        rec("proto_exists", False, f"{args.proto} 不存在")
        return finish(checks, violations, [], {})
    rec("proto_exists", True, args.proto)

    try:
        proto = json.load(open(args.proto, encoding="utf-8"))
    except Exception as e:
        rec("proto_parse", False, f"JSON 解析失败: {e}")
        return finish(checks, violations, [], {})
    rec("proto_parse", True, "解析成功")

    src_ids, n_files = collect_src_testids(args.src)
    proto_ids = set()
    collect_proto_ids(proto, proto_ids)
    rec("proto_ids", bool(proto_ids),
        f"可交互组件 id {len(proto_ids)} 个" if proto_ids else "proto 中未识别到任何可交互组件 id")

    missing = sorted(proto_ids - src_ids)
    extra = sorted(src_ids - proto_ids)
    rec("testid_coverage", not missing,
        "proto 可交互组件锚点全部注入" if not missing
        else f"{len(missing)} 个组件未注入 data-testid: {', '.join(missing)}")

    counts = {"src_files": n_files, "src_testids": len(src_ids),
              "proto_interactive_ids": len(proto_ids),
              "missing": len(missing), "extra_in_src": len(extra)}
    return finish(checks, violations, missing, counts)


def finish(checks, violations, missing, counts):
    ok = not violations
    json.dump({"pass": ok, "checks": checks, "violations": violations,
               "missing": missing, "counts": counts},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    # 末行单行摘要：gate_switch script_exit 原语取末行作 B 档违例详情
    summary = {"pass": ok, "violations": violations, "missing": missing} if not ok else {"pass": ok}
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
