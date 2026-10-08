"""Console Notification Provider.

Logs notifications to console and maintains an in-memory dispatch history
for testing, inspection, and verification.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from app.services.notification_providers import BaseNotificationProvider

logger = logging.getLogger("ConsoleNotificationProvider")


class ConsoleNotificationProvider(BaseNotificationProvider):
    """Logs notifications to standard output / logger."""

    def __init__(self):
        self.sent_notifications: List[Dict[str, Any]] = []

    def send_notification(
        self,
        recipient_type: str,
        recipient_id: int,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log message and record in history."""
        record = {
            "channel": "CONSOLE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recipient_type": recipient_type.upper(),
            "recipient_id": recipient_id,
            "title": title,
            "message": message,
            "metadata": metadata or {},
            "status": "DELIVERED",
        }
        self.sent_notifications.append(record)
        logger.info(f"[{record['channel']}] To: {record['recipient_type']} #{record['recipient_id']} | {title}: {message}")
        return record

    def get_history(self) -> List[Dict[str, Any]]:
        """Return history of sent messages."""
        return list(self.sent_notifications)
