"""SMS OTP delivery — stub.

No SMS gateway account (Twilio/MSG91/etc.) is configured for this deployment.
This module mirrors core/email.py's shape so wiring a real provider later is a
drop-in: implement send_sms_otp's body and is_configured() flips on once
SMS_GATEWAY_API_KEY is set. Callers (routers/mfa.py, routers/auth.py) check
is_configured() before offering SMS as an option — nothing calls
send_sms_otp() unless it would actually work.
"""
import os


def is_configured() -> bool:
    return bool(os.environ.get("SMS_GATEWAY_API_KEY", "").strip())


def send_sms_otp(phone: str, code: str) -> dict:
    if not is_configured():
        raise RuntimeError("SMS gateway not configured (set SMS_GATEWAY_API_KEY)")
    raise NotImplementedError("SMS gateway integration not yet implemented")
