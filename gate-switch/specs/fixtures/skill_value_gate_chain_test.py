#!/usr/bin/env python3
"""skill_value_gate_chain_test.py — 块K 全链路自验（修订增补2 替代版；spec script_exit 调用，全在临时目录，零生产触碰）。

链路：母体测例紧贴改写候选 ×2 次过闸 →
  第1次：exit 7 DEDUP_COUNT，临时 registry demand_count=1，demand_ledger 1 笔（快照三字段+全文），无转化
  第2次：exit 7，demand_count 达 2（第三次被需要）→ specialize_replace 替代式转化：
         旧领域=status archived+superseded_by+_sp_cycle+目录移 archive/；
         新专项 entry（<旧id>-sp1：specialized/parent_skill/supersedes:[旧]/demand_count=0）+ 新 SKILL.md 专项卡；
         role-retro-links 旧绑定剔除+新专项绑定；decision 台账 SPECIALIZE 留痕（含 new_specialty_id）。
  数据源无残留核验（单元域）：skills/ 无旧目录、role-links 无旧绑定、registry 现役集无旧 id。
  （引擎 LanceDB/legacy SQL 层由 --no-engine 隔离；生产路径代码由 spec grep 核验，派生态可重建见 CONTRACT.md 2.1）
退出码：0=全链路过 / 1=任一断言失败（打印失败点）。
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path.home() / ".agents/skills/gate-switch/scripts/skill_value_gate_check.py"
FIXTURE = Path.home() / ".agents/skills/gate-switch/specs/fixtures/skill_value_gate_dup.json"
SRC_REGISTRY = Path.home() / ".agents/retro-skills-registry/registry-index.json"
SRC_SKILLS = Path.home() / ".agents/retro-skills-registry/skills"
TARGET = "retro-backend-engineer-001-依赖外部服务的质量闸门禁止静默降级VL-hastext-文字拦截依赖-"


def fail(msg):
    print(f"CHAIN-FAIL: {msg}")
    sys.exit(1)


def main():
    dup = json.loads(FIXTURE.read_text(encoding="utf-8"))["content"]
    tmp = Path(tempfile.mkdtemp(prefix="svg_chain_"))
    reg = tmp / "registry.json"
    shutil.copy(SRC_REGISTRY, reg)
    src_entry = next((e for e in json.loads(reg.read_text(encoding="utf-8"))["entries"]
                      if e["skill_id"] == TARGET), None)
    if src_entry is None:
        fail(f"母体测例条目不在 registry: {TARGET}")
    skills = tmp / "skills"
    archive = tmp / "archive"
    src_skill_dir = SRC_SKILLS / src_entry.get("skill_dir", TARGET)
    if src_skill_dir.exists():
        shutil.copytree(src_skill_dir, skills / src_skill_dir.name)
    dled, dec = tmp / "demand.jsonl", tmp / "decisions.jsonl"
    links = tmp / "role-links.json"
    links.write_text(json.dumps({"schema_version": "1.0.0", "roles": {
        "be": [{"skill_id": TARGET, "description": "seed", "match_count": 0}]}}, ensure_ascii=False), encoding="utf-8")

    def run(content=None):
        return subprocess.run(
            [sys.executable, str(GATE), "--content", content or dup, "--role", "be", "--project", "fixture-dedup",
             "--registry", str(reg), "--demand-ledger", str(dled),
             "--decision-ledger", str(dec), "--skills-dir", str(skills),
             "--archive-dir", str(archive), "--role-links", str(links), "--no-engine"],
            capture_output=True, text=True)

    r1 = run()
    if r1.returncode != 7:
        fail(f"第1次过闸 exit={r1.returncode}（期望 7 DEDUP_COUNT）stdout_tail={(r1.stdout or '')[-200:]}")
    e1 = next(e for e in json.loads(reg.read_text(encoding="utf-8"))["entries"] if e["skill_id"] == TARGET)
    if (e1.get("demand_count") or 0) != 1:
        fail(f"第1次后 demand_count={e1.get('demand_count')}（期望 1）")
    if e1.get("status") == "archived":
        fail("第1次后旧领域不应归档")
    n_demand_1 = sum(1 for l in open(dled, encoding="utf-8") if l.strip())
    if n_demand_1 != 1:
        fail(f"第1次后 demand_ledger={n_demand_1} 笔（期望 1）")
    # 口径补充①：快照必须存足——触发层面/场景/内容全文
    snap1 = json.loads(open(dled, encoding="utf-8").readline())["candidate_snapshot"]
    for field in ("trigger_layer", "scenario", "content_full"):
        if field not in snap1:
            fail(f"demand 快照缺字段 {field}（口径补充①：触发层面/场景/内容全文必备）")
    if snap1["content_full"] != dup:
        fail("content_full 非全文（被截断）")

    r2 = run()
    if r2.returncode != 7:
        fail(f"第2次过闸 exit={r2.returncode}（期望 7）stdout_tail={(r2.stdout or '')[-200:]} stderr={(r2.stderr or '')[-200:]}")
    entries = json.loads(reg.read_text(encoding="utf-8"))["entries"]
    old = next(e for e in entries if e["skill_id"] == TARGET)
    new_sid = f"{TARGET}-sp1"
    new = next((e for e in entries if e["skill_id"] == new_sid), None)
    # ── 修订增补2①：晋升=替代非并存 ──
    if old.get("status") != "archived":
        fail("旧领域技能未归档（替代口径失败：新旧并存）")
    if old.get("superseded_by") != new_sid:
        fail(f"旧领域 superseded_by={old.get('superseded_by')}（期望 {new_sid[:40]}…）")
    if (old.get("_sp_cycle") or 0) != 1:
        fail(f"旧领域 _sp_cycle={old.get('_sp_cycle')}（期望 1 轮次留痕）")
    if new is None:
        fail(f"新专项 entry 不存在: {new_sid[:50]}…")
    if not new.get("specialized") or new.get("skill_level") != "specialty":
        fail("新专项 specialized/skill_level 标记缺失")
    if new.get("parent_skill") != TARGET:
        fail(f"新专项 parent_skill={new.get('parent_skill')}（期望指向旧领域）")
    if new.get("supersedes") != [TARGET]:
        fail(f"新专项 supersedes={new.get('supersedes')}（期望 [旧领域skill_id]）")
    if (new.get("demand_count") or 0) != 0:
        fail(f"新专项 demand_count={new.get('demand_count')}（期望 0 重置）")
    # ── 修订增补2③+任务书自验新增项：各数据源无残留 ──
    if (skills / src_entry.get("skill_dir", TARGET)).exists():
        fail("skills/ 旧目录残留（未移档）")
    if not (archive / src_entry.get("skill_dir", TARGET)).exists():
        fail("archive/ 无旧目录（移档未发生）")
    if not (skills / new_sid / "SKILL.md").exists():
        fail("新专项 SKILL.md 未生成")
    lk = json.loads(links.read_text(encoding="utf-8"))
    flat = [x.get("skill_id") for es in lk.get("roles", {}).values() if isinstance(es, list) for x in es]
    if TARGET in flat:
        fail("role-retro-links 旧绑定残留")
    if new_sid not in flat:
        fail("role-retro-links 新专项未绑定")
    # 新专项卡四段骨架（口径补充②③）
    text = (skills / new_sid / "SKILL.md").read_text(encoding="utf-8")
    for section in ("### 场景族", "### 主线步骤", "### 参数与分支", "### 坑位"):
        if section not in text:
            fail(f"专项技能卡缺骨架段 {section}")
    if "TODO" not in text:
        fail("语义补完 TODO 标记缺失")
    if f"specialized_from: `{TARGET}`" not in text:
        fail("专项卡缺 specialized_from 溯源行")
    if text.count("#### 需求案 #") != 2:
        fail(f"需求证据快照数={text.count('#### 需求案 #')}（期望 2）")
    n_demand_2 = sum(1 for l in open(dled, encoding="utf-8") if l.strip())
    if n_demand_2 != 2:
        fail(f"demand_ledger={n_demand_2} 笔（期望 2）")
    decs = [json.loads(l) for l in open(dec, encoding="utf-8") if l.strip()]
    if not any(d.get("verdict") == "SPECIALIZE" and d.get("new_specialty_id") == new_sid for d in decs):
        fail("decision 台账缺 SPECIALIZE 留痕（含 new_specialty_id）")

    # ── 口径补充3 自验新增项：specialized 条目再遇同义候选 → 计数不变+内容追加+候选不入库 ──
    old_desc = old.get("description") or ""
    dup3 = old_desc + "。坑位补充：离线演练时健康检查走模拟通道"  # 含一行全新内容（验证抽取）
    n_entries_before = len(entries)
    r3 = run(dup3)
    if r3.returncode != 7:
        fail(f"第3次过闸（吸收期）exit={r3.returncode}（期望 7）stdout_tail={(r3.stdout or '')[-200:]}")
    if "ABSORB_TARGET" not in (r3.stdout or ""):
        fail(f"第3次未走吸收期（无 ABSORB_TARGET）：{(r3.stdout or '')[-200:]}")
    reg3 = json.loads(reg.read_text(encoding="utf-8"))["entries"]
    if len(reg3) != n_entries_before:
        fail(f"吸收期候选入库了（entries {n_entries_before}→{len(reg3)}）（违反③直接丢弃）")
    new3 = next(e for e in reg3 if e["skill_id"] == new_sid)
    if (new3.get("demand_count") or 0) != 0:
        fail(f"吸收期 demand_count 变化（{new3.get('demand_count')}）（违反①不再计数）")
    n_demand_3 = sum(1 for l in open(dled, encoding="utf-8") if l.strip())
    if n_demand_3 != 2:
        fail(f"吸收期 demand_ledger 新增记录（{n_demand_3}≠2）（违反①不计数）")
    decs3 = [json.loads(l) for l in open(dec, encoding="utf-8") if l.strip()]
    absorb_rec = next((d for d in decs3 if d.get("verdict") == "ABSORB" and d.get("matched_skill_id") == new_sid), None)
    if absorb_rec is None:
        fail("decision 台账缺 ABSORB 留痕（违反④）")
    if not any("模拟通道" in ln for ln in absorb_rec.get("extracted_lines", [])):
        fail(f"ABSORB 抽取行缺新内容（extracted={absorb_rec.get('extracted_lines')}）（违反②抽取）")
    if "content_full" not in (absorb_rec.get("candidate_snapshot") or {}):
        fail("ABSORB 台账缺候选快照 content_full（违反④快照留痕）")
    text3 = (skills / new_sid / "SKILL.md").read_text(encoding="utf-8")
    if "<!-- DEMAND-ABSORB:START -->" not in text3 or "模拟通道" not in text3:
        fail("专项卡缺 DEMAND-ABSORB 块或未含新内容行（违反②追加）")

    print(f"CHAIN-PASS: 计数1→2→替代式转化→吸收期全链路（{TARGET[:36]}…→…-sp1）"
          f"墓碑/移档/新专项卡/角色绑定替换/台账留痕/计数重置/数据源无残留/吸收期(计数不变+内容追加+候选丢弃) 全部断言通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
