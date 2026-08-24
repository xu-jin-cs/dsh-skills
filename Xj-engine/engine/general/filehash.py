"""filehash.py — 文件 MD5 计算唯一实现（FIX-MD5-CONSOLIDATE，2026-08-22 短板修复）。

原 _md5_file 在 general_stages.py / worker.py / parsers.py 三处重复，现收口于此。
消费方：general_stages.general_validate / worker.build_ingest_payload / parsers.parse。
"""
import hashlib
from pathlib import Path


def md5_file(path: Path) -> str:
    """流式计算文件 MD5 hex（1MiB 分块，大文件不爆内存）。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1 << 20), b""):
            h.update(buf)
    return h.hexdigest()
