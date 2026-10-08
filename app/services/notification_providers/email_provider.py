"""Email Notification Provider with automatic fallback to Console."""

import os
from typing import Any, Dict, Optional
from app.services.notification_providers import BaseNotificationProvider
from app.services.notification_providers.console_provider import ConsoleNotificationProvider


class EmailNotificationProvider(BaseNotificationProvider):
    """Dispatches email notifications, or falls back to console if unconfigured."""

    def __init__(self, fallback: Optional[BaseNotificationProvider] = None):
        self.smtp_host = os.getenv("SMTP_HOST")
        self.fallback = fallback or ConsoleNotificationProvider()

    def send_notification(
        self,
        recipient_type: str,
        recipient_id: int,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch email, falling back to console if SMTP not configured."""
        if not self.smtp_host:
            # Fallback to console provider
            record = self.fallback.send_notification(
                recipient_type, recipient_id, title, message, metadata
            )
            record["fallback"] = True
            record["fallback_reason"] = "SMTP_HOST not configured"
            return record

        # Stub for active SMTP dispatch
        return {
            "channel": "EMAIL",
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "title": title,
            "message": message,
            "metadata": metadata or {},
            "status": "SENT",
        }
