#!/usr/bin/env python3
"""reform_layer_check.py — REFORM-GATE 层位一致性机械核验（2026-08-19 用户终裁落地）

针对事故：问题住数据/注册表层、方案全落工程执行层也能判 A（2026-08-19 闸插件治错方向事故）。

契约（gate_switch.py script_exit 原语，{block} 由 --set 注入 cmd）：
  python3 reform_layer_check.py <块文件>
  exit 0 = 层位相交（或不相交但有非空层位偏离理由，stdout 末行 WARNING）
  exit 2 = 缺必填字段 / 层位不相交且无偏离理由（stdout 末行为判 B 原因）

解析字段（行首允许 "- " 前缀，值尾部的（…）/(…) 批注剥离）：
  问题层位: <层位名，、或，分隔>
  方案层位: <同上，必填但判定以文件映射为准>
  改动文件清单:           （随后每行一个路径，空行或下一个字段行结束）
  层位偏离理由: <可选，非空则不相交时降级 WARNING 放行，理由质量留软层+复盘审计>
"""
import os
import re
import sys

HOME = os.path.expanduser("~")

# 层位映射表：路径前缀 → 层位（按特异性从高到低匹配，先中先得）
LAYER_TABLE = [
    (f"{HOME}/.agents/skills/gate-switch/specs/", "spec 层"),
    (f"{HOME}/.agents/rules/", "规则文本层"),
    (f"{HOME}/.agents/dsh-plugins/", "工程执行层"),
    (f"{HOME}/.npm/_npx/", "工程执行层"),          # dsh fork（npx node_modules）
    (f"{HOME}/agent-harness/backend/", "工程执行层"),
]

def layer_of(path):
    """路径 → 层位。skills 下 scripts/ 与 SKILL.md 用正则，注册表/账本按扩展名，兜底外部项目层。"""
    p = os.path.expanduser(path.strip())
    for prefix, layer in LAYER_TABLE:
        if p.startswith(prefix):
            return layer
    if re.match(rf"^{re.escape(HOME)}/\.agents/skills/[^/]+/scripts/", p):
        return "开关脚本层"
    if re.match(rf"^{re.escape(HOME)}/\.agents/skills/[^/]+/SKILL\.md$", p):
        return "技能定义层"
    if p.startswith(f"{HOME}/.agents/") and (p.endswith(".json") or p.endswith(".jsonl")):
        return "数据/注册表层"
    return "外部项目层"

def strip_note(value):
    """剥离线值尾部的（…）/(…) 批注。"""
    return re.sub(r"[（(].*?[）)]", "", value).strip()

def split_layers(value):
    """层位列表解析：只按 、/，/, 分隔（层位名本身含空格如 'spec 层'，禁按空格分）。"""
    return [s.strip() for s in re.split(r"[、，,]", strip_note(value)) if s.strip()]

def parse_block(text):
    fields = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*-?\s*(问题层位|方案层位|改动文件清单|层位偏离理由)\s*[:：]\s*(.*)$", lines[i])
        if m:
            key, value = m.group(1), m.group(2)
            if key == "改动文件清单":
                files = []
                if value.strip():
                    files.append(value.strip())
                i += 1
                while i < len(lines):
                    l = lines[i]
                    if l.strip() == "" or re.match(r"^\s*-?\s*[\u4e00-\u9fffA-Za-z#]+[:：#]", l) and not l.startswith((" ", "\t", "/")):
                        break
                    if l.strip().startswith(("/", "~")) or l.startswith((" ", "\t")):
                        cand = l.strip().lstrip("- ").strip()
                        if cand:
                            files.append(cand)
                    i += 1
                fields[key] = files
                continue
            fields[key] = value
        i += 1
    return fields

def main():
    if len(sys.argv) < 2:
        print("用法: reform_layer_check.py <块文件>")
        sys.exit(2)
    block_path = os.path.expanduser(sys.argv[1])
    if not os.path.isfile(block_path):
        print(f"块文件不存在: {block_path}")
        sys.exit(2)
    fields = parse_block(open(block_path, encoding="utf-8").read())

    missing = [k for k in ("问题层位", "方案层位", "改动文件清单")
               if k not in fields or (k == "改动文件清单" and not fields[k]) or (k != "改动文件清单" and not str(fields[k]).strip())]
    if missing:
        print(f"缺必填字段: {'、'.join(missing)}（REFORM-GATE v4 起 ①问题层位 ②方案层位+改动文件清单 为必填）")
        sys.exit(2)

    problem_layers = set(split_layers(fields["问题层位"]))
    derived = {}
    for f in fields["改动文件清单"]:
        derived.setdefault(layer_of(f), []).append(f)
    derived_set = set(derived)

    inter = derived_set & problem_layers
    if inter:
        print(f"层位相交 {sorted(inter)}：方案文件层位 {sorted(derived_set)} ∩ 问题层位 {sorted(problem_layers)} ≠ ∅ → PASS")
        sys.exit(0)

    reason = str(fields.get("层位偏离理由", "")).strip()
    if reason:
        print(f"层位不相交：问题层位 {sorted(problem_layers)}，方案文件层位 {sorted(derived_set)}")
        print(f"WARNING: 层位偏离放行——理由「{reason}」（理由质量留软层+复盘审计，谎报由 trigger 审计追责）")
        sys.exit(0)

    print(f"层位不相交：问题层位 {sorted(problem_layers)} 与方案文件层位集合 {sorted(derived_set)} 不相交，且无层位偏离理由 → 判 B")
    sys.exit(2)

if __name__ == "__main__":
    main()
