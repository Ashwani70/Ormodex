"""Self-hosted CAPTCHA challenge (no third-party account required).

No reCAPTCHA/hCaptcha site key is configured for this deployment. A simple
arithmetic challenge is sufficient defense-in-depth against scripted
brute-force after repeated failed logins — it's stateless (the expected
answer's hash travels inside a short-lived signed JWT, not a server-side
session store), so it works fine behind the in-memory, single-process rate
limiter without needing shared state.

Swap in a real provider later by replacing generate_challenge/verify_challenge
with calls to the provider's verify API; callers (routers/auth.py) only see
{"token", "question"} in and a bool out either way.
"""
import hashlib
import random
from datetime import datetime, timezone, timedelta

import jwt

from .auth_utils import JWT_ALGORITHM, jwt_secret

CHALLENGE_EXPIRE_MIN = 5


def _answer_hash(answer: str) -> str:
    return hashlib.sha256(answer.strip().lower().encode("utf-8")).hexdigest()


def generate_challenge() -> dict:
    a, b = random.randint(2, 9), random.randint(2, 9)
    answer = str(a + b)
    payload = {
        "type": "captcha",
        "ans": _answer_hash(answer),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_EXPIRE_MIN),
    }
    token = jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)
    return {"token": token, "question": f"{a} + {b} = ?"}


def verify_challenge(token: str, answer: str) -> bool:
    if not token or answer is None:
        return False
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "captcha":
            return False
        return payload.get("ans") == _answer_hash(str(answer))
    except jwt.InvalidTokenError:
        return False
