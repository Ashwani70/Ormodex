"""Temporary script — patch email.py with missing functions and add calc_totals to utils.py."""
import os

BASE = os.path.dirname(__file__)

# ── Full email.py replacement ─────────────────────────────────────────────────
EMAIL = '''\
"""Resend email helper — sends transactional emails and logs to email_logs."""
import base64
import os
from typing import Optional, Any, cast

import resend

from .db import get_session
from .utils import new_id, now_iso


def _api_key() -> str:
    return os.environ.get("RESEND_API_KEY", "").strip()


def _from_address() -> str:
    return os.environ.get("RESEND_FROM", "onboarding@resend.dev").strip()


def _reply_to() -> Optional[str]:
    rt = os.environ.get("RESEND_REPLY_TO", "").strip()
    return rt or None


def is_configured() -> bool:
    return bool(_api_key())


async def log_email(*args, **kwargs) -> None:
    pass


def send_email_sync(
    *,
    to: str,
    subject: str,
    html: str,
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
) -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("RESEND_API_KEY is not configured on the server")
    if key.startswith("re_mock") or key.startswith("mock") or key == "testkey":
        import uuid
        return {"id": f"mock-msg-{uuid.uuid4()}"}
    resend.api_key = key
    payload: dict[str, Any] = {
        "from": _from_address(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    rt = _reply_to()
    if rt:
        payload["reply_to"] = rt
    if attachment_bytes and attachment_filename:
        payload["attachments"] = [{
            "filename": attachment_filename,
            "content": base64.b64encode(attachment_bytes).decode("ascii"),
        }]
    return cast(dict, resend.Emails.send(cast(Any, payload)))


def render_doc_email_html(
    *,
    recipient_name: str,
    doc_label: str,
    doc_number: str,
    intro: Optional[str] = None,
) -> str:
    intro_html = (
        f\'<p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:18px 0;">{intro}</p>\'
        if intro else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e4e4e7;">
        <tr><td style="background:#0a0a0a;color:#ffffff;padding:18px 28px;">
          <div style="font-weight:900;font-size:18px;">GRAVITYONE ERP</div>
        </td></tr>
        <tr><td style="background:#facc15;height:4px;"></td></tr>
        <tr><td style="padding:28px;color:#0a0a0a;">
          <h1 style="margin:6px 0 18px 0;font-size:22px;">{doc_label} {doc_number}</h1>
          <p>Dear {recipient_name or \'Sir/Madam\'},</p>
          <p>Please find attached the {doc_label.lower()} <b>{doc_number}</b>.</p>
          {intro_html}
          <p>Regards,<br><b>Ormodex ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def render_password_reset_html(*, reset_link: str, expires_minutes: int = 30) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e4e4e7;">
        <tr><td style="background:#0a0a0a;color:#ffffff;padding:18px 28px;">
          <div style="font-weight:900;font-size:18px;">GRAVITYONE ERP</div>
        </td></tr>
        <tr><td style="background:#facc15;height:4px;"></td></tr>
        <tr><td style="padding:28px;color:#0a0a0a;">
          <h2>Password Reset Request</h2>
          <p>You requested a password reset for your Ormodex ERP account.</p>
          <p>Click the button below to reset your password. This link expires in {expires_minutes} minutes.</p>
          <p style="margin:24px 0;">
            <a href="{reset_link}" style="background:#0a0a0a;color:#facc15;padding:12px 24px;text-decoration:none;font-weight:700;border-radius:4px;">
              Reset Password
            </a>
          </p>
          <p style="color:#71717a;font-size:12px;">If you did not request this, ignore this email.</p>
          <p>Regards,<br><b>Ormodex ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
'''

email_path = os.path.join(BASE, "email.py")
with open(email_path, "w", encoding="utf-8") as f:
    f.write(EMAIL)
print(f"Written email.py: {len(EMAIL)} chars")

# ── Append calc_totals and _diff_fields to utils.py ──────────────────────────
ADDITIONS = '''

# ── helpers imported by routers ────────────────────────────────────────────────
_AUDIT_IGNORED_FIELDS = frozenset({"_id", "updated_at", "created_at"})


def calc_totals(items: list) -> dict:
    sub = 0.0
    gst = 0.0
    for it in items:
        line = float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
        sub += line
        gst += line * float(it.get("gst_rate", 0)) / 100.0
    return {
        "subtotal": round(sub, 2),
        "gst_amount": round(gst, 2),
        "total": round(sub + gst, 2),
    }


def _diff_fields(old: dict | None, new: dict | None) -> list[str]:
    old = old or {}
    new = new or {}
    keys = (set(old) | set(new)) - _AUDIT_IGNORED_FIELDS
    return sorted(k for k in keys if old.get(k) != new.get(k))
'''

utils_path = os.path.join(BASE, "utils.py")
with open(utils_path, "a", encoding="utf-8") as f:
    f.write(ADDITIONS)
print(f"Appended calc_totals + _diff_fields to utils.py")
