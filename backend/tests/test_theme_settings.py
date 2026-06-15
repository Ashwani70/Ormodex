import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@gravityone.com"
ADMIN_PASSWORD = "Admin@123"

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s

@pytest.fixture(scope="module")
def employee_session(admin_session):
    email = "employee_theme@gravityone.com"
    password = "Employee@123"
    admin_session.post(
        f"{BASE_URL}/api/users",
        json={
            "name": "Employee Theme Test",
            "email": email,
            "phone": "9876543210",
            "role": "employee",
            "password": password,
            "permissions": {}
        }
    )
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, f"Employee login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    s.user = data["user"]
    return s

@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()

def test_get_active_theme_default(admin_session, anon_session):
    """Unauthenticated requests retrieve the default theme (Gravity brand)."""
    r_reset = admin_session.post(f"{BASE_URL}/api/theme-settings/reset")
    assert r_reset.status_code == 200

    r = anon_session.get(f"{BASE_URL}/api/theme-settings/active")
    assert r.status_code == 200
    assert r.json()["theme_id"] == "gravity"

def test_save_theme_unauthorized(anon_session):
    """Anonymous requests to save theme settings are blocked."""
    r = anon_session.post(
        f"{BASE_URL}/api/theme-settings",
        json={"theme_id": "template"}
    )
    assert r.status_code == 401

def test_save_theme_authorized(admin_session, anon_session):
    """An admin can switch to the blue template theme and it persists globally."""
    r_save = admin_session.post(f"{BASE_URL}/api/theme-settings", json={"theme_id": "template"})
    assert r_save.status_code == 200
    assert r_save.json()["theme_id"] == "template"

    r_get = admin_session.get(f"{BASE_URL}/api/theme-settings")
    assert r_get.status_code == 200
    assert r_get.json()["theme_id"] == "template"

    r_active = anon_session.get(f"{BASE_URL}/api/theme-settings/active")
    assert r_active.status_code == 200
    assert r_active.json()["theme_id"] == "template"

def test_invalid_theme_falls_back_to_default(admin_session):
    """An unknown theme_id is coerced to the default Gravity brand."""
    r_save = admin_session.post(f"{BASE_URL}/api/theme-settings", json={"theme_id": "does_not_exist"})
    assert r_save.status_code == 200
    assert r_save.json()["theme_id"] == "gravity"

def test_reset_theme_authorized(admin_session, anon_session):
    """An admin can reset theme settings back to the default brand theme."""
    admin_session.post(f"{BASE_URL}/api/theme-settings", json={"theme_id": "template"})
    r_reset = admin_session.post(f"{BASE_URL}/api/theme-settings/reset")
    assert r_reset.status_code == 200
    assert r_reset.json()["theme_id"] == "gravity"

    r_active = anon_session.get(f"{BASE_URL}/api/theme-settings/active")
    assert r_active.status_code == 200
    assert r_active.json()["theme_id"] == "gravity"

def test_employee_theme_flow(admin_session, employee_session, anon_session):
    """An employee can save and reset their own theme, isolated from the global one."""
    # 1. Reset both global and employee to default
    assert admin_session.post(f"{BASE_URL}/api/theme-settings/reset").status_code == 200
    assert employee_session.post(f"{BASE_URL}/api/theme-settings/reset").status_code == 200

    # 2. Employee active theme is default gravity
    r = employee_session.get(f"{BASE_URL}/api/theme-settings/active")
    assert r.status_code == 200
    assert r.json()["theme_id"] == "gravity"

    # 3. Employee switches to the template theme
    r_save = employee_session.post(f"{BASE_URL}/api/theme-settings", json={"theme_id": "template"})
    assert r_save.status_code == 200
    assert r_save.json()["theme_id"] == "template"

    # 4. Employee sees their own selection
    assert employee_session.get(f"{BASE_URL}/api/theme-settings/active").json()["theme_id"] == "template"

    # 5. Anonymous still gets the global default (gravity)
    assert anon_session.get(f"{BASE_URL}/api/theme-settings/active").json()["theme_id"] == "gravity"

    # 6. Admin sets the global active theme to template
    assert admin_session.post(f"{BASE_URL}/api/theme-settings", json={"theme_id": "template"}).status_code == 200
    assert anon_session.get(f"{BASE_URL}/api/theme-settings/active").json()["theme_id"] == "template"

    # 7. Employee resets -> falls back to the global template theme
    assert employee_session.post(f"{BASE_URL}/api/theme-settings/reset").status_code == 200
    assert employee_session.get(f"{BASE_URL}/api/theme-settings/active").json()["theme_id"] == "template"

    # 8. Admin resets -> global back to gravity
    assert admin_session.post(f"{BASE_URL}/api/theme-settings/reset").status_code == 200
    assert anon_session.get(f"{BASE_URL}/api/theme-settings/active").json()["theme_id"] == "gravity"
