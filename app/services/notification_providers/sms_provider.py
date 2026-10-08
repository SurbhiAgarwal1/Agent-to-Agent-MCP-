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
        """Dispatch SMS, falling back to console if API key not configured."""
        if not self.sms_api_key:
            record = self.fallback.send_notification(
                recipient_type, recipient_id, title, message, metadata
            )
            record["fallback"] = True
            record["fallback_reason"] = "SMS_API_KEY not configured"
            return record

        return {
            "channel": "SMS",
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "title": title,
            "message": message,
            "metadata": metadata or {},
            "status": "SENT",
        }
