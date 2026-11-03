"""测试会话级隔离（2026-11-04 内核回归轮引入）。

必须在 engine.database 首次 import 前生效（DATABASE_URL 为 import 期解析）：
内核/状态库/审计一律落本目录临时 SQLite，绝不触碰生产 data/engine.db。
"""
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="xjengine_test_db_")
os.environ["XJ_ENGINE_DB_URL"] = f"sqlite:///{_TEST_DB_DIR}/test_engine.db"
