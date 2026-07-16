"""In-process TTL cache for reference data.

Why this exists
---------------
The Supabase Postgres pooler this app talks to lives in ``ap-southeast-1``
(Singapore). Every round-trip from an IPv4 client costs ~260ms of pure network
latency, and opening a *new* pooled connection costs several seconds. The data
itself is tiny, so the dominant cost of almost every request is the number of
DB round-trips, not query execution.

A short-TTL in-process cache turns a repeat read (the same user identity on every
authenticated request, the category list, the company record, theme/settings)
from a 260ms round-trip into a dict lookup (~0ms). This is the single biggest
lever available without moving the database closer.

Design
------
* **In-process only** (no Redis). The backend is single-process here
  (see ``project-security-hardening`` — the rate limiter is single-process too),
  so a module-level dict is sufficient and has zero deploy cost. If this ever
  scales to multiple workers, swap the backing store for Redis behind the same
  ``get``/``set``/``invalidate`` API.
* **TTL per entry.** Stale window is bounded to seconds. Writers also call
  ``invalidate`` / ``invalidate_prefix`` so a change is reflected immediately on
  the process that made it.
* **Async single-flight** (``get_or_set``): when many concurrent requests miss
  the same key at once (a dashboard fan-out), only ONE runs the loader; the rest
  await its result. This prevents a cold-cache request burst from stampeding the
  DB with N identical cross-region queries.
* **Negative caching is the caller's choice** — ``get_or_set`` caches whatever
  the loader returns, including ``None``; pass ``cache_none=False`` to skip
  caching empty results.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

# key -> (value, expires_at_monotonic)
_store: dict[str, tuple[Any, float]] = {}
# key -> asyncio.Lock, for single-flight loading
_locks: dict[str, asyncio.Lock] = {}

# Lightweight hit/miss counters for the /admin diagnostics endpoint.
_stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0}

# Sentinel so callers can cache a real ``None`` value and still distinguish it
# from "absent".
_MISS = object()


def get(key: str) -> Any:
    """Return the cached value for ``key`` or the ``_MISS`` sentinel if absent/expired."""
    entry = _store.get(key)
    if entry is None:
        _stats["misses"] += 1
        return _MISS
    value, expires_at = entry
    if expires_at < time.monotonic():
        _store.pop(key, None)
        _stats["misses"] += 1
        return _MISS
    _stats["hits"] += 1
    return value


def set(key: str, value: Any, ttl: float) -> None:
    """Cache ``value`` under ``key`` for ``ttl`` seconds."""
    _store[key] = (value, time.monotonic() + ttl)
    _stats["sets"] += 1


def get_default(key: str, default: Any = None) -> Any:
    """Like get(), but returns `default` instead of the internal _MISS sentinel
    when the key is absent/expired — for callers outside this module that
    shouldn't need to know about _MISS."""
    value = get(key)
    return default if value is _MISS else value


def invalidate(*keys: str) -> None:
    """Drop one or more exact keys."""
    for k in keys:
        if _store.pop(k, None) is not None:
            _stats["invalidations"] += 1


def invalidate_prefix(prefix: str) -> None:
    """Drop every key starting with ``prefix`` (e.g. ``"categories:"``)."""
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
        _stats["invalidations"] += 1


def clear() -> None:
    """Drop the whole cache (used by tests)."""
    _store.clear()
    _locks.clear()


async def get_or_set(
    key: str,
    ttl: float,
    loader: Callable[[], Awaitable[Any]],
    *,
    cache_none: bool = True,
) -> Any:
    """Return ``key`` from cache, or run ``loader`` once and cache its result.

    Single-flight: concurrent misses on the same key share one loader run.
    """
    cached = get(key)
    if cached is not _MISS:
        return cached

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # Re-check: another waiter may have populated it while we waited.
        cached = get(key)
        if cached is not _MISS:
            return cached
        value = await loader()
        if value is not None or cache_none:
            set(key, value, ttl)
        return value
    # (lock intentionally left in _locks; it's reused and cheap. A periodic GC
    # could prune locks for evicted keys, but the working set here is small.)


# ── Generation counters ──────────────────────────────────────────────────────
# For data that's read-hot but written from many scattered places (so per-key
# invalidation is unreliable), we don't cache the value under a fixed key —
# instead the cache key embeds a monotonic "generation" for a logical dataset.
# Any writer bumps the generation, which atomically orphans every cached entry
# built against the old one (they simply stop being looked up and expire on TTL).
# This makes a cache correct-by-construction without hunting down every writer:
# only the few write helpers that touch the dataset call bump_generation().
_generations: dict[str, int] = {}


def generation(name: str) -> int:
    return _generations.get(name, 0)


def bump_generation(name: str) -> None:
    _generations[name] = _generations.get(name, 0) + 1


def stats() -> dict:
    total = _stats["hits"] + _stats["misses"]
    hit_rate = (_stats["hits"] / total) if total else 0.0
    return {
        **_stats,
        "entries": len(_store),
        "hit_rate": round(hit_rate, 3),
    }


# ── TTL constants (seconds) ──────────────────────────────────────────────────
# Tuned for "changes appear within a few seconds" while killing the repeat
# cross-region round-trips. Writers invalidate their own keys for instant
# consistency on the writing process.
TTL_USER = 30          # user identity re-fetched on every authed request
TTL_REFERENCE = 60     # categories, settings, company — change rarely
TTL_DASHBOARD = 60     # dashboard/MIS summaries — expensive aggregations
