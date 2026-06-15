"""Webhook signing & delivery — Module K.

Signed payloads (HMAC-SHA256, Stripe-style) + retry with exponential backoff.
Delivery runs on a background task; failures are re-queued with an increasing
`next_attempt_at` until max attempts, then parked as 'failed'.

Collections: webhook_subscriptions, webhook_deliveries
"""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone, timedelta


def sign_payload(secret: str, payload: dict, timestamp: int | None = None) -> dict:
    """
    Produce signature headers for a webhook payload.

    Signature = HMAC_SHA256(secret, "{timestamp}.{body}"). The receiver
    recomputes it over the raw body to verify authenticity + integrity, and
    rejects stale timestamps to prevent replay.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signed_content = f"{ts}.{body}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Timestamp": str(ts),
        "X-Webhook-Signature": f"t={ts},v1={signature}",
        "_body": body,
    }


def verify_signature(secret: str, body: str, signature_header: str, timestamp: str,
                     tolerance_seconds: int = 300) -> bool:
    """Receiver-side verification (also used in tests). Constant-time compare."""
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False
    # header form: "t=<ts>,v1=<sig>"
    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    provided = parts.get("v1", "")
    expected = hmac.new(secret.encode("utf-8"), f"{ts}.{body}".encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def backoff_delay(attempt: int, base: int = 5, cap: int = 3600) -> int:
    """Exponential backoff in seconds: 5, 10, 20, 40, … capped at `cap`."""
    return min(base * (2 ** max(attempt - 1, 0)), cap)


def next_attempt_time(attempt: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=backoff_delay(attempt))).isoformat()


async def enqueue_event(db, event_type: str, payload: dict):
    """
    Fan an event out to all active subscriptions listening for it, creating a
    pending delivery per subscription. The delivery worker picks these up.
    """
    subs = await db.webhook_subscriptions.find(
        {"active": True, "events": event_type}, {"_id": 0}
    ).to_list(1000)
    from core.utils import new_id, now_iso
    deliveries = []
    for sub in subs:
        deliveries.append({
            "id": new_id(),
            "subscription_id": sub["id"],
            "url": sub["url"],
            "event_type": event_type,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "max_attempts": sub.get("max_attempts", 5),
            "next_attempt_at": now_iso(),
            "created_at": now_iso(),
        })
    if deliveries:
        await db.webhook_deliveries.insert_many(deliveries)
    return len(deliveries)


async def deliver_pending(db, http_post=None) -> dict:
    """
    Process due deliveries. `http_post(url, body, headers)` is injected so this
    is testable without real network; returns (status_code) or raises.

    On success → 'delivered'. On failure → re-queue with backoff until
    max_attempts, then 'failed'.
    """
    from core.utils import now_iso
    now = datetime.now(timezone.utc).isoformat()
    due = await db.webhook_deliveries.find(
        {"status": {"$in": ["pending", "retrying"]}, "next_attempt_at": {"$lte": now}}, {"_id": 0}
    ).to_list(500)

    delivered, failed, retried = 0, 0, 0
    for d in due:
        sub = await db.webhook_subscriptions.find_one({"id": d["subscription_id"]}, {"_id": 0})
        secret = (sub or {}).get("secret", "")
        headers = sign_payload(secret, d["payload"])
        body = headers.pop("_body")
        attempt = d["attempts"] + 1
        ok = False
        status_code = None
        try:
            if http_post is not None:
                status_code = await http_post(d["url"], body, headers)
                ok = 200 <= int(status_code) < 300
        except Exception:
            ok = False

        if ok:
            await db.webhook_deliveries.update_one(
                {"id": d["id"]},
                {"$set": {"status": "delivered", "attempts": attempt,
                          "delivered_at": now_iso(), "last_status_code": status_code}},
            )
            delivered += 1
        elif attempt >= d["max_attempts"]:
            await db.webhook_deliveries.update_one(
                {"id": d["id"]},
                {"$set": {"status": "failed", "attempts": attempt,
                          "last_status_code": status_code, "failed_at": now_iso()}},
            )
            failed += 1
        else:
            await db.webhook_deliveries.update_one(
                {"id": d["id"]},
                {"$set": {"status": "retrying", "attempts": attempt,
                          "last_status_code": status_code,
                          "next_attempt_at": next_attempt_time(attempt)}},
            )
            retried += 1

    return {"due": len(due), "delivered": delivered, "failed": failed, "retried": retried}
