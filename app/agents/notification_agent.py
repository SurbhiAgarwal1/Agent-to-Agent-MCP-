"""Notification Agent for Blood Donation Emergency Coordination.

Part 12: Alerts hospitals, blood banks, and donors upon creation
of an emergency fulfillment plan.
"""

from typing import Any, Dict, List, Optional
import logging

from app.services.notification_providers import BaseNotificationProvider
from app.services.notification_providers.console_provider import ConsoleNotificationProvider

logger = logging.getLogger("NotificationAgent")


class NotificationAgent:
    """Agent responsible for alerting parties regarding blood fulfillment plans."""

    def __init__(
        self,
        provider: Optional[BaseNotificationProvider] = None,
        bus: Optional[Any] = None,
    ):
        """Initialize the Notification Agent.
        
        Args:
            provider: Custom or injected notification provider (defaults to ConsoleNotificationProvider).
            bus: Optional A2A message bus.
        """
        self.provider = provider or ConsoleNotificationProvider()
        self.bus = bus

    def notify_plan(
        self,
        hospital_id: int,
        request_id: int,
        fulfillment_plan: Dict[str, Any],
        hospital_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send notifications for an optimized fulfillment plan.
        
        Notifies:
            1. Requesting hospital of overall plan outcome.
            2. Each matched blood bank/donor of units requested and ETA.
            
        Args:
            hospital_id: Identifier of the requesting hospital.
            request_id: Identifier of the blood request.
            fulfillment_plan: Multi-source fulfillment plan dictionary.
            hospital_name: Optional human-readable name of the hospital.
            
        Returns:
            Dictionary summarizing dispatched notifications.
        """
        status = fulfillment_plan.get("status", "UNFULFILLED")
        total_units = fulfillment_plan.get("total_units", 0)
        units_req = fulfillment_plan.get("details", {}).get("units_required", total_units)
        hosp_display = hospital_name or f"Hospital #{hospital_id}"

        dispatched: List[Dict[str, Any]] = []

        # 1. Hospital Notification
        if status == "FULLY_FULFILLED":
            hosp_title = f"Request #{request_id} FULLY FULFILLED"
            hosp_body = (
                f"Emergency blood request #{request_id} has been completely fulfilled. "
                f"All {total_units}/{units_req} units have been secured across {len(fulfillment_plan.get('plan', []))} source(s)."
            )
        elif status == "PARTIALLY_FULFILLED":
            shortage = fulfillment_plan.get("details", {}).get("units_shortage", units_req - total_units)
            hosp_title = f"Request #{request_id} PARTIALLY FULFILLED"
            hosp_body = (
                f"Emergency blood request #{request_id} has been partially fulfilled: {total_units}/{units_req} units secured. "
                f"Critical shortage: {shortage} unit(s) remaining."
            )
        else:
            hosp_title = f"Request #{request_id} UNFULFILLED"
            hosp_body = (
                f"Urgent alert: Blood request #{request_id} could not be fulfilled. "
                f"No compatible sources currently available within safe transit radius."
            )

        hosp_notif = self.provider.send_notification(
            recipient_type="HOSPITAL",
            recipient_id=hospital_id,
            title=hosp_title,
            message=hosp_body,
            metadata={
                "request_id": request_id,
                "status": status,
                "total_units": total_units,
            },
        )
        dispatched.append(hosp_notif)

        # 2. Source Notifications (Blood Banks & Donors)
        for item in fulfillment_plan.get("plan", []):
            s_type = item.get("source_type", "BLOOD_BANK")
            s_id = item.get("source_id", 0)
            units = item.get("units", 1)
            dist_km = item.get("distance_km", 0.0)
            eta = item.get("estimated_time", f"{dist_km} km away")

            src_title = f"Dispatch Order: Request #{request_id}"
            src_body = (
                f"Emergency dispatch order for {units} unit(s) of compatible blood to {hosp_display}. "
                f"Transit distance: {dist_km} km ({eta}). Please prepare for immediate pickup."
            )

            src_notif = self.provider.send_notification(
                recipient_type=s_type,
                recipient_id=s_id,
                title=src_title,
                message=src_body,
                metadata={
                    "request_id": request_id,
                    "units": units,
                    "hospital_id": hospital_id,
                    "distance_km": dist_km,
                },
            )
            dispatched.append(src_notif)

        return {
            "success": True,
            "request_id": request_id,
            "dispatched_count": len(dispatched),
            "notifications": dispatched,
        }
