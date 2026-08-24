#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_fix_selfcheck.py — Bug 修复提交前开发自检最小校验器（gate-switch 配套，2026-08-16）

本源禁令：01b_flow_b_bugfix.md 流程B「Bug修复阶段强制自检（2026-07-11 新增）」——
修复提交前四项自检（导入验证/旧名零残留/依赖同步/配置文档同步），任意一项未通过
修复不能提交。治「开发口头声称自检通过但旧名残留/导入爆炸/requirements 未同步」。

参数化设计：四项机械可判项各对应一个参数组，给哪项查哪项（至少给一项）：
  --old-name <旧名> --paths "<路径1> <路径2> ..."
      旧名零残留：在 --paths 指定的文件/目录（目录递归，自动跳过 .git/
      __pycache__/node_modules/dist）内按字面量计数，命中 >0 即违例。
  --import-mod <模块> [--import-from <符号>] [--cwd <运行目录>]
      导入冒烟：python3 -c "import <模块>"（--import-from 给出时改
      "from <模块> import <符号>"），非 0 退出即违例。
  --requirements <requirements.txt 路径> --require-lib <库名>
      依赖同步：新引入的库名必须已在 requirements.txt 中出现（按行匹配
      包名，忽略版本钉 ==/>= 后缀与注释行）。
  --doc <文档路径> --doc-keyword <关键词>
      配置文档同步：配置变更对应的关键词必须在文档中出现 ≥1 次。

退出码：0=全部给定项通过 / 1=有违例（stdout 末行全量汇总供 script_exit 取尾行）。
由 gate_switch.py 以 script_exit 原语包装（expect 0）。纯 stdlib。
"""
import argparse
import os
import re
import subprocess
import sys

_SKIP_DIRS = {".git", "__pycache__", "node_modules", "dist", "build", ".venv", "venv"}


def check_old_name(old_name, paths):
    """旧名在 paths 内字面出现次数；返回 (命中数, 明细列表)。"""
    hits, details = 0, []
    for raw in paths:
        p = raw.strip()
        if not p:
            continue
        if not os.path.exists(p):
            details.append(f"{p}（路径不存在）")
            continue
        if os.path.isfile(p):
            files = [p]
        else:
            files = []
            for r, ds, fs in os.walk(p):
                ds[:] = [d for d in ds if d not in _SKIP_DIRS]
                files.extend(os.path.join(r, f) for f in fs)
        for fp in files:
            try:
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    n = sum(line.count(old_name) for line in fh)
            except OSError:
                continue
            if n:
                hits += n
                details.append(f"{fp}×{n}")
    return hits, details


def check_import(mod, symbol, cwd):
    cmd = [sys.executable, "-c",
           f"from {mod} import {symbol}" if symbol else f"import {mod}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                       cwd=cwd or None)
    return r.returncode, (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]


def check_requirements(req_path, lib):
    if not os.path.isfile(req_path):
        return False, f"requirements 文件不存在: {req_path}"
    pat = re.compile(r"^\s*" + re.escape(lib) + r"\s*([=<>!~\[ ]|$)", re.IGNORECASE)
    for line in open(req_path, encoding="utf-8", errors="ignore"):
        s = line.strip()
        if s and not s.startswith("#") and pat.match(s):
            return True, ""
    return False, f"{lib} 未出现在 {req_path}（引入新库但未同步 requirements.txt）"


def check_doc_keyword(doc_path, keyword):
    if not os.path.isfile(doc_path):
        return False, f"文档不存在: {doc_path}"
    with open(doc_path, encoding="utf-8", errors="ignore") as fh:
        if keyword in fh.read():
            return True, ""
    return False, f"关键词 {keyword!r} 未出现在 {doc_path}（配置变更但文档未同步）"


def main():
    ap = argparse.ArgumentParser(description="Bug 修复提交前开发自检（旧名零残留/导入冒烟/依赖同步/文档同步）")
    ap.add_argument("--old-name", default="", help="改名前的旧函数/类/文件名（字面量）")
    ap.add_argument("--paths", default="", help="旧名扫描范围，空格分隔的文件/目录列表")
    ap.add_argument("--import-mod", default="", help="导入冒烟模块（如 backend.engine.kernel；旧 signer/orchestrator_gate/guards/validators 已随 2026-08-17 引擎替换删除）")
    ap.add_argument("--import-from", default="", help="按名导入的符号（给出时用 from X import Y）")
    ap.add_argument("--cwd", default="", help="导入冒烟运行目录（缺省当前目录）")
    ap.add_argument("--requirements", default="", help="requirements.txt 路径")
    ap.add_argument("--require-lib", default="", help="必须已入 requirements 的库名")
    ap.add_argument("--doc", default="", help="需同步的文档路径")
    ap.add_argument("--doc-keyword", default="", help="文档中必须出现的关键词")
    args = ap.parse_args()

    checks, violations = 0, []

    if args.old_name:
        checks += 1
        if not args.paths.strip():
            violations.append("--old-name 已给但 --paths 为空（无扫描范围，零残留无法实证）")
        else:
            hits, details = check_old_name(args.old_name, args.paths.split())
            if hits:
                violations.append(
                    f"旧名 {args.old_name!r} 残留 {hits} 处: {'，'.join(details[:5])}"
                    + (" …" if len(details) > 5 else ""))

    if args.import_mod:
        checks += 1
        code, tail = check_import(args.import_mod, args.import_from, args.cwd)
        if code != 0:
            violations.append(
                f"导入冒烟失败: {args.import_mod}"
                + (f" import {args.import_from}" if args.import_from else "")
                + f" exit={code} {tail[0]}")

    if args.require_lib:
        checks += 1
        if not args.requirements:
            violations.append("--require-lib 已给但 --requirements 为空")
        else:
            ok, why = check_requirements(args.requirements, args.require_lib)
            if not ok:
                violations.append(why)

    if args.doc_keyword:
        checks += 1
        if not args.doc:
            violations.append("--doc-keyword 已给但 --doc 为空")
        else:
            ok, why = check_doc_keyword(args.doc, args.doc_keyword)
            if not ok:
                violations.append(why)

    if checks == 0:
        print("VIOLATION: 未给出任何自检项（--old-name/--import-mod/--require-lib/--doc-keyword 至少一项），自检空转视同未自检")
        sys.exit(1)

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}")
        # script_exit 原语只取 stdout 末行作 B 档理由 → 末行必须是全量违例汇总
        print(f"VIOLATIONS({len(violations)}): " + " ｜ ".join(violations))
        sys.exit(1)
    print(f"OK: {checks} 项开发自检全部通过（旧名零残留/导入冒烟/依赖同步/文档同步按给定项核验）")
    sys.exit(0)


if __name__ == "__main__":
    main()
