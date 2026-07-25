import os
from pathlib import Path
from dotenv import load_dotenv
import pytest as _pytest
import requests

# Load .env file automatically for all tests
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


# ── One persistent event loop for the whole test process ─────────────────────
# The data layer migrated from MongoDB to SQLAlchemy + PostgreSQL. The unit tests
# drive coroutines with ``asyncio.run(...)``, which creates a NEW event loop per
# call and CLOSES it on return. A pooled async engine (asyncpg) binds each pooled
# connection to the loop that opened it, so the *second* ``asyncio.run`` in a test
# reuses a connection whose loop is gone → ``RuntimeError: Event loop is closed``.
#
# Rather than disable pooling (NullPool reconnects on every op — far too slow and
# flaky against a remote Supabase over SSL), we run every test coroutine on a
# SINGLE long-lived loop. The pool then stays valid across all calls. We do this
# by pointing ``asyncio.run`` at one persistent loop for the test process only;
# production code is completely untouched.
import asyncio as _asyncio

_TEST_LOOP = _asyncio.new_event_loop()
_asyncio.set_event_loop(_TEST_LOOP)


def _run_on_persistent_loop(coro, *args, **kwargs):
    """Drop-in for asyncio.run that reuses one loop (keeps the asyncpg pool alive
    across the many asyncio.run(...) calls a single test makes)."""
    return _TEST_LOOP.run_until_complete(coro)


# Override only within the test process. Real app code never imports conftest.
_asyncio.run = _run_on_persistent_loop


# ── pytest-asyncio (``@pytest.mark.asyncio`` tests) must use the SAME loop ────
# pytest.ini sets asyncio_default_test_loop_scope=session so pytest-asyncio
# builds one asyncio.Runner for the whole session instead of one per test —
# but by default that Runner still creates its OWN new loop, a second, separate
# long-lived loop coexisting with _TEST_LOOP above. Any asyncpg connection the
# SQLAlchemy pool hands out gets bound to whichever of the two loops was
# current at the time; when a connection created under one loop is later
# reused while the other loop is current, asyncpg raises "Future attached to a
# different loop" (or, before the session-scope fix, "Event loop is closed").
# Point pytest-asyncio's loop factory at _TEST_LOOP so there is truly only one
# event loop for the entire test process, matching _run_on_persistent_loop.
@_pytest.fixture(scope="session")
def event_loop_policy():
    base = type(_asyncio.get_event_loop_policy())

    class _SingleLoopPolicy(base):
        def new_event_loop(self):
            return _TEST_LOOP

        def get_event_loop(self):
            return _TEST_LOOP

    return _SingleLoopPolicy()


# ── Reset the in-process cache between tests ─────────────────────────────────
# core/cache.py holds a process-global TTL cache (user identity, category /
# product lists, dashboard summaries). Unit tests monkeypatch core.db.db with a
# fresh in-memory fake per test, swapping the WHOLE data layer rather than going
# through the write methods that auto-invalidate — so a list cached in one test
# would be served stale to the next. Clear the cache (and generation counters)
# before every test so each starts from a clean slate. Production is untouched.


@_pytest.fixture(autouse=True)
def _clear_app_cache():
    # Unit tests swap the WHOLE data layer (core.db.db) with a fresh in-memory
    # fake per test, and exercise handlers that don't all go through the cache's
    # auto-invalidating write paths — so a value cached against one test's fake
    # could otherwise leak into the next. Clear the process-global cache (and
    # generation counters) before each test so every test starts clean. Real app
    # code never imports conftest, so production caching is unaffected.
    try:
        from core import cache as _cache
        _cache.clear()
        _cache._generations.clear()
    except Exception:
        pass
    yield


@_pytest.fixture(autouse=True)
def _restore_monkeypatched_globals():
    """Snapshot & restore module-level globals that some unit tests overwrite
    in place (e.g. `routers.purchase_v2.crud_create = mock`, `core.db.db = fake`)
    without ever putting the originals back. Without this, a test file that
    patches these globals leaks its in-memory fakes into every test that runs
    after it — making the suite order-dependent (e.g. test_po_numbering.py
    passes alone but fails after test_purchase_bill_posting.py). Production code
    never imports conftest, so this only affects the test process.
    """
    import importlib
    targets = [
        "routers.purchase_v2", "routers.ledger", "routers.inventory_v2",
        "routers.job_work", "routers.sales", "routers.debtors_creditors",
        "routers.accounting", "core.product_stock_bridge", "core.db",
        "core.utils", "core.voucher_engine", "core.ledger_posting",
        "core.stock_ledger", "core.po_numbering", "core.masters_crud",
        "core.voucher_numbering", "core._mongo_compat",
    ]
    watched_attrs = ("crud_create", "crud_get", "crud_update", "crud_delete", "db")
    saved: dict = {}
    for mod_name in targets:
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for attr in watched_attrs:
            if hasattr(mod, attr):
                saved[(mod_name, attr)] = (mod, getattr(mod, attr))
    try:
        yield
    finally:
        for (mod_name, attr), (mod, original) in saved.items():
            try:
                setattr(mod, attr, original)
            except Exception:
                pass


# Monkeypatch requests to add X-Test-Bypass header for integration test login rate limit bypass
original_request = requests.Session.request

def patched_request(self, method, url, *args, **kwargs):
    headers = kwargs.get("headers")
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)
    headers["X-Test-Bypass"] = "true"
    kwargs["headers"] = headers
    try:
        return original_request(self, method, url, *args, **kwargs)
    except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
        if "127.0.0.1" in str(url) or "localhost" in str(url):
            _pytest.skip(f"Live backend server not running at {url}", allow_module_level=True)
        raise e

requests.Session.request = patched_request
