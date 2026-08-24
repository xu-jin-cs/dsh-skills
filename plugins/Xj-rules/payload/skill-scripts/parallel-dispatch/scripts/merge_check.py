#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_check.py — parallel-dispatch 三槽契约 SLOT-MERGE 机械校验（2026-08-16 REFORM-GATE item2）

四道合并校验中可机械化的两道：
  a) 文件级冲突：--manifest f1.json f2.json ...（每份含 agent 名与 changed_files 数组），
     两分身改同一文件即冲突判 1，列出冲突文件与涉事分身。
  b) 产物完整性：--expect <清单文件>（一行一个绝对路径，# 开头为注释），
     全部真实存在否则判 1 并列差集。

留软层（自杀开关：纯语义不造门）：
  ②契约级冲突（接口/Schema 不一致）与 ③数据格式级冲突依赖语义判断，
  本脚本明确不做，由母体按 SKILL.md 第六节软层人工校验，禁止伪造机械结论。

退出码：0 = 合格  1 = 不合格（列出全部违例）  2 = 用法错误

用法：
  python3 merge_check.py --manifest a.json b.json
  python3 merge_check.py --expect /path/to/expect.txt
  python3 merge_check.py --manifest a.json b.json --expect expect.txt   # 两道一次过

manifest 格式：{"agent": "<分身名>", "changed_files": ["<绝对路径>", ...]}
（files 字段名亦兼容；agent 缺省时回退为文件名）
"""
import argparse
import json
import os
import sys


def load_manifest(path):
    """返回 (agent名, 文件集合)；解析失败抛 ValueError。"""
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"manifest 解析失败 {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"manifest 不是 JSON 对象: {path}")
    agent = data.get("agent") or os.path.basename(path)
    files = data.get("changed_files", data.get("files"))
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise ValueError(f"manifest changed_files 缺失或不是字符串数组: {path}")
    return agent, files


def check_conflicts(manifest_paths):
    """文件级冲突：返回违例清单。"""
    violations = []
    owners = {}  # file -> [agent, ...]
    for p in manifest_paths:
        agent, files = load_manifest(p)
        for f in files:
            owners.setdefault(f, []).append(agent)
    for f, agents in sorted(owners.items()):
        if len(agents) > 1:
            violations.append(f"文件级冲突: {f} 被多个分身修改: {agents}")
    return violations


def check_expect(expect_path):
    """产物完整性：返回违例清单。"""
    if not os.path.isfile(expect_path):
        return [f"expect 清单不存在: {expect_path}"]
    missing = []
    for line in open(expect_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not os.path.exists(line):
            missing.append(line)
    if missing:
        return [f"产物缺失（差集 {len(missing)} 项）: {m}" for m in missing]
    return []


def main():
    ap = argparse.ArgumentParser(description="SLOT-MERGE 合并机械校验（文件级冲突 + 产物完整性）")
    ap.add_argument("--manifest", nargs="+", default=None,
                    help="各分身 changed_files 清单 JSON（≥1 份）")
    ap.add_argument("--expect", default=None,
                    help="期望产物清单文件（一行一个绝对路径）")
    args = ap.parse_args()

    if not args.manifest and not args.expect:
        ap.error("至少给 --manifest 或 --expect 之一")

    violations = []
    try:
        if args.manifest:
            violations += check_conflicts(args.manifest)
        if args.expect:
            violations += check_expect(args.expect)
    except ValueError as e:
        print(f"[merge_check] FAIL: {e}")
        sys.exit(1)

    if violations:
        print("[merge_check] FAIL: MERGE 校验违例：")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    print("[merge_check] PASS: 文件级冲突差集为空 + 产物完整性满足"
          "（契约级/语义级冲突留软层，母体人工校验）")
    sys.exit(0)


if __name__ == "__main__":
    main()
