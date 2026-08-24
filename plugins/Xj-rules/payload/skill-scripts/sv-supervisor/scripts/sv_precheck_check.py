#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sv_precheck_check.py — sv-supervisor 步骤切换前置校验（五项）机械闸
（gate-switch spec: sv_precheck.json 的 script_exit 被包装脚本，2026-08-16 D 域批量开关化，
 合并 SKILL.md 6.3 前置校验规则 + 6.4 项目前置输入文件哈希校验规范两处）

前置五项（对齐 SKILL.md 6.3 原文）：
  ① .flow_state.json 存在且合法（可解析、含 status/step）
  ② 当前步骤交付物齐全：deliverables[] 每条 file/path 存在 + sha256/hash 匹配
     （无 deliverables 字段 → SKIP；有条目但缺 hash 字段 → 违例，无法机械校验即缺斤短两）
  ③ sv_verdict.current == APPROVED（兼容字符串形态 sv_verdict == "APPROVED"）
  ④ 违规积分 < 3（violation_points 数值，或 violations[] 长度；缺省按 0）
  ⑤ 项目前置输入合规（仅当 project_input.project_input_completed 字段存在时执行，对齐 6.3 触发条件）：
     project_input_completed === true；.prd.md 与 .ui-proto.json 存在且
     SHA256 与 project_input.input_files_hashes 逐一匹配（键兼容 prd/ui_proto 与文件名形态）；
     project_input.input_files 声明清单与实际文件一致

退出码：0=全过（SKIP 不计失败） / 2=有违例 / 3=参数错误。纯 stdlib。
"""
import argparse
import hashlib
import json
import os
import sys


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="sv-supervisor 前置五项机械校验")
    ap.add_argument("--project", required=True, help="项目根（含 .flow_state.json）")
    args = ap.parse_args()
    root = args.project
    fs_path = os.path.join(root, ".flow_state.json")

    violations, notes = [], []

    # ① .flow_state.json 存在且合法
    if not os.path.isfile(fs_path):
        print(f"[sv_precheck] VIOLATION ① .flow_state.json 不存在: {fs_path}")
        print("[sv_precheck] FAIL 违例 1 项")
        sys.exit(2)
    try:
        fs = json.load(open(fs_path, encoding="utf-8"))
        assert isinstance(fs, dict)
    except Exception as e:
        print(f"[sv_precheck] VIOLATION ① .flow_state.json 解析失败: {e}")
        print("[sv_precheck] FAIL 违例 1 项")
        sys.exit(2)
    if "status" in fs or "step" in fs:
        print("[sv_precheck] PASS ① .flow_state.json 存在且合法")
    else:
        violations.append("① .flow_state.json 缺 status/step 关键字段")

    # ② 交付物齐全（存在 + hash 匹配）
    dl = fs.get("deliverables")
    if not dl:
        notes.append("② deliverables[] 缺省，SKIP（无交付物声明）")
    else:
        for i, d in enumerate(dl):
            if not isinstance(d, dict):
                violations.append(f"② deliverables[{i}] 非对象，无法校验")
                continue
            rel = d.get("file") or d.get("path") or d.get("artifact_path")
            expect = d.get("sha256") or d.get("hash")
            if not rel:
                violations.append(f"② deliverables[{i}] 缺 file/path 字段")
                continue
            fp = rel if os.path.isabs(rel) else os.path.join(root, rel)
            if not os.path.isfile(fp):
                violations.append(f"② 交付物缺失: {rel}")
                continue
            if not expect:
                violations.append(f"② deliverables[{i}] {rel} 缺 sha256/hash 字段，无法机械校验")
                continue
            actual = sha256_of(fp)
            if actual != expect:
                violations.append(f"② 交付物 hash 不匹配: {rel}"
                                  f"（declared={expect[:12]}… actual={actual[:12]}…）")
        if not any(v.startswith("②") for v in violations):
            print(f"[sv_precheck] PASS ② 交付物 {len(dl)} 件存在且 hash 匹配")

    # ③ sv_verdict == APPROVED
    verdict = fs.get("sv_verdict")
    cur = verdict.get("current") if isinstance(verdict, dict) else verdict
    if cur == "APPROVED":
        print("[sv_precheck] PASS ③ sv_verdict == APPROVED")
    else:
        violations.append(f"③ sv_verdict={cur!r} ≠ APPROVED")

    # ④ 违规积分 < 3
    pts = fs.get("violation_points")
    if pts is None:
        v = fs.get("violations")
        pts = len(v) if isinstance(v, list) else 0
    if isinstance(pts, (int, float)) and pts < 3:
        print(f"[sv_precheck] PASS ④ 违规积分 {pts} < 3")
    else:
        violations.append(f"④ 违规积分 {pts} ≥ 3（熔断阈值）")

    # ⑤ 项目前置输入（含 6.4 SHA256 比对）
    pi = fs.get("project_input")
    if not isinstance(pi, dict) or "project_input_completed" not in pi:
        notes.append("⑤ 无 project_input.project_input_completed 字段，SKIP（无项目路径，对齐触发条件）")
    else:
        if pi.get("project_input_completed") is not True:
            violations.append("⑤ project_input_completed ≠ true（前置项目输入未齐备，"
                              "需补齐 .prd.md + .ui-proto.json）")
        else:
            hashes = pi.get("input_files_hashes") or {}
            targets = {".prd.md": ["prd", ".prd.md"],
                       ".ui-proto.json": ["ui_proto", ".ui-proto.json"]}
            for fname, keys in targets.items():
                fp = os.path.join(root, fname)
                if not os.path.isfile(fp):
                    violations.append(f"⑤ {fname} 缺失")
                    continue
                expect = next((hashes[k] for k in keys if k in hashes), None)
                if not expect:
                    violations.append(f"⑤ input_files_hashes 缺 {fname} 的哈希记录")
                    continue
                actual = sha256_of(fp)
                if actual != expect:
                    violations.append(f"⑤ {fname} SHA256 不匹配（被篡改或未同步）:"
                                      f" declared={expect[:12]}… actual={actual[:12]}…")
            declared = pi.get("input_files")
            if isinstance(declared, list):
                for rel in declared:
                    fp = rel if os.path.isabs(rel) else os.path.join(root, rel)
                    if not os.path.isfile(fp):
                        violations.append(f"⑤ input_files 声明文件缺失: {rel}")
            if not any(v.startswith("⑤") for v in violations):
                print("[sv_precheck] PASS ⑤ .prd.md/.ui-proto.json SHA256 与批次记录一致")

    for n in notes:
        print(f"[sv_precheck] NOTE {n}")
    if violations:
        for v in violations:
            print(f"[sv_precheck] VIOLATION {v}")
        print(f"[sv_precheck] FAIL 违例 {len(violations)} 项")
        sys.exit(2)
    print("[sv_precheck] PASS 前置五项全过（SKIP 项见 NOTE）")
    sys.exit(0)


if __name__ == "__main__":
    main()
