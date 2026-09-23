#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""component_freshness_check.py — 成分标定新鲜度闸（2026-08-22 块L 方向3，REFORM-GATE 判A，
块文件 ~/.agents/logs/reform_blocks/trigger_rate_99_20260822.md）。
背景：recalibration_freshness 随召回指标废止（abolished_skill_hitrate_20260822）时，
成分侧（SOFT 信号 n 元成分化，块E/M3b）的标定值守被误伤——本检查重挂该点位。

判 B（exit 2）条件（任一命中即 B，强制重标 component_calibration.py）：
  ① 标定件缺失：component_lexicon.json / calibration_examples.json 不存在或不可解析；
  ② pipeline_hash 漂移：component_calibration.py + component_lexicon.json 联合 sha256
     前 16 位 ≠ calibration_examples.json meta.pipeline_hash（口径断代戳，标定管线或
     词表变更即现行标定失效）；
  ③ 语料漂移 >5%：用户语料消息数（_user_corpus_ngrams.json total_msgs）相对
     标定记录 meta.corpus_msgs 漂移超 ±5%。
全过 → exit 0（A），单行输出理由。挂点：复盘着陆闸族。
"""
import hashlib
import json
import os
import sys

GATE_DIR = os.path.expanduser("~/.agents/skills/gate-switch")
SCRIPT = os.path.join(GATE_DIR, "scripts", "component_calibration.py")
LEXICON = os.path.join(GATE_DIR, "data", "component_lexicon.json")
EXAMPLES = os.path.join(GATE_DIR, "data", "calibration_examples.json")
CORPUS = os.path.expanduser("~/.agents/retro-skills-registry/runtime/_user_corpus_ngrams.json")
DRIFT_CAP = 0.05
TAG = "COMPONENT-FRESHNESS"


def fail(reason):
    print(f"{TAG}: 判B——{reason} → 强制重标 python3 {SCRIPT}（成分标定管线）")
    sys.exit(2)


# ① 标定件缺失
for p in (SCRIPT, LEXICON, EXAMPLES, CORPUS):
    if not os.path.isfile(p):
        fail(f"标定件缺失 {p}")
try:
    meta = json.load(open(EXAMPLES, encoding="utf-8"))["meta"]
    recorded_hash = meta["pipeline_hash"]
    recorded_msgs = int(meta["corpus_msgs"])
    total_msgs = int(json.load(open(CORPUS, encoding="utf-8"))["total_msgs"])
except Exception as e:
    fail(f"标定件不可解析（{e}）")

# ② pipeline_hash 漂移（联合 sha256 前 16 位，口径断代戳）
h = hashlib.sha256()
for p in (SCRIPT, LEXICON):
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
cur_hash = h.hexdigest()[:16]
if cur_hash != recorded_hash:
    fail(f"pipeline_hash 漂移（记录 {recorded_hash} ≠ 现行 {cur_hash}），标定管线/词表已变更")

# ③ 语料漂移 >5%
drift = abs(total_msgs - recorded_msgs) / max(recorded_msgs, 1)
if drift > DRIFT_CAP:
    fail(f"语料漂移 {drift:.1%} > 5%（标定 {recorded_msgs} 条 → 现行 {total_msgs} 条）")

print(f"{TAG}: PASS pipeline_hash={cur_hash} corpus={total_msgs}/{recorded_msgs} "
      f"drift={drift:.1%}≤5% 成分标定现行有效")
sys.exit(0)
