"""Legacy migration helpers.

These date from the MongoDB era. The data layer is now PostgreSQL (SQLAlchemy
models + Alembic migrations under ``alembic/``), so the Mongo-specific schema
operations below are no-ops kept only so the legacy ``migration_0NN`` scripts
still import cleanly. They are not part of the active migration path.
"""
from typing import Any


async def collmod_safe(db: Any, collection: str, validator: dict) -> None:
    """No-op stand-in for the old MongoDB ``collMod`` validator helper.

    On PostgreSQL, schema/constraints are enforced by the ORM models and DDL,
    so applying a Mongo JSON-Schema validator is meaningless. Retained as a
    no-op to keep legacy migration scripts importable.
    """
    return None
