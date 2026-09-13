# 【宿主集成件 · HOST-ONLY】2026-09-13：本模块深绑 agent-harness 工作流/数据库，
# 无宿主环境（干净 venv 无 backend）不可 import——属预期语义（宿主功能在宿主用）。
# FlowGraph 核心（graph/nodes/edges/state/checkpoint）不依赖本模块。
import os as _os_hostcheck
if _os_hostcheck.environ.get("XJFRAME_STRICT_NO_HOST") == "1":
    raise ImportError("BRANCH_STORE_HOST_ONLY: 宿主集成件在无宿主模式禁用")
"""分支状态 SQLAlchemy 操作封装（业务库 harness.db）。"""

from datetime import datetime, timezone
from typing import Optional, List

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import InstanceBranchStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BranchStatusDTO(BaseModel):
    instance_id: str
    branch_node_key: str
    branch_sub_thread_id: str
    status: str
    start_time: Optional[datetime]
    finish_time: Optional[datetime]
    error_msg: Optional[str]
    artifact_root: Optional[str]


def _to_dto(row: InstanceBranchStatus) -> BranchStatusDTO:
    return BranchStatusDTO(
        instance_id=row.instance_id,
        branch_node_key=row.branch_node_key,
        branch_sub_thread_id=row.branch_sub_thread_id,
        status=row.status,
        start_time=row.start_time,
        finish_time=row.finish_time,
        error_msg=row.error_msg,
        artifact_root=row.artifact_root,
    )


def get_db_session() -> Session:
    return SessionLocal()


def init_branch_record(
    db: Session,
    instance_id: str,
    branch_node_key: str,
    sub_thread_id: str,
    artifact_root: str,
) -> None:
    """不存在则初始化分支记录；存在则跳过（幂等）。"""
    existing = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.instance_id == instance_id,
        InstanceBranchStatus.branch_node_key == branch_node_key,
    ).first()
    if existing:
        return
    rec = InstanceBranchStatus(
        instance_id=instance_id,
        branch_node_key=branch_node_key,
        branch_sub_thread_id=sub_thread_id,
        status="pending",
        artifact_root=artifact_root,
    )
    db.add(rec)
    db.commit()


def set_branch_running(db: Session, sub_thread_id: str) -> None:
    rec = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.branch_sub_thread_id == sub_thread_id
    ).first()
    if rec:
        rec.status = "running"
        rec.start_time = _utcnow()
        db.commit()


def set_branch_final(
    db: Session,
    sub_thread_id: str,
    status: str,
    error_msg: Optional[str] = None,
) -> None:
    rec = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.branch_sub_thread_id == sub_thread_id
    ).first()
    if rec:
        rec.status = status
        rec.finish_time = _utcnow()
        rec.error_msg = error_msg
        db.commit()


def reset_branch_to_pending(db: Session, instance_id: str, branch_node_key: str) -> None:
    rec = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.instance_id == instance_id,
        InstanceBranchStatus.branch_node_key == branch_node_key,
    ).first()
    if rec:
        rec.status = "pending"
        rec.start_time = None
        rec.finish_time = None
        rec.error_msg = None
        db.commit()


def list_instance_branches(db: Session, instance_id: str) -> List[BranchStatusDTO]:
    rows = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.instance_id == instance_id
    ).all()
    return [_to_dto(r) for r in rows]


def get_branch(db: Session, instance_id: str, branch_node_key: str) -> Optional[BranchStatusDTO]:
    r = db.query(InstanceBranchStatus).filter(
        InstanceBranchStatus.instance_id == instance_id,
        InstanceBranchStatus.branch_node_key == branch_node_key,
    ).first()
    return _to_dto(r) if r else None


def list_instance_branches_sync(instance_id: str) -> List[BranchStatusDTO]:
    db = get_db_session()
    try:
        return list_instance_branches(db, instance_id)
    finally:
        db.close()
