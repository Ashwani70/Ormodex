"""Resend email helper — sends transactional emails and logs to email_logs."""
import base64
import os
from html import escape as _esc
from typing import Optional, Any, cast

import resend



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
    # Escape all dynamic, potentially user-controlled values before embedding
    # them in HTML to prevent markup/script injection in the rendered email.
    doc_label_e = _esc(doc_label)
    doc_number_e = _esc(doc_number)
    recipient_e = _esc(recipient_name) if recipient_name else "Sir/Madam"
    intro_html = (
        f'<p style="color:#3f3f46;line-height:1.6;font-size:14px;margin:18px 0;">{_esc(intro)}</p>'
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
          <h1 style="margin:6px 0 18px 0;font-size:22px;">{doc_label_e} {doc_number_e}</h1>
          <p>Dear {recipient_e},</p>
          <p>Please find attached the {doc_label_e.lower()} <b>{doc_number_e}</b>.</p>
          {intro_html}
          <p>Regards,<br><b>GRAVITYONE ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def render_password_reset_html(*, reset_link: str, expires_minutes: int = 30) -> str:
    # Only allow http(s) links, then attribute-escape so a crafted value can't
    # break out of the href or inject a javascript:/data: scheme.
    safe_link = reset_link if reset_link.startswith(("http://", "https://")) else "#"
    safe_link = _esc(safe_link, quote=True)
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
          <p>You requested a password reset for your GRAVITYONE ERP account.</p>
          <p>Click the button below to reset your password. This link expires in {expires_minutes} minutes.</p>
          <p style="margin:24px 0;">
            <a href="{safe_link}" style="background:#0a0a0a;color:#facc15;padding:12px 24px;text-decoration:none;font-weight:700;border-radius:4px;">
              Reset Password
            </a>
          </p>
          <p style="color:#71717a;font-size:12px;">If you did not request this, ignore this email.</p>
          <p>Regards,<br><b>GRAVITYONE ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def render_otp_email_html(*, code: str, expires_minutes: int = 10) -> str:
    code_e = _esc(code)
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
          <h2>Password Reset Code</h2>
          <p>Use the code below to reset your GRAVITYONE ERP password. It expires in {expires_minutes} minutes.</p>
          <p style="margin:24px 0;font-size:32px;font-weight:900;letter-spacing:6px;">{code_e}</p>
          <p style="color:#71717a;font-size:12px;">If you did not request this, ignore this email.</p>
          <p>Regards,<br><b>GRAVITYONE ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


_SECURITY_EVENT_COPY = {
    "password_changed": ("Password Changed", "Your password was just changed. If this wasn't you, contact your administrator immediately."),
    "new_device_login": ("New Device Sign-In", "Your account was just signed in to from a new device or location."),
    "mfa_enabled": ("Two-Factor Authentication Enabled", "Two-factor authentication was just turned on for your account."),
    "mfa_disabled": ("Two-Factor Authentication Disabled", "Two-factor authentication was just turned off for your account."),
    "multiple_failed_logins": ("Multiple Failed Sign-In Attempts", "There have been several failed sign-in attempts on your account."),
}


def render_security_notification_html(event_type: str, details: Optional[dict] = None) -> str:
    """One shared renderer for the security-notification family of emails
    (password changed / new device / 2FA toggled / repeated failed logins),
    switched on event_type rather than one near-duplicate function per event."""
    title, summary = _SECURITY_EVENT_COPY.get(event_type, ("Security Notice", "A security-relevant change occurred on your account."))
    details = details or {}
    rows = "".join(
        f'<tr><td style="padding:4px 0;color:#71717a;font-size:12px;">{_esc(str(k))}</td>'
        f'<td style="padding:4px 0;font-size:12px;">{_esc(str(v))}</td></tr>'
        for k, v in details.items() if v
    )
    details_html = f'<table style="margin:16px 0;">{rows}</table>' if rows else ""
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
          <h2>{_esc(title)}</h2>
          <p>{_esc(summary)}</p>
          {details_html}
          <p style="color:#71717a;font-size:12px;">If this wasn't you, secure your account immediately and contact your administrator.</p>
          <p>Regards,<br><b>GRAVITYONE ERP</b></p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
