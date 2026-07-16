"""
Offline unit tests for the GST provider health check (irp_einvoice.health_status).

These run WITHOUT a server, MongoDB, or network: the auth round-trip
(_get_token) is patched. They lock in the stable integration contract — the
exact response shapes and, critically, that secrets never leak into the
response — so future refactors (including wiring the real GSP auth flow) can't
silently change the API or expose credentials.
"""
import asyncio

import pytest

from core import irp_einvoice as irp


# Every key the response is ever allowed to contain.
ALLOWED_KEYS = {
    "configured",
    "authenticated",
    "provider",
    "environment",
    "error",
    "last_checked_at",
}

# Keys that must NEVER appear in the response.
FORBIDDEN_KEYS = [
    "client_id",
    "client_secret",
    "username",
    "password",
    "token",
    "access_token",
    "base_url",
]


@pytest.fixture(autouse=True)
def reset_irp_state(monkeypatch):
    """Isolate each test: clear caches and restore a known config baseline."""
    irp._health_cache = None
    irp._token_cache.clear()
    monkeypatch.setitem(irp.IRP_CONFIG, "provider", "NIC")
    monkeypatch.setitem(irp.IRP_CONFIG, "environment", "sandbox")
    yield
    irp._health_cache = None
    irp._token_cache.clear()


def _run(coro):
    return asyncio.run(coro)


def _assert_contract(result):
    """Shared invariants for any health response: schema + no secret leakage."""
    assert set(result.keys()).issubset(ALLOWED_KEYS), (
        f"unexpected keys: {set(result.keys()) - ALLOWED_KEYS}"
    )
    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in result
    # Belt and braces: no secret-shaped value smuggled into any field either.
    blob = " ".join(str(v) for v in result.values()).lower()
    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in blob


def test_not_configured(monkeypatch):
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "")  # is_configured() -> False
    result = _run(irp.health_status("user", "pass"))

    assert result["configured"] is False
    assert result["authenticated"] is False
    assert result["error"] == "IRP credentials are not configured"
    _assert_contract(result)


def test_missing_credentials(monkeypatch):
    """Configured base_url but no username/password is still 'not configured'."""
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")
    result = _run(irp.health_status("", ""))

    assert result["configured"] is False
    assert result["authenticated"] is False
    assert result["error"] == "IRP credentials are not configured"
    _assert_contract(result)


def test_authentication_success(monkeypatch):
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")

    async def fake_token(username, password):
        return "SECRET-TOKEN-should-never-surface"

    monkeypatch.setattr(irp, "_get_token", fake_token)
    result = _run(irp.health_status("user", "pass"))

    assert result["configured"] is True
    assert result["authenticated"] is True
    assert result["provider"] == "NIC"
    assert result["environment"] == "sandbox"
    assert "last_checked_at" in result
    _assert_contract(result)


def test_authentication_failure(monkeypatch):
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")

    async def fake_token(username, password):
        raise irp.IRPAuthError()

    monkeypatch.setattr(irp, "_get_token", fake_token)
    result = _run(irp.health_status("user", "pass"))

    assert result["configured"] is True
    assert result["authenticated"] is False
    assert result["error"] == "Authentication failed"
    _assert_contract(result)


def test_cache_hit_skips_auth(monkeypatch):
    """First call authenticates; a second within the TTL does not re-auth."""
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")
    calls = {"n": 0}

    async def counting_token(username, password):
        calls["n"] += 1
        return "tok"

    monkeypatch.setattr(irp, "_get_token", counting_token)

    first = _run(irp.health_status("user", "pass"))
    second = _run(irp.health_status("user", "pass"))

    assert calls["n"] == 1, "second call within TTL must not re-authenticate"
    assert first == second, "cached response must be identical"
    _assert_contract(first)


def test_force_bypasses_cache(monkeypatch):
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")
    calls = {"n": 0}

    async def counting_token(username, password):
        calls["n"] += 1
        return "tok"

    monkeypatch.setattr(irp, "_get_token", counting_token)

    _run(irp.health_status("user", "pass"))
    _run(irp.health_status("user", "pass", force=True))

    assert calls["n"] == 2, "force=True must re-authenticate"


def test_timeout_handling(monkeypatch):
    """Auth that hangs past the timeout is reported as a clean auth failure."""
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")
    # Shrink the timeout so the test is fast but still exercises the real path.
    monkeypatch.setattr(irp, "HEALTH_AUTH_TIMEOUT_SECONDS", 0.05)

    async def hanging_token(username, password):
        await asyncio.sleep(5)  # >> timeout
        return "tok"

    monkeypatch.setattr(irp, "_get_token", hanging_token)
    result = _run(irp.health_status("user", "pass"))

    assert result["configured"] is True
    assert result["authenticated"] is False
    assert result["error"] == "Authentication failed"
    _assert_contract(result)


def test_schema_no_drift_across_all_states(monkeypatch):
    """Every reachable state must keep its keys within the allowed schema."""
    # Not configured
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "")
    _assert_contract(_run(irp.health_status("u", "p")))

    irp._health_cache = None
    monkeypatch.setitem(irp.IRP_CONFIG, "base_url", "https://irp.example.test")

    async def ok(username, password):
        return "tok"

    monkeypatch.setattr(irp, "_get_token", ok)
    _assert_contract(_run(irp.health_status("u", "p")))
