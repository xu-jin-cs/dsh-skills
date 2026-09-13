"""
LangGraph 文件引用读写工具 — 文档/日志写入磁盘，State 只存 FilePathRef。

写入规范：
  Agent 产出完整文档/日志后，统一写入 evidence_root_dir 下：
    {evidence_root_dir}/docs/   — 文档类（PRD、交互设计、报告等）
    {evidence_root_dir}/logs/   — 日志类（审计日志、错误日志分段文件）
  写入后计算 md5，生成 FilePathRef 存入 FlowState，原始长文本丢弃。

读取规范：
  read_file_ref() 根据 path+md5 校验文件完整性后返回全文。
  md5 不匹配 → 抛出 ValueError（文件被篡改）。
"""

import hashlib
import os
import uuid
from typing import Optional

from engine.flow.state import FilePathRef


def ensure_evidence_dirs(evidence_root_dir: str) -> None:
    """创建证据目录子结构"""
    for sub in ("docs", "logs"):
        os.makedirs(os.path.join(evidence_root_dir, sub), exist_ok=True)


# DEPRECATED（ENG-050，2026-08-20 审计）：零调用方，FilePathRef 机制名存实亡，禁止新代码调用。
def write_evidence_file(
    evidence_root: str,
    sub_dir: str,
    content: str,
    brief_summary: Optional[str] = None,
    filename: Optional[str] = None,
) -> FilePathRef:
    """
    写入证据文件并返回 FilePathRef。

    Args:
        evidence_root: evidence_root_dir（FlowState.evidence_root_dir）
        sub_dir: "docs" 或 "logs"
        content: 完整文件内容
        brief_summary: 百字内摘要（仅用于流程判断，不存全文）
        filename: 可选文件名，默认自动生成 uuid.md
    """
    target_dir = os.path.join(evidence_root, sub_dir)
    os.makedirs(target_dir, exist_ok=True)

    file_path = os.path.join(target_dir, filename or f"{uuid.uuid4().hex}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    with open(file_path, "rb") as f:
        file_md5 = hashlib.md5(f.read()).hexdigest()

    return FilePathRef(
        file_path=os.path.abspath(file_path),
        file_md5=file_md5,
        brief_summary=brief_summary,
    )


# DEPRECATED（ENG-050，2026-08-20 审计）：零调用方，FilePathRef 机制名存实亡，禁止新代码调用。
def read_file_ref(ref: FilePathRef) -> str:
    """
    根据 FilePathRef 读取文件全文，校验 md5。
    文件被篡改 → 抛出 ValueError。
    """
    if not os.path.exists(ref.file_path):
        raise FileNotFoundError(f"文件不存在: {ref.file_path}")

    with open(ref.file_path, "rb") as f:
        real_md5 = hashlib.md5(f.read()).hexdigest()

    if real_md5 != ref.file_md5:
        raise ValueError(
            f"文件被篡改或损坏: {ref.file_path} "
            f"(期望md5={ref.file_md5}, 实际md5={real_md5})"
        )

    with open(ref.file_path, "r", encoding="utf-8") as f:
        return f.read()


# DEPRECATED（ENG-050，2026-08-20 审计）：零调用方，FilePathRef 机制名存实亡，禁止新代码调用。
def verify_file_ref(ref: FilePathRef) -> bool:
    """校验 FilePathRef 引用文件是否完整（不加载全文）"""
    if not os.path.exists(ref.file_path):
        return False
    with open(ref.file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest() == ref.file_md5
