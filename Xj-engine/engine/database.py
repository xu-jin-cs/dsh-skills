"""Xj-engine standalone 数据库入口。

替代原平台数据库模块：
- Base：SQLAlchemy DeclarativeBase
- engine：SQLite 引擎，默认 ./data/engine.db，可用 XJ_ENGINE_DB_URL 覆盖
- SessionLocal：会话工厂
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "engine.db"
_DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = __import__("os").environ.get(
    "XJ_ENGINE_DB_URL",
    f"sqlite:///{_DEFAULT_DB}",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_size=20,
    max_overflow=30,
    pool_timeout=60,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
