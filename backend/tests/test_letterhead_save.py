import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = "admin@ormodex.com"
ADMIN_PASSWORD = "Admin@123456"

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
    s.user = data["user"]  # type: ignore
    return s

def test_letterhead_save_flow(admin_session):
    # 1. Create a letterhead template
    payload = {
        "template_name": "Test Letterhead Save",
        "theme": "corporate_blue",
        "page_size": "A4",
        "margin_top": 20.0,
        "margin_bottom": 20.0,
        "margin_left": 20.0,
        "margin_right": 20.0,
        "header_height": 35.0,
        "footer_height": 22.0,
        "logo_position": "left",
        "is_default": False
    }
    
    r_create = admin_session.post(
        f"{BASE_URL}/api/letterhead/templates",
        json=payload
    )
    assert r_create.status_code == 201, f"Failed to create template: {r_create.text}"
    created_data = r_create.json()
    template_id = created_data["id"]
    assert created_data["template_name"] == "Test Letterhead Save"

    # 2. Update the template (save changes)
    update_payload = {
        "template_name": "Updated Test Letterhead Save",
        "theme": "modern_minimalist",
        "page_size": "A4",
        "margin_top": 15.0,
        "margin_bottom": 15.0,
        "margin_left": 15.0,
        "margin_right": 15.0,
        "header_height": 30.0,
        "footer_height": 20.0,
        "logo_position": "center",
        "is_default": False,
        "change_note": "Updating margins and theme"
    }

    r_update = admin_session.put(
        f"{BASE_URL}/api/letterhead/templates/{template_id}",
        json=update_payload
    )
    assert r_update.status_code == 200, f"Failed to update template: {r_update.text}"
    updated_data = r_update.json()
    assert updated_data["template_name"] == "Updated Test Letterhead Save"
    assert updated_data["theme"] == "modern_minimalist"

    # 3. Clean up (delete template)
    r_delete = admin_session.delete(f"{BASE_URL}/api/letterhead/templates/{template_id}")
    assert r_delete.status_code == 200, f"Failed to delete template: {r_delete.text}"
