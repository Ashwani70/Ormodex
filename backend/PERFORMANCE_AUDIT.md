# ERP Performance Audit & Optimization — 2026-06-26

FastAPI + React + Supabase PostgreSQL. Reported symptom: **every page 30–60 s to load.**

## TL;DR

| Scenario | Before | After (warm) | After (cold) |
|---|---:|---:|---:|
| Dashboard load | 30–60 s | **9 ms** | 2.6 s (once / 20 s) |
| 12-request page fan-out (real first paint) | 30–60 s | **57–63 ms** | 2.7 s |
| `/auth/me` (runs on every authed request) | 442 ms | **6 ms** | — |
| `/company/active` | 444 ms | **5 ms** | — |
| `/theme-settings/active` | 452 ms | **6 ms** | — |
| `/categories` | 741 ms | **10 ms** | — |
| `/products` (live stock) | 2170–2793 ms | **5 ms** | 1.5 s |

Cache hit-rate in steady state: **~88 %**. Targets (dashboard < 1 s warm, API < 500 ms warm, queries < 100 ms) are met on every cached path.

---

## Root cause (measured, not guessed)

The database is the Supabase pooler in **`ap-southeast-1` (Singapore)**, accessed from India over the transaction pooler (`:6543`). Raw measurements from this machine:

| Operation | Time | What it is |
|---|---:|---|
| Cold connect | **6,421 ms** | TLS + auth handshake to open a NEW pooled connection |
| First query after connect | 2,688 ms | extra warmup on a fresh connection |
| Warm round-trip (`SELECT 1`) | **~260 ms** | pure India→Singapore network RTT |
| `count(products)` — 13 rows | 274 ms | ~100 % network; the data is trivial |
| `EXPLAIN ANALYZE` execution time | **0.04 ms** | actual query work is negligible |

**Conclusion:** this is a *network-distance* problem, not a query problem. Tables hold a handful of rows; `EXPLAIN ANALYZE` shows 0.04 ms execution against ~470 ms wall — **>99.9 % of every request is network round-trip.** The 30–60 s loads came from three compounding effects:

1. **Per-request auth round-trip.** `get_current_user` re-fetched the user row from Singapore on *every* authenticated request (~260 ms each). A page firing ~10 requests paid ~2.6 s of redundant identical user lookups.
2. **Cold-connect storms.** A page that fans out parallel requests against a cold/undersized pool forced each new connection to pay the **6.4 s** handshake — concurrently, while the user waited.
3. **Sequential round-trips per endpoint.** Each `await db.*` adds 260 ms; chatty endpoints (dashboard = 9, theme = 3) stacked up.

So the only levers that matter here are: **eliminate round-trips (cache), eliminate cold connects (warm the pool), and reduce per-endpoint round-trip count.** Index/query tuning is a no-op at this scale (and the schema is already richly indexed).

---

## What was changed

### 1. In-process TTL cache — `core/cache.py` (new)
Short-TTL, single-process cache with **async single-flight** (a concurrent miss-burst runs the loader once; everyone else awaits it — prevents cache-cold stampedes). TTLs: user 30 s, reference data 60 s, dashboards 20 s. Hit/miss stats exposed.

### 2. Cached `get_current_user` — `core/auth_utils.py`
The single highest-leverage fix: the per-request user lookup is now cache-served (`user:<id>`, 30 s). Writes that change auth-relevant fields invalidate the key. **442 ms → 6 ms** on every authenticated request.

### 3. Centralized cache invalidation — `core/_mongo_compat.py`
Rather than sprinkling `invalidate()` across 50+ routers (easy to miss one), **every write path** (`update_one`/`update_many`/`delete_*`/`insert_*`/`find_one_and_update`/upsert) calls `_invalidate_caches()`. It targets the matching cache keys for `users`, `product_categories`, `theme_settings`, `companies`, and bumps a **generation counter** for `products`/`stock_items`/`stock_ledger_entries`. `crud_create/update/delete` (which bypass the shim) bump the generation too.

### 4. Cached endpoints
- `/dashboard/summary` — whole computed payload cached 20 s (single-tenant). 9 round-trips → 0 on a hit. **Single-flight** means a multi-tab refresh burst computes once.
- `/categories` (default list), `/company/active`, `/theme-settings/active`, `/products` (default list) — all cached; `/products` is **generation-guarded** so any stock/product write orphans the cached list immediately (no stale on-hand qty).
- `/theme-settings/active` also now reuses the cached user loader instead of its own user round-trip.

### 5. Cold-connect storm fix — `core/db.py` `warm_pool()`
Now warms the **full `pool_size`** in parallel on boot (wall cost ≈ one cold connect, not 15 sequential). The first real page-load burst reuses warm connections instead of paying 6.4 s handshakes. (Prior session already fixed `pool_pre_ping`/`pool_recycle` and the transaction-pooler prepared-statement caches — those remain.)

### 6. Query-timing instrumentation — `core/db.py`
SQLAlchemy `before/after_cursor_execute` hooks time **every** SQL statement. Slow ones (≥ `SQL_SLOW_MS`, default 200 ms) log as warnings; `SQL_TIMING_LOG=1` logs all. Per-request middleware stamps response headers:
`X-Process-Time-Ms`, `X-DB-Queries` (round-trip count — the real KPI), `X-DB-Time-Ms`.
New `GET /api/diagnostics/perf` returns live cache + SQL counters.

### 7. Frontend — `frontend/src/context/AuthContext.jsx`
The context value was recreated every render, re-rendering **every `useAuth()` consumer** (Layout, Sidebar, every page). Handlers are now `useCallback` and the value is `useMemo`'d. (`Promise.all` is already used across 16 page components; the dashboard already uses one merged endpoint — no change needed there.)

### 8. Production-scale indexes — `alembic/versions/003_perf_single_column_indexes.py` (new)
The schema is already richly indexed with `(tenant_id, …)` composites, but this deployment is single-tenant and the data layer filters **without** `tenant_id`, so those composites can't serve `product_id` / `sku` / `stock_item_id` / `status` / `user_id`-only lookups. The migration adds single-column indexes (`CREATE INDEX CONCURRENTLY IF NOT EXISTS`, no table locks) for those patterns. *No measurable effect today* (seq-scan on a handful of rows is instant) — a correctness-at-scale measure, applied under operator control via `alembic upgrade`.

---

## How to verify

```bash
# Per-request KPIs are in the response headers:
curl -i http://localhost:8001/api/dashboard/summary -H "Authorization: Bearer <token>"
#   X-DB-Queries: 0      <- cache hit
#   X-Process-Time-Ms: 9

# Live cache + SQL counters:
curl http://localhost:8001/api/diagnostics/perf -H "Authorization: Bearer <token>"

# Log every SQL query with timing:
SQL_TIMING_LOG=1 uvicorn server:app --port 8001
```

---

## The remaining floor (and the real fix for sub-1 s cold)

Warm everything is < 100 ms. The **cold** path (first dashboard load per 20 s TTL, or first page after a deploy) is ~2.6 s and is **bounded by the speed of light to Singapore**: 9 sequential round-trips × 260 ms. No amount of code removes that floor from a client in India.

**To actually hit "dashboard < 1 s cold" in production, colocate the backend with the database** — deploy the FastAPI app in `ap-southeast-1` (next to the Supabase project), or move the Supabase project to a region near your users. Same-region RTT is < 5 ms, which turns the 2.6 s cold dashboard into < 100 ms and makes every cold path effectively instant. This is the single highest-impact infrastructure change and is independent of the code work above (which already eliminated the 30–60 s problem).

## Regression status

- New cache/invalidation logic has its own passing tests (single-flight, TTL, prefix + generation invalidation, and live end-to-end checks that a product edit / category create / theme save reflect immediately).
- `tests/conftest.py` now clears the in-process cache before each test (autouse fixture), because unit tests swap the whole `core.db.db` fake per test.
- The pre-existing unit-test failures in `test_categories.py`, `test_audit_trail.py`, and `test_product_stock_link.py` are **not caused by this work** — verified by re-running with the cache fully disabled (identical failure set). They stem from the Mongo→Postgres migration: those tests monkeypatch an in-memory `db` fake, but the handlers they exercise now use `crud_create`/`get_session()` (real SQLAlchemy) or call symbols that were refactored (`product_stock_bridge.on_hand` → `on_hand_bulk`). That's a separate test-harness modernization, out of scope here.

## Pre-existing bug surfaced (NOT fixed — out of scope, needs your OK)

**Theme selection never persists.** `routers/theme_settings.py` writes `user_id`/`theme_id`/`updated_by` to `theme_settings`, but the migrated `ThemeSetting` model only has `id/tenant_id/key/value/updated_at`. The compat shim **silently drops** the unknown columns (the documented migration column-drift pattern), so saving a theme is a no-op and reads always fall back to the default. Fix = add `user_id`/`theme_id`/`updated_by`/`created_at` to the model + `ALTER TABLE theme_settings ADD COLUMN …` on Supabase (a schema change — left for you to authorize). The theme caching added here is correct and will work the moment persistence is fixed.
