"""Notification Providers package for Blood Donation Coordination."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("NotificationProvider")


class BaseNotificationProvider(ABC):
    """Abstract base class for notification dispatch providers."""

    @abstractmethod
    def send_notification(
        self,
        recipient_type: str,  # "HOSPITAL", "BLOOD_BANK", "DONOR"
        recipient_id: int,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatch a single notification message."""
        pass
