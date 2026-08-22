#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_sync_check.py — 技能发布同步事前闸（2026-08-17 存量清算落地）

铁律（~/.dsh/AGENTS.md 技能调用规范节）：对外分发技能真源在 ~/dsh-skills/ 仓库，
两个用户根（~/.dsh/skills/、~/.agents/skills/）必须是指向仓库的符号链接，
禁止双副本漂移；更新规则后须 git push。

一门三查（对仓库内每个技能）：
  P1 符号链接：~/.dsh/skills/<name> 与 ~/.agents/skills/<name> 均为符号链接
     且 readlink 指向 ~/dsh-skills/<name>（或仓库内该技能目录）；
  P2 仓库干净：git status --porcelain 为空（无未提交改动）；
  P3 无未推送：git rev-list @{u}..HEAD 计数为 0（无本地领先提交；无上游分支时报 WARNING 不判 B）。

退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 publish_sync_check.py
"""
import json
import os
import subprocess
import sys

REPO = os.path.expanduser("~/dsh-skills")
ROOTS = [os.path.expanduser("~/.dsh/skills"), os.path.expanduser("~/.agents/skills")]


def git(*args):
    return subprocess.run(["git", "-C", REPO] + list(args),
                          capture_output=True, text=True, timeout=60)


def main():
    violations, warnings = [], []

    if not os.path.isdir(REPO):
        print(json.dumps({"ok": False, "violations": [
            {"code": "P0-NO-REPO", "detail": f"发布仓库不存在: {REPO}"}]},
            ensure_ascii=False, indent=2))
        return 2

    # P1：符号链接指向（对仓库内每个含 SKILL.md 的技能目录）
    skills = sorted(
        d for d in os.listdir(REPO)
        if os.path.isfile(os.path.join(REPO, d, "SKILL.md"))
    )
    for name in skills:
        repo_dir = os.path.join(REPO, name)
        for root in ROOTS:
            link = os.path.join(root, name)
            if not os.path.islink(link):
                violations.append({"code": "P1-NOT-SYMLINK", "skill": name,
                                   "detail": f"{link} 不是符号链接（双副本漂移风险）"})
                continue
            target = os.path.realpath(link)
            if target != os.path.realpath(repo_dir):
                violations.append({"code": "P1-WRONG-TARGET", "skill": name,
                                   "detail": f"{link} 指向 {target}，应为 {repo_dir}"})

    # P2：仓库干净
    r = git("status", "--porcelain")
    dirty = [l for l in r.stdout.splitlines() if l.strip()]
    if dirty:
        violations.append({"code": "P2-REPO-DIRTY",
                           "detail": f"仓库有 {len(dirty)} 处未提交改动: {dirty[:5]}"})

    # P3：无未推送提交（无上游分支只警告）
    up = git("rev-parse", "--abbrev-ref", "@{u}")
    if up.returncode != 0:
        warnings.append({"code": "P3-NO-UPSTREAM", "detail": "当前分支无上游，跳过推送检查"})
    else:
        ahead = git("rev-list", "--count", "@{u}..HEAD").stdout.strip()
        if ahead != "0":
            violations.append({"code": "P3-UNPUSHED",
                               "detail": f"本地领先上游 {ahead} 个提交未 push"})

    out = {"ok": not violations, "repo": REPO, "skills_checked": skills,
           "violations": violations, "warnings": warnings}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        print(f"PUBLISH_SYNC_CHECK: FAIL count={len(violations)}")
        return 2
    print(f"PUBLISH_SYNC_CHECK: PASS skills={len(skills)} warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
