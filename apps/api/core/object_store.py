# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import io
from pathlib import Path

from core.config import config

_LOCAL_ROOT = Path(__file__).resolve().parent / "data" / "attachments"


def _production() -> bool:
    return config.RUNTIME_PROFILE.lower() in {"production", "prod"}


def _client():
    if not config.OBJECT_STORAGE_ENDPOINT:
        if _production():
            raise RuntimeError("OBJECT_STORAGE_ENDPOINT is required in production")
        return None
    from minio import Minio
    return Minio(config.OBJECT_STORAGE_ENDPOINT, access_key=config.OBJECT_STORAGE_ACCESS_KEY,
                 secret_key=config.OBJECT_STORAGE_SECRET_KEY, secure=config.OBJECT_STORAGE_SECURE)


def ensure_bucket() -> None:
    client = _client()
    if client is None:
        _LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        return
    if not client.bucket_exists(config.OBJECT_STORAGE_BUCKET):
        client.make_bucket(config.OBJECT_STORAGE_BUCKET)


def put(key: str, data: bytes, content_type: str) -> None:
    ensure_bucket()
    client = _client()
    if client is None:
        target = (_LOCAL_ROOT / key).resolve()
        if _LOCAL_ROOT.resolve() not in target.parents:
            raise ValueError("Invalid object key")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return
    client.put_object(config.OBJECT_STORAGE_BUCKET, key, io.BytesIO(data), len(data), content_type=content_type)


def get(key: str) -> bytes:
    client = _client()
    if client is None:
        target = (_LOCAL_ROOT / key).resolve()
        if _LOCAL_ROOT.resolve() not in target.parents:
            raise ValueError("Invalid object key")
        return target.read_bytes()
    response = client.get_object(config.OBJECT_STORAGE_BUCKET, key)
    try:
        return response.read()
    finally:
        response.close(); response.release_conn()
