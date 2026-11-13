"""Credential-backed delivery with explicit, non-delivery simulation fallback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import base64
import logging
import os
import secrets
import smtplib
import time
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("notification.delivery")


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    provider_reference: Optional[str] = None


def new_response_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, digest: str) -> bool:
    return hmac.compare_digest(token_digest(token), digest or "")


def response_token_expiry(now: Optional[datetime] = None) -> datetime:
    """Calculate expiry for response links; default lifetime is 24 hours."""
    try:
        lifetime = int(os.getenv("NOTIFICATION_RESPONSE_TOKEN_TTL_SECONDS", "86400"))
    except ValueError as exc:
        raise ValueError("NOTIFICATION_RESPONSE_TOKEN_TTL_SECONDS must be an integer") from exc
    if lifetime < 1:
        raise ValueError("NOTIFICATION_RESPONSE_TOKEN_TTL_SECONDS must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now + timedelta(seconds=lifetime)


def response_token_expired(expires_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """Treat missing expiry as invalid and compare database-naive timestamps as UTC."""
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= expires_at


def response_token_problem(row: object, token: str, now: Optional[datetime] = None) -> Optional[str]:
    """Return a safe lifecycle reason: invalid, expired, used, or None when valid."""
    if getattr(row, "response_status", None) != "pending" or not getattr(row, "response_token_hash", None):
        return "used"
    if not isinstance(token, str) or not token or not token_matches(token, getattr(row, "response_token_hash", "")):
        return "invalid"
    if response_token_expired(getattr(row, "response_token_expires_at", None), now):
        return "expired"
    return None


def consume_response_token(row: object) -> None:
    """Invalidate a one-time response token after a successful response."""
    row.response_token_hash = None
    row.response_token_expires_at = None


def response_url(recipient_type: str, notification_id: int, token: str) -> str:
    base = os.getenv("NOTIFICATION_PUBLIC_BASE_URL", "http://localhost:8105").rstrip("/")
    if recipient_type == "donor":
        base = os.getenv("NOTIFICATION_PUBLIC_DONOR_URL", "http://localhost:8106").rstrip("/")
    return f"{base}/api/v1/{'blood-bank' if recipient_type == 'bank' else 'donor'}-notifications/{notification_id}/respond?token={quote(token)}"


def twilio_callback_url(recipient_type: str, notification_id: int) -> str:
    base = os.getenv("NOTIFICATION_PUBLIC_BASE_URL", "http://localhost:8105").rstrip("/")
    path = "blood-bank-notifications" if recipient_type == "bank" else "donor-notifications"
    if recipient_type == "donor":
        base = os.getenv("NOTIFICATION_PUBLIC_DONOR_URL", "http://localhost:8106").rstrip("/")
    return f"{base}/api/v1/{path}/{notification_id}/twilio-status"


def twilio_signature_valid(recipient_type: str, notification_id: int, params: dict[str, str], signature: str) -> bool:
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth_token or not signature:
        return False
    canonical = twilio_callback_url(recipient_type, notification_id)
    material = canonical + "".join(key + params[key] for key in sorted(params))
    expected = base64.b64encode(hmac.new(auth_token.encode("utf-8"), material.encode("utf-8"), hashlib.sha1).digest()).decode("ascii")
    return hmac.compare_digest(expected, signature)


def _simulation(reason: str, channel: str, to: str) -> DeliveryOutcome:
    logger.info("Notification simulated channel=%s recipient=%s reason=%s", channel, to, reason)
    return DeliveryOutcome("simulated", error=reason)


def _is_synthetic(address: str) -> bool:
    return address.lower().endswith(".invalid") or address.startswith("+91-00000-")


def deliver_notification(channel: str, email: str, phone: str, subject: str, body: str, *, status_callback: Optional[str] = None) -> DeliveryOutcome:
    """Send email or SMS, or return SIMULATED when local credentials/recipient are synthetic.

    SMTP/Twilio acceptance is recorded as SENT; only authenticated delivery callbacks can
    advance a record to DELIVERED. Temporary network/provider failures get three attempts.
    """
    channel = channel.lower()
    if channel == "console":
        return _simulation("console mode", channel, email)
    target = email if channel == "email" else phone
    if _is_synthetic(target):
        return _simulation("synthetic recipient address", channel, target)
    attempts = 3
    last_error = "delivery provider is not configured"
    if channel == "email":
        host = os.getenv("SMTP_HOST")
        sender = os.getenv("SMTP_FROM")
        if not host or not sender:
            return _simulation("SMTP_HOST or SMTP_FROM missing", channel, target)
        for attempt in range(attempts):
            try:
                message = EmailMessage()
                message["From"] = sender
                message["To"] = email
                message["Subject"] = subject
                message.set_content(body)
                port = int(os.getenv("SMTP_PORT", "587"))
                timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "8"))
                if os.getenv("SMTP_USE_SSL", "false").lower() == "true":
                    client = smtplib.SMTP_SSL(host, port, timeout=timeout)
                else:
                    client = smtplib.SMTP(host, port, timeout=timeout)
                with client as smtp:
                    if os.getenv("SMTP_USE_STARTTLS", "true").lower() == "true" and not isinstance(smtp, smtplib.SMTP_SSL):
                        smtp.starttls()
                    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
                    if user and password:
                        smtp.login(user, password)
                    smtp.send_message(message)
                return DeliveryOutcome("sent", datetime.now(timezone.utc))
            except (OSError, smtplib.SMTPException) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < attempts:
                    time.sleep(0.1 * (attempt + 1))
        return DeliveryOutcome("failed", error=last_error[:1000])

    if channel == "sms":
        account = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        sender = os.getenv("TWILIO_FROM_NUMBER")
        if not account or not auth_token or not sender:
            return _simulation("Twilio credentials missing", channel, target)
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=float(os.getenv("SMS_TIMEOUT_SECONDS", "8"))) as client:
                    result = client.post(
                        f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json",
                        auth=(account, auth_token),
                    data={"To": phone, "From": sender, "Body": body, **({"StatusCallback": status_callback} if status_callback else {})},
                    )
                if result.status_code in {429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                if result.is_error:
                    return DeliveryOutcome("failed", error=f"Twilio HTTP {result.status_code}: {result.text[:800]}")
                payload = result.json()
                return DeliveryOutcome("sent", datetime.now(timezone.utc), provider_reference=payload.get("sid"))
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < attempts:
                    time.sleep(0.1 * (attempt + 1))
        return DeliveryOutcome("failed", error=last_error[:1000])
    return DeliveryOutcome("failed", error=f"unsupported channel: {channel}")
