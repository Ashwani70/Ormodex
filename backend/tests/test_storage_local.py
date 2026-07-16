"""Unit tests for the local-filesystem object store in core.storage.

Guards that uploaded objects (company logos, product images) persist to disk
and survive a server restart — they previously lived only in memory and were
lost on every restart.
"""
import importlib

import pytest


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    """Reload core.storage pointed at a temp dir, so tests never touch the real
    backend/uploads directory."""
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path))
    import core.storage as storage
    importlib.reload(storage)
    return storage


def test_put_then_get_roundtrip(local_storage):
    path = "gew-erp/products/u1/logo.png"
    local_storage.put_object(path, b"\x89PNG-bytes", "image/png")
    data, ctype = local_storage.get_object(path)
    assert data == b"\x89PNG-bytes"
    assert ctype == "image/png"


def test_survives_restart(local_storage, tmp_path, monkeypatch):
    """The whole point: an upload must still be readable after the process
    restarts (simulated by reloading the module, which clears all in-memory
    state)."""
    path = "gew-erp/products/u1/logo.png"
    local_storage.put_object(path, b"persisted", "image/webp")

    # Simulate a fresh process: reload wipes module-level state.
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path))
    import core.storage as storage
    importlib.reload(storage)

    data, ctype = storage.get_object(path)
    assert data == b"persisted"
    assert ctype == "image/webp"


def test_missing_object_raises(local_storage):
    with pytest.raises(FileNotFoundError):
        local_storage.get_object("gew-erp/products/u1/does-not-exist.png")


def test_path_traversal_is_rejected(local_storage):
    # A crafted path must never escape LOCAL_STORAGE_DIR.
    with pytest.raises(ValueError):
        local_storage.put_object("../../etc/passwd", b"x", "text/plain")
    with pytest.raises(ValueError):
        local_storage.get_object("../../../secret")


def test_nested_paths_create_directories(local_storage):
    path = "gew-erp/products/deep/nested/dir/img.gif"
    local_storage.put_object(path, b"gif", "image/gif")
    data, _ = local_storage.get_object(path)
    assert data == b"gif"
