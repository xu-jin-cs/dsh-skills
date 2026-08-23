#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scope_diff_check.py — 范围边界机械拦截器（SV-GATE-001 重生版，2026-08-15）

旧 YAML 版靠文本关键词"超出PRD范围"（从未执行）；重生版用集合运算：
git 变更文件集 − 范围白名单（task-breakdown/PRD 声明的范围文件清单）− 例外白名单 = 越界清单。

判定：
  越界为空 → exit 0（A：范围内）
  越界非空 → exit 1（B：阻断提交，列出越界文件，须 PM 确认或删除——"即使代码已写也要删掉"）

例外白名单（对应 SKILL.md「IDE 自动生成的配置/类型声明」）：
  *.d.ts / *.config.* / tsconfig*.json / .idea/** / .vscode/** / *.iml

用法：
  scope_diff_check.py --repo <git仓库> --allow <范围清单文件> [--base <git基线，默认HEAD>]
  范围清单格式：每行一个路径（相对 repo 根），或以 / 结尾的目录前缀；JSON 数组亦可。
"""
import argparse
import fnmatch
import json
import os
import subprocess
import sys

WHITELIST = ["*.d.ts", "*.config.*", "tsconfig*.json", ".idea/*", ".vscode/*", "*.iml"]


def git_changed(repo, base):
    def run(*args):
        r = subprocess.run(["git", "-C", repo] + list(args),
                           capture_output=True, text=True)
        return r.stdout.splitlines() if r.returncode == 0 else []
    changed = set(run("diff", "--name-only", base))
    changed |= set(run("diff", "--name-only", "--cached", base))
    changed |= set(run("ls-files", "--others", "--exclude-standard"))
    return {c for c in changed if c}


def load_allow(path):
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):
        return [x for x in json.loads(text) if isinstance(x, str)]
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def allowed(f, allow_set):
    for a in allow_set:
        if a.endswith("/") and f.startswith(a):
            return True
        if f == a or fnmatch.fnmatch(f, a):
            return True
    return False


def whitelisted(f):
    return any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch(os.path.basename(f), p)
               for p in WHITELIST)


def main():
    ap = argparse.ArgumentParser(description="范围边界机械拦截器（git diff vs 范围清单集合运算）")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--allow", required=True, help="范围文件清单（每行一个路径或 JSON 数组）")
    ap.add_argument("--base", default="HEAD")
    args = ap.parse_args()

    if not os.path.isdir(os.path.join(args.repo, ".git")):
        out = {"pass": False, "violations": [f"非 git 仓库: {args.repo}"]}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)
    if not os.path.isfile(args.allow):
        out = {"pass": False, "violations": [f"范围清单不存在: {args.allow}（task-breakdown 需先产出范围文件清单）"]}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    allow_set = load_allow(args.allow)
    changed = git_changed(args.repo, args.base)
    out_of_scope = sorted(f for f in changed
                          if not allowed(f, allow_set) and not whitelisted(f))

    ok = not out_of_scope
    result = {
        "pass": ok,
        "changed_count": len(changed),
        "allow_count": len(allow_set),
        "out_of_scope": out_of_scope,
        "violations": ([] if ok else
                       [f"越界文件 {len(out_of_scope)} 个（不在范围清单且非例外白名单）: "
                        + ", ".join(out_of_scope)]),
    }
    # 单行 JSON：gate_switch script_exit 取末行作 B 档违例详情
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
