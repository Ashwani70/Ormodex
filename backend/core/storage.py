"""Emergent object storage client.

Used for uploading product images and other binary assets.
Storage key is initialised once and reused across requests.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "gew-erp")

_storage_key: str | None = None
_mock_storage: dict[str, tuple[bytes, str]] = {}
_use_mock_storage = False


def init_storage() -> str:
    global _storage_key, _use_mock_storage
    if _storage_key:
        return _storage_key
    key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not key or key == "testkey":
        logger.warning("Using mock in-memory storage (invalid/missing key)")
        _use_mock_storage = True
        _storage_key = "mock_key"
        return _storage_key

    try:
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": key}, timeout=10)
        resp.raise_for_status()
        _storage_key = resp.json()["storage_key"]
    except Exception as e:
        logger.warning(f"Emergent object storage init failed, falling back to mock: {e}")
        _use_mock_storage = True
        _storage_key = "mock_key"
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if _use_mock_storage:
        _mock_storage[path] = (data, content_type)
        return {"path": path, "size": len(data), "content_type": content_type}

    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code == 403:
        # storage_key may have expired — re-init once
        global _storage_key
        _storage_key = None
        key = init_storage()
        if _use_mock_storage:
            _mock_storage[path] = (data, content_type)
            return {"path": path, "size": len(data), "content_type": content_type}
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    key = init_storage()
    if _use_mock_storage:
        if path in _mock_storage:
            return _mock_storage[path]
        raise FileNotFoundError(f"Mock file not found: {path}")

    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key},
        timeout=60,
    )
    if resp.status_code == 403:
        global _storage_key
        _storage_key = None
        key = init_storage()
        if _use_mock_storage:
            if path in _mock_storage:
                return _mock_storage[path]
            raise FileNotFoundError(f"Mock file not found: {path}")
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

