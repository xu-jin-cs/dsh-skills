"""通用文档 ETL MinIO 操作封装（前缀隔离）。"""

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 环境默认值：生产环境必须通过环境变量注入凭据，禁止在代码中写死密码
_MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
_MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "etl_user")
_MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
_MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"


class MinIOError(Exception):
    pass


def _get_client():
    try:
        import urllib3
        from minio import Minio
    except ImportError as exc:
        raise MinIOError("minio / urllib3 not installed") from exc
    return Minio(
        _MINIO_ENDPOINT,
        access_key=_MINIO_ACCESS_KEY,
        secret_key=_MINIO_SECRET_KEY,
        secure=_MINIO_SECURE,
        region="us-east-1",
        http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=10)),
    )


def _resolve_config_prefix(prefix_type: str) -> str:
    if prefix_type == "source":
        return os.getenv("ETL_MINIO_SOURCE_PREFIX", "general_doc_source/")
    if prefix_type == "tmp":
        return os.getenv("ETL_MINIO_TMP_PREFIX", "general_doc_tmp/")
    raise ValueError(f"Unknown prefix type: {prefix_type}")


def upload_bytes(bucket: str, object_key: str, data: bytes) -> str:
    """上传字节到 MinIO，返回 object_key。"""
    try:
        client = _get_client()
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(bucket, object_key, BytesIO(data), length=len(data))
        return object_key
    except Exception as exc:
        logger.warning("MinIO upload failed: %s", exc)
        raise MinIOError(str(exc)) from exc


def download_bytes(bucket: str, object_key: str) -> bytes:
    try:
        client = _get_client()
        response = client.get_object(bucket, object_key)
        return response.read()
    except Exception as exc:
        logger.warning("MinIO download failed: %s", exc)
        raise MinIOError(str(exc)) from exc


def delete_object(bucket: str, object_key: str) -> None:
    try:
        client = _get_client()
        client.remove_object(bucket, object_key)
    except Exception as exc:
        logger.warning("MinIO delete failed: %s", exc)
        raise MinIOError(str(exc)) from exc


def local_mirror_path(object_key: str, root: Optional[str] = None) -> Path:
    """当 MinIO 不可用时使用的本地镜像路径。"""
    root = root or os.getenv("ETL_MINIO_FALLBACK_LOCAL_DIR", "data/general_doc_local")
    return Path(root) / object_key
