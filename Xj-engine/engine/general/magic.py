"""general/magic.py — 魔数校验（ETLEngine 自实现，行为资产注册实现本体）。

台账 H6 裁定：魔数字节表是行为数据，不搬进 YAML——validation.yaml 只登记
开关与 check_extensions 白名单，条目指向本实现。是否对某 ext 启用校验由
调用方（general_validate 执行器）按规则表裁决；本函数对未登记 ext 恒 True
（交由白名单层拦截，不越权拒绝）。
"""

# ZIP 族（Office Open XML）与 OLE2 族（二进制 Office）魔数前缀
_ZIP_MAGIC = b"PK\x03\x04"
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_ZIP_EXTS = frozenset({"docx", "xlsx", "pptx"})
_OLE2_EXTS = frozenset({"doc", "wps", "ppt", "xls"})
_TEXT_EXTS = frozenset({"txt", "md", "csv", "html", "htm"})

_SNIFF_BYTES = 8192  # 文本嗅探窗口（前 8KB）


def _looks_like_text(header: bytes) -> bool:
    """前 8KB 可解码且非二进制 → True（文本格式恒 True 通道）。"""
    if b"\x00" in header:  # NUL 字节 = 二进制实锤
        return False
    for enc in ("utf-8", "gbk"):
        try:
            header.decode(enc)
            return True
        except UnicodeDecodeError:
            continue
    return False


def check_magic_bytes(file_path: str, ext: str) -> bool:
    """校验文件头魔数是否与扩展名匹配。未登记 ext 返回 True（白名单层拦截）。"""
    ext = ext.lower().lstrip(".")
    if ext not in _ZIP_EXTS | _OLE2_EXTS | _TEXT_EXTS:
        return True
    try:
        with open(file_path, "rb") as f:
            header = f.read(_SNIFF_BYTES)
    except OSError:
        return False
    if not header:
        return ext in _TEXT_EXTS  # 空文件：文本可过，二进制不可过
    if ext in _ZIP_EXTS:
        return header.startswith(_ZIP_MAGIC)
    if ext in _OLE2_EXTS:
        return header.startswith(_OLE2_MAGIC)
    return _looks_like_text(header)
