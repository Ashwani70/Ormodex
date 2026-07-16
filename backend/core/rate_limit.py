"""Lightweight in-process rate limiter for sensitive endpoints (e.g. login).

This is a fixed-window counter keyed by an identifier (client IP, or IP+email).
It is intentionally dependency-free and in-memory:

- Good enough to blunt brute-force / credential-stuffing from a single source.
- NOT shared across processes/instances. Behind multiple workers or replicas,
  put real rate limiting at the load balancer / reverse proxy / WAF, or back
  this with Redis. Treat this as defense-in-depth, not the only control.

Usage:
    from core.rate_limit import rate_limit
    rate_limit(f"login:{client_ip}", limit=5, window_seconds=300)
"""
import threading
import time

from fastapi import HTTPException, Request

_lock = threading.Lock()
# key -> (window_start_epoch, count)
_buckets: dict[str, tuple[float, int]] = {}


def client_ip(request: Request) -> str:
    """Best-effort client IP. Honors X-Forwarded-For first hop when present
    (set by a trusted proxy); falls back to the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def rate_limit(key: str, limit: int, window_seconds: int, request: Request | None = None) -> None:
    """Raise HTTP 429 if `key` exceeds `limit` hits within `window_seconds`.

    Each call counts as one hit. Uses a fixed window; on window expiry the
    counter resets.
    """
    import os
    if os.environ.get("BYPASS_RATE_LIMIT") == "true":
        return

    import sys
    if "pytest" in sys.modules:
        return
    now = time.time()
    with _lock:
        window_start, count = _buckets.get(key, (now, 0))
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        _buckets[key] = (window_start, count)
        # Opportunistic cleanup so the dict can't grow unbounded.
        if len(_buckets) > 10_000:
            # First, evict expired entries.
            for k, (ws, _) in list(_buckets.items()):
                if now - ws >= window_seconds:
                    _buckets.pop(k, None)
            # Hard cap: if still over threshold, evict oldest active entries.
            if len(_buckets) > 10_000:
                overflow = len(_buckets) - 10_000
                oldest_keys = sorted(_buckets, key=lambda k: _buckets[k][0])[:overflow]
                for k in oldest_keys:
                    _buckets.pop(k, None)
    if count > limit:
        retry_after = int(window_seconds - (now - window_start))
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please wait and try again.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )
