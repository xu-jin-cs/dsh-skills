#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whitebox_scope_switch.py — 白盒增量回归「范围圈定」单刀双掷开关（2026-08-16 用户裁定）

治的软点：SKILL.md 文本禁令「禁止凭 git status/人工判断圈定范围」无牙——Agent 跳过
archmap diff 直接凭 git status 圈范围，跨文件影响闭包全丢。本开关把判定权从模型移交脚本：
  掷点 A（exit 0）：diff_impact.json 存在+mode=diff+不陈旧 → 机械输出权威范围照抄块
  掷点 B（exit 1）：缺失/非 diff/陈旧 → violations 即修复指令（先跑 archmap diff）
模型只照抄，禁止手写范围。

新鲜度判据：diff_impact.computed_at >= 项目内最新源码文件 mtime
（源码=白名单扩展名；排除 .git/node_modules/archmap/evidence 等噪声目录）。
由 gate_switch.py 以 script_exit 原语包装（spec: whitebox_scope.json，expect 0）。
"""
import argparse
import datetime
import json
import os
import sys

_SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", "archmap",
              "evidence", ".venv", "venv", "coverage", ".next", "target"}
_SRC_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".java", ".go", ".rs",
            ".sql", ".sh", ".html", ".css"}


def latest_code_mtime(project):
    """项目内最新源码文件 mtime（epoch 秒）；无源码文件返回 0。"""
    latest = 0.0
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if root.count(os.sep) - project.count(os.sep) > 8:
            dirs[:] = []
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in _SRC_EXT:
                continue
            try:
                m = os.path.getmtime(os.path.join(root, fn))
                if m > latest:
                    latest = m
            except OSError:
                continue
    return latest


def fail(violations):
    for v in violations:
        print(f"VIOLATION: {v}")
    # script_exit 原语只取 stdout 末行作 B 档理由 → 末行必须是全量违例汇总
    print(f"VIOLATIONS({len(violations)}): " + " ｜ ".join(violations))
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="白盒增量回归范围圈定单刀双掷开关")
    ap.add_argument("--project", required=True, help="目标工程根目录")
    ap.add_argument("--src", default="src", help="覆盖率目标目录名（默认 src，按项目实际传）")
    args = ap.parse_args()

    target = os.path.join(args.project, "archmap", "diff_impact.json")
    violations = []
    data = None

    if not os.path.isfile(target):
        violations.append(
            f"diff_impact.json 不存在: {target}——必须先执行 "
            f"`python3 ~/.dsh/xujin-scripts/skills/archmap/archmap {args.project} diff [修改备注]` 产出影响面，"
            "禁止凭 git status/人工判断圈定范围")
    else:
        try:
            data = json.load(open(target))
        except (json.JSONDecodeError, OSError) as e:
            violations.append(f"diff_impact.json 不可解析: {e}——重跑 archmap diff 重新产出")

    if data is not None and not violations:
        if data.get("mode") != "diff" or data.get("status") != "ok":
            violations.append(
                f"diff_impact.json 状态非法: mode={data.get('mode')} status={data.get('status')}"
                "——重跑 archmap diff 产出合法影响面")
        else:
            computed_at = datetime.datetime.fromisoformat(
                data["computed_at"]).timestamp()
            latest = latest_code_mtime(args.project)
            if latest > computed_at:
                violations.append(
                    "diff_impact.json 陈旧于代码变更: "
                    f"computed_at={data['computed_at']} < 最新源码变更="
                    f"{datetime.datetime.fromtimestamp(latest).isoformat(timespec='seconds')}"
                    "——代码在 diff 之后又改过，必须先重跑 archmap diff 再圈范围")

    if violations:
        fail(violations)

    stats = data.get("stats", {})
    if stats.get("changed_files", 0) == 0 and not data.get("changed_files"):
        print("OK: 无代码变更，免测——本工作期源码零变更，增量回归不适用")
        sys.exit(0)

    sel = data.get("test_selection", {})
    selected = sel.get("selected", [])
    untested = sel.get("untested_changes", [])
    deleted = data.get("deleted_files", [])

    # 掷点 A：机械输出权威范围照抄块
    print("━━ 范围圈定照抄块（判定权在脚本，禁止手写增删） ━━")
    print(f"AFFECTED_CLOSURE({len(data.get('affected_closure', []))}): "
          + json.dumps(data.get("affected_closure", []), ensure_ascii=False))
    print(f"SCOPE_SELECTED({len(selected)}): " + json.dumps(selected, ensure_ascii=False))
    if untested:
        print(f"SCOPE_UNTESTED_CHANGES({len(untested)}): " + json.dumps(untested, ensure_ascii=False)
              + " —— 必须为无测试变更文件先补用例再执行（阻断级）")
    if deleted:
        print(f"DELETED_FILES({len(deleted)}): " + json.dumps(deleted, ensure_ascii=False)
              + " —— 归一化已从分母剔除")
    if selected:
        print("SCOPE_CMD: python3 -m coverage run --branch --source=" + args.src
              + " -m pytest " + " ".join(selected)
              + " && python3 -m coverage json -o evidence/tdd/coverage_raw_diff.json")
    print(f"OK: 范围圈定照抄 diff_impact.json（受影响测试 {len(selected)} 个，"
          f"无测试变更 {len(untested)} 个，影响闭包 {len(data.get('affected_closure', []))} 个）")
    sys.exit(0)


if __name__ == "__main__":
    main()
