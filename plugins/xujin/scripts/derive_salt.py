#!/usr/bin/env python3
"""wrench-skill 开发者侧 Salt 派生工具（一次性运行，不随插件分发运行）。

链路（二道混淆之第一道，开发期离线执行）：
  固定盐源文本（从 lib/constants.mjs 单源读取）
  → 本地冻结 1024 维 BGE-M3 编码（HF 缓存离线加载，零网络）
  → L2 归一化 → uint16 定点量化 → 截取前 16 字节
  → 写回 lib/constants.mjs 的 EMBEDDED_SALT_HEX

插件运行时只消费派生结果常量，不依赖任何模型，保持轻量化。

用法：
  python3 scripts/derive_salt.py            # 派生并写回 constants.mjs
  python3 scripts/derive_salt.py --check    # 只校验当前常量是否与重算一致
"""
import os
import re
import struct
import sys
from pathlib import Path

# 强制离线：只读本地 HF 缓存，禁止任何网络访问
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONSTANTS = PLUGIN_ROOT / 'lib' / 'constants.mjs'
MODEL_ID = 'BAAI/bge-m3'  # 冻结 1024 维模型，本地 HF 缓存
SALT_BYTES = 16


def read_salt_source_text() -> str:
    text = CONSTANTS.read_text(encoding='utf-8')
    m = re.search(r"SALT_SOURCE_TEXT\s*=\s*'([^']*)'", text)
    if not m:
        sys.exit('错误：未能在 lib/constants.mjs 中找到 SALT_SOURCE_TEXT。')
    return m.group(1)


def derive() -> str:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    source = read_salt_source_text()
    print(f'→ 盐源文本：{source!r}')
    print(f'→ 离线加载本地模型 {MODEL_ID}（首次加载约数十秒）…')
    model = SentenceTransformer(MODEL_ID, local_files_only=True)
    vec = model.encode(source, normalize_embeddings=False)
    vec = np.asarray(vec, dtype=np.float64)
    if vec.shape[0] != 1024:
        sys.exit(f'错误：Embedding 维度异常，期望 1024 维，实际 {vec.shape[0]} 维。模型版本可能被更换。')
    # L2 归一化
    vec = vec / (np.linalg.norm(vec) or 1.0)
    # uint16 定点量化（与 lib/embedding 历史链路同一定义）：[-1,1] → [0,65535] 四舍五入
    q = np.clip(np.round((vec + 1.0) / 2.0 * 65535.0), 0, 65535).astype('<u2')
    salt = q.tobytes()[:SALT_BYTES]
    return salt.hex()


def write_back(hex_salt: str):
    text = CONSTANTS.read_text(encoding='utf-8')
    new_text, n = re.subn(r"EMBEDDED_SALT_HEX\s*=\s*'[0-9a-f]*'",
                          f"EMBEDDED_SALT_HEX = '{hex_salt}'", text)
    if n != 1:
        sys.exit('错误：constants.mjs 中 EMBEDDED_SALT_HEX 替换失败。')
    CONSTANTS.write_text(new_text, encoding='utf-8')


def main():
    hex_salt = derive()
    if '--check' in sys.argv:
        text = CONSTANTS.read_text(encoding='utf-8')
        m = re.search(r"EMBEDDED_SALT_HEX\s*=\s*'([0-9a-f]*)'", text)
        current = m.group(1) if m else ''
        if current == hex_salt:
            print('✓ 校验通过：constants.mjs 中的 Salt 与本地模型重算一致。')
        else:
            sys.exit(f'✗ 校验失败：constants 中={current or "(空)"}，重算={hex_salt}。'
                     '模型或盐源文本已漂移，需重新加密全部资产。')
        return
    write_back(hex_salt)
    print(f'✓ Salt 派生完成并写回 lib/constants.mjs：{hex_salt}')
    print('  后续执行 node scripts/encrypt.mjs --manifest <清单> 即使用该 Salt 加密。')


if __name__ == '__main__':
    main()
