"""Local filesystem object storage.

Used for uploading product images, company logos, and other binary assets.
Objects are stored on disk under LOCAL_STORAGE_DIR so uploads survive server
restarts. Each object is a data file plus a `.meta.json` sidecar holding its
content type.

Public API: ``init_storage``, ``put_object``, ``get_object``, ``APP_NAME``.
"""
import os
import json
import logging
import pathlib

logger = logging.getLogger(__name__)

APP_NAME = os.environ.get("APP_NAME", "gew-erp")

# Root directory for stored objects. Defaults to a folder next to the backend
# package; override with LOCAL_STORAGE_DIR in production (e.g. a mounted volume).
LOCAL_STORAGE_DIR = os.environ.get(
    "LOCAL_STORAGE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"),
)

_initialised = False


def _local_paths(path: str) -> tuple[str, str]:
    """Map a storage path to (data_file, meta_file) on disk, guarding against
    path traversal so a crafted path can never escape LOCAL_STORAGE_DIR."""
    base = pathlib.Path(LOCAL_STORAGE_DIR).resolve()
    target = (base / path).resolve()
    if base != target and base not in target.parents:
        raise ValueError(f"Unsafe storage path: {path!r}")
    return str(target), str(target) + ".meta.json"


def init_storage() -> str:
    """Ensure the storage root exists. Returns the resolved storage directory.

    Kept for backwards compatibility with startup hooks that call it once.
    """
    global _initialised
    if not _initialised:
        os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
        logger.info("Using local filesystem storage at %s", LOCAL_STORAGE_DIR)
        _initialised = True
    return LOCAL_STORAGE_DIR


def put_object(path: str, data: bytes, content_type: str) -> dict:
    init_storage()
    data_file, meta_file = _local_paths(path)
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    with open(data_file, "wb") as f:
        f.write(data)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"content_type": content_type, "size": len(data)}, f)
    return {"path": path, "size": len(data), "content_type": content_type}


def get_object(path: str) -> tuple[bytes, str]:
    init_storage()
    data_file, meta_file = _local_paths(path)
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"File not found: {path}")
    with open(data_file, "rb") as f:
        data = f.read()
    content_type = "application/octet-stream"
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            content_type = json.load(f).get("content_type", content_type)
    except (OSError, ValueError):
        pass
    return data, content_type
