"""真并行唯一判据（G5，2026-11-13）。

组成员互不依赖才算真并行：成员之间无直接依赖，也不存在某成员是另一成员的祖先。
调用方：engine/paradigm/team.py（detect_parallel）、engine/paradigm/gates.py（组校验）、
build/normalize_agent.py（范式判定）。禁止各处再写"成员≥2 即并行"。
"""
from __future__ import annotations


def _deps(nodes: list[dict]) -> dict[str, set[str]]:
    out = {}
    for n in nodes:
        nid = n.get("nodeId") or n.get("id")
        out[nid] = set(n.get("dependsOn") or n.get("depends_on") or [])
    return out


def true_parallel(nodes: list[dict], members: list[str]) -> bool:
    members = [m for m in members if m]
    if len(members) < 2:
        return False
    mset = set(members)
    dep = _deps(nodes)

    def ancestors(nid: str, seen: set[str]) -> set[str]:
        for d in dep.get(nid, ()):
            if d in seen:
                continue
            seen.add(d)
            ancestors(d, seen)
        return seen

    for m in members:
        if dep.get(m, set()) & mset:
            return False
    for a in members:
        for b in members:
            if a != b and a in ancestors(b, set()):
                return False
    return True
