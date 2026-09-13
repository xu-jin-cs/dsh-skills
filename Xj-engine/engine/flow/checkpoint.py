"""
LangGraph 本地 SQLite Checkpoint — 多版本快照存储，支持定点回滚。

改造说明（2026-07-01，P1 多版本改造）：
  原有单版本覆盖存储，thread_id 唯一主键，每次 save 覆盖旧状态。
  改造后支持：
    - 复合主键 (thread_id, snap_id)，每次生成独立快照，不覆盖旧数据
    - 手动基线快照（带 memo 备注，用于目录树备份）
    - 按 snap_id 定点回滚任意历史 FlowState
    - 快照列表查询（轻量化元数据，不含大 blob）
    - 向下兼容：load_latest 逻辑完全保留

分层存储策略（同原有设计）：
  ┌──────────────────────────────────────────────┐
  │ LangGraph 本地 SQLite Checkpoint（第 1 优先） │ ← 短期运行缓存
  ├──────────────────────────────────────────────┤
  │ Harness 主数据库（第 2 优先）                  │ ← 永久全量归档
  └──────────────────────────────────────────────┘

数据模型（新表结构）：
  CREATE TABLE checkpoints (
      thread_id TEXT NOT NULL,
      snap_id TEXT NOT NULL,      -- snap_{毫秒时间戳}_{8位hex}
      state_json TEXT NOT NULL,
      node_key TEXT DEFAULT '',
      memo TEXT DEFAULT '',        -- 快照备注，如「目录原始基线」
      create_ts INTEGER NOT NULL, -- 毫秒时间戳
      PRIMARY KEY (thread_id, snap_id)
  );

字段说明：
  thread_id  — 会话唯一 ID，同原有逻辑
  snap_id    — 快照唯一标识，每次 INSERT 自动生成
  state_json — 完整序列化 FlowState JSON（胖状态，目录树等）
  node_key   — Graph 当前执行节点名，定位快照生成阶段
  memo       — 自定义备注，手动快照必填，标记「目录原始基线」
  create_ts  — 毫秒 Unix 时间戳，排序/筛选
"""

import json
import logging
import os
import sqlite3
import subprocess  # noqa: S404 — subprocess 仅用于 checkpoint-pack.sh ZIP 归档触发，非用户输入
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.flow.state import FlowState, FlowStatus

logger = logging.getLogger("langgraph.checkpoint")

# 默认 Checkpoint 目录
DEFAULT_CHECKPOINT_DIR = os.environ.get(
    "LANGGRAPH_CHECKPOINT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".langgraph"),
)


def generate_snap_id() -> str:
    """生成快照唯一 ID 格式：snap_{毫秒时间戳}_{8位hex}"""
    ts = int(time.time() * 1000)
    short_uid = uuid.uuid4().hex[:8]
    return f"snap_{ts}_{short_uid}"


def format_timestamp(ts_ms: int) -> str:
    """毫秒时间戳 → 本地可读日期时间"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


class SqliteCheckpointer:
    """
    SQLite 本地 Checkpoint — 多版本快照持久化。

    线程安全：threading.Lock 保护写操作
    自动建表/迁移：首次使用时创建/迁移 checkpoints 表
    自动快照：Graph step() 调用 save()，生成独立 snap_id
    手动快照：manual_snapshot() 带备注，用于目录基线备份
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(DEFAULT_CHECKPOINT_DIR, "checkpoints.db")
        self._lock = threading.Lock()

        # 确保目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化/迁移表结构
        self._init_db()

    # ─── 数据库初始化 & 迁移 ─────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # WAL 模式 + busy_timeout：读写不互斥，等待 5s 后超时
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        """
        创建或迁移 checkpoints 表。

        迁移逻辑：
          1. 新安装 → 直接建新表
          2. 旧版本（单版本 thread_id PK）→ 自动迁移到复合主键
          3. v2 扩展 → 增量添加 task_status, task_title 字段
        """
        with self._lock:
            conn = self._get_conn()
            try:
                # 检查旧表是否存在（单版本结构：thread_id TEXT PK）
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'")
                old_table = cursor.fetchone()

                if old_table:
                    # 检查是否是旧版单主键表
                    pragma = conn.execute("PRAGMA table_info(checkpoints)").fetchall()
                    columns = {r["name"]: r for r in pragma}
                    has_snap_id = "snap_id" in columns

                    if not has_snap_id:
                        logger.info("检测到旧版 checkpoints 表（单版本），开始迁移到多版本...")
                        # 1. 重命名旧表
                        conn.execute("ALTER TABLE checkpoints RENAME TO checkpoints_old")
                        # 2. 创建新表（含 task_title, task_status）
                        conn.execute("""
                            CREATE TABLE checkpoints (
                                thread_id TEXT NOT NULL,
                                snap_id TEXT NOT NULL,
                                state_json TEXT NOT NULL,
                                node_key TEXT DEFAULT '',
                                memo TEXT DEFAULT '',
                                create_ts INTEGER NOT NULL,
                                task_title TEXT DEFAULT '',
                                task_status TEXT DEFAULT 'unknown',
                                PRIMARY KEY (thread_id, snap_id)
                            )
                        """)
                        # 3. 索引
                        conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ts
                            ON checkpoints(thread_id, create_ts DESC)
                        """)
                        conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_checkpoints_task_time
                            ON checkpoints(task_title, create_ts DESC)
                        """)
                        # 4. 迁移存量数据
                        conn.execute("""
                            INSERT INTO checkpoints
                            (thread_id, snap_id, state_json, node_key, memo, meta, create_ts, task_title, task_status)
                            SELECT
                                thread_id,
                                'snap_legacy_' || printf('%d', CAST(
                                    CASE
                                        WHEN updated_at != '' THEN
                                            (strftime('%s', updated_at) * 1000)
                                        ELSE
                                            (strftime('%s', 'now') * 1000)
                                    END AS INTEGER
                                )) || '_' || substr(hex(randomblob(4)), 1, 8),
                                state_json,
                                node_key,
                                '存量历史基线（升级前自动迁移）',
                                CAST(
                                    CASE
                                        WHEN updated_at != '' THEN
                                            (strftime('%s', updated_at) * 1000)
                                        ELSE
                                            (strftime('%s', 'now') * 1000)
                                    END AS INTEGER
                                ),
                                '',
                                'unknown'
                            FROM checkpoints_old
                        """)
                        conn.commit()
                        logger.info("Checkpoint 表迁移完成：单版本 → 多版本复合主键")
                    else:
                        # 已经是新表，检查是否有 task_title, task_status 字段
                        has_task_title = "task_title" in columns
                        has_task_status = "task_status" in columns

                        if not has_task_title:
                            logger.info("增量添加 task_title 字段...")
                            conn.execute("ALTER TABLE checkpoints ADD COLUMN task_title TEXT DEFAULT ''")
                        if not has_task_status:
                            logger.info("增量添加 task_status 字段...")
                            conn.execute("ALTER TABLE checkpoints ADD COLUMN task_status TEXT DEFAULT 'unknown'")

                        # 增量添加 meta 字段（P2-B: 自愈/进化关联 ID）
                        has_meta = "meta" in columns
                        if not has_meta:
                            logger.info("增量添加 meta 字段...")
                            conn.execute("ALTER TABLE checkpoints ADD COLUMN meta TEXT DEFAULT '{}'")

                        # 确保索引存在
                        conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ts
                            ON checkpoints(thread_id, create_ts DESC)
                        """)
                        conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_checkpoints_task_time
                            ON checkpoints(task_title, create_ts DESC)
                        """)
                        conn.commit()
                else:
                    # 全新安装，直接建新表（含 task_title, task_status）
                    conn.execute("""
                        CREATE TABLE checkpoints (
                            thread_id TEXT NOT NULL,
                            snap_id TEXT NOT NULL,
                            state_json TEXT NOT NULL,
                            node_key TEXT DEFAULT '',
                            memo TEXT DEFAULT '',
                            meta TEXT DEFAULT '{}',
                            create_ts INTEGER NOT NULL,
                            task_title TEXT DEFAULT '',
                            task_status TEXT DEFAULT 'unknown',
                            PRIMARY KEY (thread_id, snap_id)
                        )
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ts
                        ON checkpoints(thread_id, create_ts DESC)
                    """)
                    conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_checkpoints_task_time
                        ON checkpoints(task_title, create_ts DESC)
                    """)
                    conn.commit()
            except sqlite3.Error as e:
                logger.error("Checkpoint 表初始化失败: %s", e)
                raise
            finally:
                conn.close()

    def _corruption_log_path(self) -> str:
        """checkpoint 损坏日志路径"""
        log_dir = os.path.join(os.path.dirname(self.db_path), "checkpoint_errors")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d")
        return os.path.join(log_dir, f"corruption_{ts}.log")

    def _log_corruption(self, thread_id: str, operation: str, error: str, state_json_hint: str = "") -> None:
        """将损坏/写入失败记录到独立错误日志（不依赖 DB，防级联失败）"""
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "thread_id": thread_id,
            "operation": operation,
            "error": str(error),
            "state_json_preview": state_json_hint[:500],
        }
        log_path = self._corruption_log_path()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 日志写入失败不抛异常

    # ─── 自动快照（Graph step 每步自动触发）─────────────────

    def save(
        self,
        state: FlowState,
        node_key: str = "",
        meta: Optional[dict] = None,
        task_title: Optional[str] = None,
        task_status: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        保存 State 到 Checkpoint，每次生成独立 snap_id。

        INSERT 而非 INSERT OR REPLACE，永久保留所有历史快照。
        返回生成的 snap_id。

        Args:
            state: 当前 FlowState（含完整目录树等胖状态）
            node_key: Graph 当前执行节点名称
            task_title: 顶层任务名称，默认从 state.project_name 自动提取
            task_status: 任务运行状态 running/finished/error/pause，默认从 state.current_status 提取
            thread_id: 可选，指定 checkpoint thread_id；默认使用 state.instance_id
        Returns:
            snap_id: 本次生成的快照 ID
        """
        snap_id = generate_snap_id()
        now_ms = int(time.time() * 1000)
        state_json = state.model_dump_json()
        title = task_title if task_title is not None else state.project_name
        status = task_status if task_status is not None else state.current_status.value
        tid = thread_id if thread_id is not None else state.instance_id

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO checkpoints
                       (thread_id, snap_id, state_json, node_key, memo, meta, create_ts, task_title, task_status)
                       VALUES (?, ?, ?, ?, '', ?, ?, ?, ?)""",
                    (tid, snap_id, state_json, node_key, json.dumps(meta) if meta else '{}', now_ms, title, status),
                )
                conn.commit()
                logger.debug("Auto snapshot saved: thread=%s, snap=%s, node=%s, title=%s, status=%s",
                             tid, snap_id, node_key, title, status)
                return snap_id
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("Checkpoint 写入失败 [%s]: %s", tid, e)
                self._log_corruption(tid, "save", str(e), state_json[:200])
                return ""
            finally:
                conn.close()

    # ─── 手动基线快照（目录修改前业务主动调用）─────────────

    def manual_snapshot(
        self,
        state: FlowState,
        node_key: str = "manual",
        memo: str = "",
        meta: Optional[dict] = None,
        task_title: Optional[str] = None,
        task_status: Optional[str] = None,
    ) -> str:
        """
        手动打基线快照，带自定义备注。

        使用场景：
          - 修改目录树前主动打快照，传 memo="目录原始基线"
          - 关键节点前备份状态

        Args:
            state: 当前 FlowState
            node_key: 节点名称（默认 manual）
            memo: 自定义备注，用于筛选回滚点
            meta: 快照元数据（bind_evolution_ids, bind_heal_event_ids）
            task_title: 顶层任务名称，默认从 state.project_name 自动提取
            task_status: 任务运行状态，默认从 state.current_status 提取
        Returns:
            snap_id
        """
        snap_id = generate_snap_id()
        now_ms = int(time.time() * 1000)
        state_json = state.model_dump_json()
        title = task_title if task_title is not None else state.project_name
        status = task_status if task_status is not None else state.current_status.value

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """INSERT INTO checkpoints
                       (thread_id, snap_id, state_json, node_key, memo, meta, create_ts, task_title, task_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (state.instance_id, snap_id, state_json, node_key, memo, json.dumps(meta) if meta else '{}', now_ms, title, status),
                )
                conn.commit()
                logger.info("Manual snapshot saved: thread=%s, snap=%s, memo=%s, title=%s, status=%s",
                            state.instance_id, snap_id, memo, title, status)
                return snap_id
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("手动快照写入失败 [%s]: %s", state.instance_id, e)
                self._log_corruption(state.instance_id, "manual_snapshot", str(e), state_json[:200])
                return ""
            finally:
                conn.close()

    # ─── 读取（最新 / 定点 / 列表）──────────────────────────

    def load(self, thread_id: str, snap_id: Optional[str] = None) -> Optional[FlowState]:
        """
        加载 FlowState。

        Args:
            thread_id: 会话 ID
            snap_id: 可选，指定快照 ID。None = 加载最新快照

        Returns:
            FlowState or None
        """
        with self._lock:
            conn = self._get_conn()
            try:
                if snap_id:
                    # 定点加载指定快照
                    row = conn.execute(
                        "SELECT state_json FROM checkpoints WHERE thread_id = ? AND snap_id = ?",
                        (thread_id, snap_id),
                    ).fetchone()
                else:
                    # 加载该会话最新快照
                    row = conn.execute(
                        "SELECT state_json FROM checkpoints WHERE thread_id = ? ORDER BY rowid DESC LIMIT 1",
                        (thread_id,),
                    ).fetchone()

                if row is None:
                    return None

                state = FlowState.model_validate_json(row["state_json"])
                return state
            except (sqlite3.Error, json.JSONDecodeError, KeyError) as e:
                logger.error("Checkpoint 恢复失败 [%s]: %s", thread_id, e)
                return None
            finally:
                conn.close()

    def load_by_snap(self, thread_id: str, snap_id: str) -> Optional[FlowState]:
        """
        按 snap_id 定点读取指定快照完整状态。
        等价于 load(thread_id, snap_id=snap_id)，显式命名更清晰。
        """
        return self.load(thread_id, snap_id=snap_id)

    def list_snapshots(self, thread_id: str) -> list[dict]:
        """
        列出会话全部历史快照元数据（不含完整 state JSON，轻量化）。

        Returns:
            [{snap_id, memo, node_key, create_ts, create_time, task_title, task_status}, ...]
            按时间倒序（最新在前）
        """
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT snap_id, memo, meta, node_key, create_ts, task_title, task_status FROM checkpoints
                       WHERE thread_id = ?
                       ORDER BY rowid DESC""",
                    (thread_id,),
                ).fetchall()

                return [
                    {
                        "snap_id": r["snap_id"],
                        "memo": r["memo"] or "",
                        "meta": json.loads(r["meta"]) if r["meta"] else {},
                        "node_key": r["node_key"] or "",
                        "create_ts": r["create_ts"],
                        "create_time": format_timestamp(r["create_ts"]),
                        "task_title": r["task_title"] or "",
                        "task_status": r["task_status"] or "",
                    }
                    for r in rows
                ]
            except sqlite3.Error as e:
                logger.error("快照列表查询失败 [%s]: %s", thread_id, e)
                return []
            finally:
                conn.close()

    # ─── 多维度筛选查询 ──────────────────────────────────────────

    def list_snapshots_by_filter(
        self,
        thread_id: Optional[str] = None,
        task_title: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        node_key: Optional[str] = None,
        task_status: Optional[str] = None,
        memo: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """
        多维度复合筛选快照元数据（不含 state JSON）。

        Args:
            thread_id: 按会话精确筛选
            task_title: 按任务名称模糊匹配
            start_ts: 起始时间戳（毫秒）
            end_ts: 截止时间戳（毫秒）
            node_key: 按节点名精确匹配
            task_status: 按任务状态精确匹配
            memo: 按备注模糊匹配
            page: 页码（从 1 开始）
            page_size: 每页条数

        Returns:
            (snapshot_list, total_count)
        """
        conditions = []
        params: list = []

        if thread_id:
            conditions.append("thread_id = ?")
            params.append(thread_id)
        if task_title:
            conditions.append("task_title LIKE ?")
            params.append(f"%{task_title}%")
        if start_ts is not None:
            conditions.append("create_ts >= ?")
            params.append(start_ts)
        if end_ts is not None:
            conditions.append("create_ts <= ?")
            params.append(end_ts)
        if node_key:
            conditions.append("node_key = ?")
            params.append(node_key)
        if task_status:
            conditions.append("task_status = ?")
            params.append(task_status)
        if memo:
            conditions.append("memo LIKE ?")
            params.append(f"%{memo}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._lock:
            conn = self._get_conn()
            try:
                # 总数
                count_row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM checkpoints WHERE {where_clause}",
                    params,
                ).fetchone()
                total = count_row["cnt"] if count_row else 0

                # 分页数据
                offset = (page - 1) * page_size
                rows = conn.execute(
                    f"""SELECT snap_id, memo, meta, node_key, create_ts, task_title, task_status, thread_id
                        FROM checkpoints WHERE {where_clause}
                        ORDER BY create_ts DESC
                        LIMIT ? OFFSET ?""",
                    params + [page_size, offset],
                ).fetchall()

                result = [
                    {
                        "snap_id": r["snap_id"],
                        "memo": r["memo"] or "",
                        "meta": json.loads(r["meta"]) if r["meta"] else {},
                        "node_key": r["node_key"] or "",
                        "create_ts": r["create_ts"],
                        "create_time": format_timestamp(r["create_ts"]),
                        "task_title": r["task_title"] or "",
                        "task_status": r["task_status"] or "",
                        "thread_id": r["thread_id"],
                    }
                    for r in rows
                ]
                return result, total
            except sqlite3.Error as e:
                logger.error("快照筛选查询失败: %s", e)
                return [], 0
            finally:
                conn.close()

    def load_by_node(self, thread_id: str, node_key: str) -> list[dict]:
        """
        按会话 + 节点名查询所有历史快照（用于节点回滚场景）。

        Returns:
            [{snap_id, memo, create_ts, create_time, task_status}, ...]
        """
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT snap_id, memo, meta, create_ts, task_status
                       FROM checkpoints
                       WHERE thread_id = ? AND node_key = ?
                       ORDER BY create_ts DESC""",
                    (thread_id, node_key),
                ).fetchall()
                return [
                    {
                        "snap_id": r["snap_id"],
                        "memo": r["memo"] or "",
                        "meta": json.loads(r["meta"]) if r["meta"] else {},
                        "create_ts": r["create_ts"],
                        "create_time": format_timestamp(r["create_ts"]),
                        "task_status": r["task_status"] or "",
                    }
                    for r in rows
                ]
            except sqlite3.Error as e:
                logger.error("节点快照查询失败 [%s/%s]: %s", thread_id, node_key, e)
                return []
            finally:
                conn.close()

    def rollback_to_node_snap(self, thread_id: str, snap_id: str, target_node: str) -> Optional[FlowState]:
        """
        节点级回滚：读取指定节点快照，截断该节点后的执行追踪，
        并重置游标状态、清除门禁标记。

        回滚上下文重置包含：
          1. 截断 execution_trace（保留 target_node 及之前）
          2. 清除冷冻状态（is_frozen / freeze_reason）
          3. 重置门禁布尔（allow_deploy / skip_test_allowed / code_review_passed / acceptance_passed）
          4. 清除 metadata 中 RESUMING/SUBGRAPH_RESUMING 等游标标记
          5. 更新 current_status 为 PENDING（回滚后需重新审批）

        Args:
            thread_id: 会话 ID
            snap_id: 目标快照 ID
            target_node: 回滚目标节点名

        Returns:
            回滚后的 FlowState，快照不存在返回 None
        """
        state = self.load(thread_id, snap_id=snap_id)
        if state is None:
            return None

        # 1. 截断执行轨迹：保留 target_node 之前（含自身）的记录
        truncated = []
        found = False
        for entry in state.execution_trace:
            truncated.append(entry)
            if entry.node_type.value == target_node or entry.output_summary.startswith(target_node):
                found = True
                break

        if found:
            state.execution_trace = truncated

        # 2. 清除冷冻状态
        if state.is_frozen:
            state.is_frozen = False
            state.freeze_reason = ""
            logger.info("回滚上下文重置: 清除冷冻状态 [%s]", thread_id)

        # 3. 重置门禁布尔
        state.allow_deploy = False
        state.skip_test_allowed = False
        state.code_review_passed = False
        state.acceptance_passed = False

        # 4. 清除游标标记（metadata 中与子图/恢复相关的键）
        resume_keys = [k for k in state.metadata if "RESUMING" in k.upper() or "resuming" in k.lower()]
        for k in resume_keys:
            del state.metadata[k]
            logger.debug("回滚清除 metadata 键: %s", k)

        # 5. 重置状态为 PENDING（回滚后需重新审批流转）
        if state.current_status not in (FlowStatus.PENDING, FlowStatus.FROZEN):
            logger.info("回滚重置状态: %s → PENDING [%s]", state.current_status.value, thread_id)
            state.current_status = FlowStatus.PENDING

        state.updated_at = datetime.utcnow().isoformat()
        return state

    # ─── 删除 & 清理 ─────────────────────────────────────────

    def delete_snapshot(self, thread_id: str, snap_id: str) -> bool:
        """删除指定快照"""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM checkpoints WHERE thread_id = ? AND snap_id = ?",
                    (thread_id, snap_id),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error("快照删除失败 [%s/%s]: %s", thread_id, snap_id, e)
                return False
            finally:
                conn.close()

    def delete_by_snap_id(self, snap_id: str) -> bool:
        """
        按 snap_id 删除快照（自动查找所属 thread_id）。

        适用于前端只持有 snap_id 的场景。
        """
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT thread_id FROM checkpoints WHERE snap_id = ? LIMIT 1",
                    (snap_id,),
                ).fetchone()
                if not row:
                    logger.warning("快照不存在: snap_id=%s", snap_id)
                    return False
                thread_id = row["thread_id"]
                conn.execute(
                    "DELETE FROM checkpoints WHERE thread_id = ? AND snap_id = ?",
                    (thread_id, snap_id),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error("按 snap_id 删除失败 [%s]: %s", snap_id, e)
                return False
            finally:
                conn.close()

    def cleanup_old_snapshots(self, thread_id: str, keep_days: int = 30) -> int:
        """
        清理指定会话中超过 keep_days 天的非基线快照。

        基线保护（三重）：
          1. memo 含「基线」 → 永久保留
          2. memo 含「project_finish」「emergency_exit」 → 永久保留
          3. 清理前校验基线数量不变

        Returns:
            deleted_count: 删除的快照数量
        """
        cutoff = int(time.time() * 1000) - (keep_days * 86400 * 1000)
        with self._lock:
            conn = self._get_conn()
            try:
                # 前置校验：统计基线快照数量，清理后对比
                before_baseline = conn.execute(
                    """SELECT COUNT(*) FROM checkpoints
                       WHERE thread_id = ?
                       AND (memo LIKE '%基线%' OR memo LIKE '%project_finish%' OR memo LIKE '%emergency_exit%'
                            OR memo LIKE '%manual%')""",
                    (thread_id,),
                ).fetchone()[0]

                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute(
                    """DELETE FROM checkpoints
                       WHERE thread_id = ?
                       AND create_ts < ?
                       AND (memo IS NULL
                            OR (memo NOT LIKE '%基线%'
                                AND memo NOT LIKE '%project_finish%'
                                AND memo NOT LIKE '%emergency_exit%'
                                AND memo NOT LIKE '%manual%'))""",
                    (thread_id, cutoff),
                )
                conn.commit()
                deleted = cursor.rowcount

                # 后置校验：确认基线没少
                after_baseline = conn.execute(
                    """SELECT COUNT(*) FROM checkpoints
                       WHERE thread_id = ?
                       AND (memo LIKE '%基线%' OR memo LIKE '%project_finish%' OR memo LIKE '%emergency_exit%'
                            OR memo LIKE '%manual%')""",
                    (thread_id,),
                ).fetchone()[0]

                if before_baseline != after_baseline:
                    logger.error("基线快照保护异常: before=%d after=%d [%s]",
                                 before_baseline, after_baseline, thread_id)

                if deleted > 0:
                    logger.info("清理过期快照 [%s]: %d 个 (基线: %d → %d)",
                                thread_id, deleted, before_baseline, after_baseline)
                return deleted
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("快照清理失败 [%s]: %s", thread_id, e)
                return 0
            finally:
                conn.close()

    # ─── 兼容旧接口 ──────────────────────────────────────────

    def list_active(self) -> list[dict]:
        """
        列出所有活跃 Checkpoint（有快照的会话）。

        返回每个会话的最新一条快照元数据。
        """
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT c.thread_id, c.node_key, c.create_ts, c.task_title, c.task_status
                       FROM checkpoints c
                       INNER JOIN (
                           SELECT thread_id, MAX(create_ts) as max_ts
                           FROM checkpoints GROUP BY thread_id
                       ) latest ON c.thread_id = latest.thread_id AND c.create_ts = latest.max_ts
                       ORDER BY c.create_ts DESC"""
                ).fetchall()
                return [
                    {
                        "thread_id": r["thread_id"],
                        "node_key": r["node_key"],
                        "updated_at": format_timestamp(r["create_ts"]),
                        "task_title": r["task_title"] or "",
                        "task_status": r["task_status"] or "",
                    }
                    for r in rows
                ]
            except sqlite3.Error as e:
                logger.error("活跃 Checkpoint 查询失败: %s", e)
                return []
            finally:
                conn.close()

    # 增量优化202607：按 task_meta.task_id 检索快照
    def find_snapshots_by_task_id(self, task_id: str) -> list[dict]:
        """
        通过 task_meta.task_id 匹配所有关联快照。
        由于 state_json 为 JSON 文本，使用 LIKE 模糊匹配。

        Returns:
            [{snap_id, thread_id, create_ts, node_key, task_status}, ...]
        """
        pattern = f"%{task_id}%"
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT snap_id, thread_id, node_key, create_ts, task_status
                       FROM checkpoints
                       WHERE state_json LIKE ?
                       ORDER BY create_ts ASC""",
                    (pattern,),
                ).fetchall()
                result = []
                for r in rows:
                    result.append({
                        "snap_id": r["snap_id"],
                        "thread_id": r["thread_id"],
                        "node_key": r["node_key"] or "",
                        "create_ts": r["create_ts"],
                        "create_time": format_timestamp(r["create_ts"]),
                        "task_status": r["task_status"] or "",
                    })
                return result
            except sqlite3.Error as e:
                logger.error("按 task_id 检索快照失败 [%s]: %s", task_id, e)
                return []
            finally:
                conn.close()

    def get_earliest_baseline_snapshot(self, task_id: str) -> Optional[str]:
        """
        获取指定 task_id 的最早基线快照 ID。
        用于回滚时恢复至任务起点。
        """
        snaps = self.find_snapshots_by_task_id(task_id)
        if not snaps:
            return None
        # ASC 排序，第一条为最早
        return snaps[0].get("snap_id")

    def count(self) -> int:
        """快照总数"""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) as cnt FROM checkpoints").fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def exists(self, thread_id: str) -> bool:
        """检查指定会话是否有快照"""
        return self.load(thread_id) is not None


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_default_checkpointer: Optional[SqliteCheckpointer] = None


def get_checkpointer() -> SqliteCheckpointer:
    """获取全局 Checkpointer 单例"""
    global _default_checkpointer
    if _default_checkpointer is None:
        _default_checkpointer = SqliteCheckpointer()
    return _default_checkpointer


# ═══════════════════════════════════════════════════════════════
# 自动基线快照 — 三类场景统一入口
# ═══════════════════════════════════════════════════════════════

def auto_create_baseline_snapshot(
    thread_id: str,
    memo_suffix: str = "",
    task_status: str = "unknown",
    state: Optional["FlowState"] = None,
    meta: Optional[dict] = None,
) -> Optional[str]:
    """
    自动创建基线快照，三类触发场景统一调用。

    场景 1: flow_finish — 会话完整执行结束
    场景 2: enter_retrospection — 进入复盘节点
    场景 3: project_close — 项目整体完结

    Args:
        thread_id: 会话 ID
        memo_suffix: 备注前缀文案（如"会话完整执行完成"）
        task_status: 快照任务状态（finished / running / closed）
        state: 可选的 FlowState，不传则从 checkpointer 加载

    Returns:
        snap_id 或 None（失败时）
    """
    checkpointer = get_checkpointer()

    # 如未传 state，从 checkpointer 按 thread_id 加载
    if state is None:
        state = checkpointer.load(thread_id)

    if not state:
        logger.warning("自动基线快照失败: 会话 %s 无 FlowState", thread_id)
        return None

    # memo 后缀校验：非空且不为 "unknown" / "unnamed" 等占位值
    memo_suffix = (memo_suffix or "").strip()
    if not memo_suffix or memo_suffix.lower() in ("unknown", "unnamed", "none", "null"):
        memo_suffix = "auto_baseline"
        logger.warning("基线快照备注后缀无效，使用默认值")

    task_title = state.project_name or "未命名任务"
    memo = f"{memo_suffix}自动基线快照"

    snap_id = checkpointer.manual_snapshot(
        state,
        node_key="auto_baseline",
        memo=memo,
        meta=meta,
        task_title=task_title,
        task_status=task_status,
    )

    # 双系统联动：SQLite 快照创建后，同步触发 ZIP 归档并传入 snap_id
    if snap_id:
        try:
            pack_script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "scripts", "checkpoint-pack.sh",
            )
            if os.path.exists(pack_script) and os.access(pack_script, os.X_OK):
                output_base = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "checkpoint",
                )
                subprocess.Popen(
                    ["bash", pack_script, thread_id, "manual",
                     "--state-snapshot-id", snap_id, output_base],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("双系统联动: SQLite snap_id=%s → ZIP 归档触发", snap_id)
        except Exception as e:
            logger.warning("双系统联动 ZIP 归档触发失败 (非阻塞): %s", e)

    return snap_id
