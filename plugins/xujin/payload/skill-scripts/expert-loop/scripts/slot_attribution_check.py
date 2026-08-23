#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slot_attribution_check.py — SLOT 回链闸校验器（gate-switch 生态型薄壳）

裁决铁律「裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾」
的机械核验层：核验项目产物目录中存在含该 expert_id 的回链落盘条目。

判定边界（软层纪律）：
  - 本脚本只判【回链落盘证据存在性】（L2 机械可判：有/无含 expert_id 的条目）。
  - 【落实质量】（改动是否真的落实了建议、写得好不好）为纯语义判断，
    按裁定留软层由母体人工校验，本脚本不判、禁止伪造机械结论。

用法：
  python3 slot_attribution_check.py --project <项目根> --expert-id <如 A04-E13>
  python3 slot_attribution_check.py --project <项目根> --advice-ref <建议卡引用>

退出码：0=命中（回链已落盘）/ 1=未命中（列出期望路径，violations 即修复指令）/ 2=入参非法。
纯 stdlib。
"""
import argparse
import glob
import json
import os
import sys

# 回链落盘文件候选路径（有序，先 expert-loop 宿主约定，后 archmap 风格）。
# internalizations.jsonl：SLOT-2 内化记录（含 source_expert 回链字段）；
# expert_advice.jsonl：SLOT-1 建议裁决记录（accepted 裁决 + expert_id）。
# 宿主另有产物目录约定的从其约定——候选用 glob 兜底 *internalizations.jsonl。
CANDIDATE_PATTERNS = [
    "{project}/.expert-loop/internalizations.jsonl",
    "{project}/.expert-loop/*internalizations.jsonl",
    "{project}/.expert-loop/*expert_advice.jsonl",
    "{project}/archmap/internalizations.jsonl",
    "{project}/archmap/*internalizations.jsonl",
    "{project}/archmap/*expert_advice.jsonl",
]

# 条目中可能承载 expert_id 回链的字段名（协议 v1.1+ 以 source_expert 为准，
# 兼容 expert_id / expert / accepted_by 等历史与宿主变体）。
EXPERT_ID_FIELDS = ["expert_id", "source_expert", "expert", "accepted_by"]

# --advice-ref 解析时，在建议卡中匹配引用值的字段。
ADVICE_REF_FIELDS = ["advice_ref", "ref", "id", "task_ref"]


def candidate_files(project):
    """按候选顺序展开为真实存在的文件清单（去重保序）。"""
    seen, files = set(), []
    for pat in CANDIDATE_PATTERNS:
        for p in sorted(glob.glob(pat.format(project=project))):
            rp = os.path.realpath(p)
            if rp not in seen and os.path.isfile(rp):
                seen.add(rp)
                files.append(rp)
    return files


def iter_entries(path):
    """逐行 JSON 解析；坏行跳过（不判语法质量，只找回链证据）。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                yield obj


def entry_has_expert(obj, expert_id):
    """条目的任一专家字段等于目标 expert_id 即命中（精确等值，不模糊子串）。"""
    for field in EXPERT_ID_FIELDS:
        if obj.get(field) == expert_id:
            return True
    return False


def resolve_advice_ref(project, advice_ref):
    """从 expert_advice.jsonl 候选中按引用字段反查 expert_id；查不到则把
    advice_ref 本身当 expert_id 用（引用与专家同形的场景兜底）。"""
    for path in candidate_files(project):
        if "expert_advice" not in os.path.basename(path):
            continue
        for obj in iter_entries(path):
            if any(obj.get(f) == advice_ref for f in ADVICE_REF_FIELDS):
                for f in EXPERT_ID_FIELDS:
                    if obj.get(f):
                        return obj[f]
    return advice_ref


def main():
    ap = argparse.ArgumentParser(description="SLOT 回链闸：核验 expert_id 回链落盘条目存在性")
    ap.add_argument("--project", required=True, help="项目根目录")
    ap.add_argument("--expert-id", help="专家 ID（如 A04-E13）")
    ap.add_argument("--advice-ref", help="建议卡引用（自动反查 expert_id）")
    args = ap.parse_args()

    if not args.expert_id and not args.advice_ref:
        print("❌ 入参非法：必须给 --expert-id 或 --advice-ref 之一", file=sys.stderr)
        return 2
    if not os.path.isdir(args.project):
        print(f"❌ 项目根不存在: {args.project}", file=sys.stderr)
        return 2

    expert_id = args.expert_id or resolve_advice_ref(args.project, args.advice_ref)
    files = candidate_files(args.project)
    if not files:
        print("❌ 未命中：项目下无任何回链落盘文件。期望路径候选（按序）：")
        for pat in CANDIDATE_PATTERNS:
            print(f"   - {pat.format(project=args.project)}")
        print("修复指令：accepted 建议必须落实改动并回链 expert_id 落盘后再收尾。")
        return 1

    for path in files:
        for obj in iter_entries(path):
            if entry_has_expert(obj, expert_id):
                print(f"✅ 命中：{path} 存在含 expert_id={expert_id} 的回链条目"
                      f"（skill={obj.get('skill_name', '-')}）")
                print("边界提示：本闸只判回链落盘存在性；落实质量留软层人工校验。")
                return 0

    print(f"❌ 未命中：以下落盘文件中均无含 expert_id={expert_id} 的条目：")
    for path in files:
        print(f"   - {path}")
    print("修复指令：accepted 建议必须落实改动并回链 expert_id 落盘后再收尾（不归因不收尾）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
