"""Resend email helper — sends transactional emails with optional PDF attachments
and logs each send to the `email_logs` MongoDB collection.
"""
import base64
import os
from typing import Optional, Any, cast

import resend

from .db import db
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


async def log_email(*, to: str, subject: str, doc_type: str, doc_id: str,
                    doc_number: str, sent_by: dict, status: str, error: Optional[str] = None,
                    message_id: Optional[str] = None):
    await db.email_logs.insert_one({
        "id": new_id(),
        "to": to,
        "subject": subject,
        "doc_type": doc_type,
        "doc_id": doc_id,
        "doc_number": doc_number,
        "sent_by": sent_by.get("name"),
        "sent_by_id": sent_by.get("id"),
        "status": status,
        "error": error,
        "message_id": message_id,
        "created_at": now_iso(),
    })


def send_email_sync(*, to: str, subject: str, html: str,
                    attachment_bytes: Optional[bytes] = None,
                    attachment_filename: Optional[str] = None) -> dict:
    """Synchronous email send via Resend SDK.
    Returns a dict like {"id": "<message-id>"} on success, raises on failure.
    """
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


def render_doc_email_html(*, recipient_name: str, doc_label: str, doc_number: str,
                          intro: Optional[str] = None) -> str:
    intro_html = (
        f'<p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:18px 0;">{intro}</p>'
        if intro
        else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e4e4e7;">
        <tr><td style="background:#0a0a0a;color:#ffffff;padding:18px 28px;">
          <div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-weight:900;letter-spacing:-0.02em;font-size:18px;">
            GRAVITYONE ERP
          </div>
          <div style="color:#facc15;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;margin-top:2px;font-weight:600;">
            AI-Powered Business Management Platform
          </div>
        </td></tr>
        <tr><td style="background:#facc15;height:4px;"></td></tr>
        <tr><td style="padding:28px;color:#0a0a0a;">
          <div style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#71717a;font-weight:700;">
            {doc_label}
          </div>
          <h1 style="margin:6px 0 18px 0;font-size:22px;font-weight:800;letter-spacing:-0.01em;">
            {doc_number}
          </h1>
          <p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:0 0 12px 0;">
            Dear {recipient_name or 'Sir/Madam'},
          </p>
          <p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:0;">
            Please find attached the {doc_label.lower()} <b>{doc_number}</b> for your reference.
            Kindly review the document and revert with your confirmation.
          </p>
          {intro_html}
          <p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:18px 0 0 0;">
            Looking forward to your response.
          </p>
          <p style="color:#0a0a0a;line-height:1.4;font-size:14px;margin:24px 0 0 0;font-weight:600;">
            Regards,<br>
            <span style="font-weight:700;">GravityOne ERP</span>
          </p>
        </td></tr>
        <tr><td style="background:#0a0a0a;color:#a1a1aa;padding:14px 28px;font-size:11px;letter-spacing:0.1em;">
          This is an automated message from the GravityOne ERP system.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
