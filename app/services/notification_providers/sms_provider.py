"""SMS Notification Provider with automatic fallback to Console."""

import os
from typing import Any, Dict, Optional
from app.services.notification_providers import BaseNotificationProvider
from app.services.notification_providers.console_provider import ConsoleNotificationProvider


class SMSNotificationProvider(BaseNotificationProvider):
    """Dispatches SMS notifications, or falls back to console if unconfigured."""

    def __init__(self, fallback: Optional[BaseNotificationProvider] = None):
        self.sms_api_key = os.getenv("SMS_API_KEY")
        self.fallback = fallback or ConsoleNotificationProvider()

    def send_notification(
        self,
        recipient_type: str,
        recipient_id: int,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send only when a destination number is supplied; otherwise simulate honestly."""
        from app.services.notification_providers.delivery import deliver_notification
        metadata = metadata or {}
        recipient = metadata.get("phone")
        if not recipient:
            record = self.fallback.send_notification(recipient_type, recipient_id, title, message, metadata)
            record["fallback_reason"] = "recipient phone number missing"
            return record
        outcome = deliver_notification("sms", "", recipient, title, message)
        return {
            "channel": "SMS",
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "delivery_status": outcome.status,
            "status": outcome.status.upper(),
            "sent_at": outcome.sent_at.isoformat() if outcome.sent_at else None,
            "error": outcome.error,
        }
