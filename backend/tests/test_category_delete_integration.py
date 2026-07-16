import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"

@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}"})
    return s

def test_delete_category_integration(admin_session):
    # 1. Create a category
    r = admin_session.post(f"{BASE_URL}/api/categories", json={
        "name": "Integration Test Category",
        "code": "ITC",
        "description": "Test Desc",
        "status": "Active",
        "display_order": 1
    })
    assert r.status_code == 200, r.text
    cat_id = r.json()["id"]

    # 2. Delete the category - should succeed
    r_del = admin_session.delete(f"{BASE_URL}/api/categories/{cat_id}")
    assert r_del.status_code == 200, r_del.text

    # 3. Create a parent category
    r_parent = admin_session.post(f"{BASE_URL}/api/categories", json={
        "name": "Parent Category Test",
        "code": "PCT",
        "status": "Active"
    })
    assert r_parent.status_code == 200, r_parent.text
    parent_id = r_parent.json()["id"]

    # 4. Create a child category
    r_child = admin_session.post(f"{BASE_URL}/api/categories", json={
        "name": "Child Category Test",
        "code": "CCT",
        "parent_id": parent_id,
        "status": "Active"
    })
    assert r_child.status_code == 200, r_child.text
    child_id = r_child.json()["id"]

    # 5. Try to delete the parent category - should fail with 400
    r_del_parent = admin_session.delete(f"{BASE_URL}/api/categories/{parent_id}")
    assert r_del_parent.status_code == 400, r_del_parent.text
    assert "Cannot delete: this category has sub-categories" in r_del_parent.text

    # 6. Delete child first
    assert admin_session.delete(f"{BASE_URL}/api/categories/{child_id}").status_code == 200

    # 7. Now deleting parent should succeed
    assert admin_session.delete(f"{BASE_URL}/api/categories/{parent_id}").status_code == 200
