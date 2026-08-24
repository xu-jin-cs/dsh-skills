#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
random_sample.py — POST_GATE_AUDIT 机械随机抽样器（纯 stdlib，2026-08-16 REFORM-GATE 裁定）

防「自选样本 / 试种子购物 / 先抽后改池」。POST_GATE_AUDIT 抽样禁止自选样本，
必须执行本脚本机械抽样；sv 只对抽到的固定样本做语义复核。

硬约束：
  1. 种子不可由调用方指定（无 --seed 参数）：脚本内部用 secrets 模块生成并留痕，
     输出四元组 {seed(hex), pool_hash, algo_version, timestamp} 可复现审计。
  2. 池快照哈希：对 --pool 文件原始字节计算 sha256 留痕（防先抽后改池）。
  3. 样本量下限硬阻断：sample_size = max(ceil(pool_size * ratio), min(默认3))；
     pool_size < 所需样本量时全量抽取并标注 exhaustive=true。
  4. 分层抽样：池中若存在含高危标记（--high-risk-key 指定字段为真）的用例，
     样本中至少含 1 条高危用例。
  5. 复现性：以留痕 seed 初始化 random.Random 抽样；审计者可用同一 seed +
     同一池快照（hash 一致）+ 同一 algo_version 复现完全相同的样本。

用例池 JSON 契约：顶层为用例数组，元素为对象（必须含 case_id 字段）或字符串
（字符串本身即 case_id）。

用法：
  python3 random_sample.py --pool <用例池JSON文件> --ratio <抽样率> \
      [--min <下限>] [--high-risk-key <高危标记字段>] --out <抽样结果JSON>

输出 JSON：
  {
    "seed": "<hex>",              # 四元组之一，secrets 生成
    "pool_hash": "<sha256>",      # 四元组之二，池文件原始字节 sha256
    "algo_version": "rs-v1",      # 四元组之三
    "timestamp": "<ISO8601Z>",    # 四元组之四
    "pool_size": <int>,
    "sample_size": <int>,
    "ratio": <float>,             # 声明抽样率（入参）
    "effective_ratio": <float>,   # 实际抽样率 sample_size/pool_size
    "min_floor": <int>,
    "exhaustive": <bool>,         # 池总量 < 下限时全量抽取
    "high_risk_key": "<str>",
    "high_risk_in_pool": <int>,
    "high_risk_in_sample": <int>,
    "samples": ["case_id", ...]
  }

退出码：0 成功；2 参数/输入违例（stderr 带原因）；1 未预期错误（stderr 带原因）。
"""
import argparse
import hashlib
import json
import math
import random
import secrets
import sys
from datetime import datetime, timezone

ALGO_VERSION = "rs-v1"
DEFAULT_MIN = 3
DEFAULT_HIGH_RISK_KEY = "high_risk"


def fail(msg, code=2):
    print("random_sample: %s" % msg, file=sys.stderr)
    sys.exit(code)


def load_pool(path):
    """读取池文件，返回 (原始字节, case_id 列表, 高危 case_id 集合)。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        fail("用例池文件读取失败: %s" % e)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        fail("用例池 JSON 解析失败: %s" % e)
    if not isinstance(data, list):
        fail("用例池 JSON 契约不符：顶层必须为数组")
    ids, seen = [], set()
    for i, item in enumerate(data):
        if isinstance(item, str):
            cid = item
        elif isinstance(item, dict):
            cid = item.get("case_id")
            if not isinstance(cid, str) or not cid.strip():
                fail("用例池第 %d 条缺 case_id（非空字符串）" % i)
        else:
            fail("用例池第 %d 条类型非法（需对象或字符串）" % i)
        if cid in seen:
            fail("用例池 case_id 重复: %s" % cid)
        seen.add(cid)
        ids.append(cid)
    return raw, ids, data


def main():
    ap = argparse.ArgumentParser(description="POST_GATE_AUDIT 机械随机抽样器（种子脚本内生成并留痕）")
    ap.add_argument("--pool", required=True, help="用例池 JSON 文件路径")
    ap.add_argument("--ratio", required=True, type=float, help="抽样率，(0,1]")
    ap.add_argument("--min", dest="min_floor", type=int, default=DEFAULT_MIN,
                    help="样本量下限（默认 %d）" % DEFAULT_MIN)
    ap.add_argument("--high-risk-key", default=DEFAULT_HIGH_RISK_KEY,
                    help="高危标记字段名（默认 %s）" % DEFAULT_HIGH_RISK_KEY)
    ap.add_argument("--out", required=True, help="抽样结果 JSON 输出路径")
    args = ap.parse_args()

    if not (0 < args.ratio <= 1):
        fail("--ratio 必须 ∈ (0,1]，实际 %s" % args.ratio)
    if args.min_floor < 1:
        fail("--min 必须 ≥ 1，实际 %s" % args.min_floor)

    raw, ids, data = load_pool(args.pool)
    pool_size = len(ids)
    if pool_size == 0:
        fail("用例池为空，无样可抽")

    hr_key = args.high_risk_key
    high_risk_ids = set()
    for item in data:
        if isinstance(item, dict) and item.get(hr_key):
            high_risk_ids.add(item["case_id"])

    pool_hash = hashlib.sha256(raw).hexdigest()
    seed = secrets.token_hex(16)  # 调用方不可指定；留痕后可复现
    rng = random.Random(seed)

    required = max(int(math.ceil(pool_size * args.ratio)), args.min_floor)
    exhaustive = pool_size < required
    sample_size = pool_size if exhaustive else required

    hr_in_pool = [cid for cid in ids if cid in high_risk_ids]
    normal_in_pool = [cid for cid in ids if cid not in high_risk_ids]

    if exhaustive:
        samples = list(ids)
    else:
        samples = []
        # 分层：高危层保底 1 条（池中存在高危用例时）
        hr_quota = 1 if hr_in_pool else 0
        if hr_quota:
            samples.append(rng.choice(hr_in_pool))
        rest_need = sample_size - len(samples)
        rest_pool = hr_in_pool + normal_in_pool  # 高危仍可与普通层竞争剩余名额
        rest_pool = [cid for cid in rest_pool if cid not in samples]
        samples.extend(rng.sample(rest_pool, rest_need))
        rng.shuffle(samples)

    result = {
        "seed": seed,
        "pool_hash": pool_hash,
        "algo_version": ALGO_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pool_size": pool_size,
        "sample_size": sample_size,
        "ratio": args.ratio,
        "effective_ratio": round(sample_size / pool_size, 6),
        "min_floor": args.min_floor,
        "exhaustive": exhaustive,
        "high_risk_key": hr_key,
        "high_risk_in_pool": len(hr_in_pool),
        "high_risk_in_sample": sum(1 for c in samples if c in high_risk_ids),
        "samples": samples,
    }

    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        fail("输出文件写入失败: %s" % e)

    print(json.dumps({"pass": True, "out": args.out,
                      "pool_size": pool_size, "sample_size": sample_size,
                      "exhaustive": exhaustive,
                      "high_risk_in_sample": result["high_risk_in_sample"]},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
