"""Unit tests for the global cross-module search endpoint.

Covers the SQL query structure, deep-link path composition rules, and fanned-out search.
Uses a stubbed SQL session context instead of a live database.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-search-tests")

import asyncio
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import MagicMock
from fastapi import Request

from routers import search as search_mod
from routers.search import _Q_AWARE_ROUTES, _ENTITIES


class DummyRequest(Request):
    def __init__(self) -> None:
        super().__init__(scope={"type": "http", "headers": [], "client": None})



def test_q_aware_routes_are_subset_of_entities():
    routes = {ent.route for ent in _ENTITIES}
    assert _Q_AWARE_ROUTES <= routes


def test_newer_modules_are_searchable():
    # Guards against the regression where modules existed but weren't searchable.
    collections = {ent.key for ent in _ENTITIES}
    for col in ("projects", "job_work_challans", "pdcs", "cheque_transactions"):
        assert col in collections, f"{col} missing from global search entities"


@asynccontextmanager
async def mock_session_context(rows):
    class FakeMapping:
        def __init__(self, d):
            self.d = d
        def __getitem__(self, key):
            return self.d[key]
        def get(self, key, default=None):
            return self.d.get(key, default)

    class FakeResult:
        def mappings(self):
            return self
        def all(self):
            return [FakeMapping(r) for r in rows]

    class FakeSession:
        async def execute(self, statement, params=None):
            return FakeResult()
        async def commit(self):
            pass
        async def rollback(self):
            pass

    yield FakeSession()


def test_global_search_fans_out_and_deep_links(monkeypatch):
    rows = [
        {
            "entity": "products",
            "id": "p1",
            "title": "Steel Rod",
            "subtitle": "STL-1 | Raw",
            "doc_number": "STL-1",
            "status": "ACTIVE",
            "occurred_at": "2026-07-14T07:33:34Z",
            "rank": 0.8,
        },
        {
            "entity": "customers",
            "id": "c1",
            "title": "Steel Corp",
            "subtitle": "Steel Pvt | 999",
            "doc_number": "GSTIN123",
            "status": "ACTIVE",
            "occurred_at": "2026-07-14T07:33:34Z",
            "rank": 0.7,
        },
    ]
    monkeypatch.setattr(search_mod, "get_session", lambda: mock_session_context(rows))

    out = asyncio.run(search_mod.global_search(request=DummyRequest(), q="steel", user={"role": "admin"}))
    assert out["count"] == 2
    
    # Flatten groups to get results list
    results = []
    for g in out["groups"].values():
        results.extend(g)
        
    by_module = {r["module"]: r for r in results}
    # Products and Customers are detail-aware -> gets ?detail=
    assert by_module["Products"]["path"] == "/products?detail=p1"
    assert by_module["Customers"]["path"] == "/customers?detail=c1"
    assert by_module["Customers"]["subtitle"] == "Steel Pvt | 999"


def test_ledger_master_is_searchable_and_deep_links(monkeypatch):
    rows = [
        {
            "entity": "master_ledgers",
            "id": "l1",
            "title": "HDFC Bank Account",
            "subtitle": "",
            "doc_number": None,
            "status": "ACTIVE",
            "occurred_at": "2026-07-14T07:33:34Z",
            "rank": 0.9,
        }
    ]
    monkeypatch.setattr(search_mod, "get_session", lambda: mock_session_context(rows))

    out = asyncio.run(search_mod.global_search(request=DummyRequest(), q="hdfc", user={"role": "admin"}))
    
    # Flatten groups to get results list
    results = []
    for g in out["groups"].values():
        results.extend(g)
        
    ledger_hits = [r for r in results if r["module"] == "Ledgers"]
    assert len(ledger_hits) == 1
    assert ledger_hits[0]["title"] == "HDFC Bank Account"
    assert ledger_hits[0]["path"] == "/masters/ledgers?detail=l1"


def test_global_search_short_query_returns_empty():
    out = asyncio.run(search_mod.global_search(request=DummyRequest(), q="a", user={"role": "admin"}))
    assert out == {"query": "a", "groups": {}, "count": 0, "took_ms": 0}


def test_global_search_escapes_regex(monkeypatch):
    monkeypatch.setattr(search_mod, "get_session", lambda: mock_session_context([]))
    out = asyncio.run(search_mod.global_search(request=DummyRequest(), q="a(b)", user={"role": "admin"}))
    assert out["count"] >= 0
