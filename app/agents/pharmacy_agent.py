"""Pharmacy Agent for A2A Hyperlocal Medicine Fulfillment and Substitute Matching."""

import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.agents.a2a.message import A2AMessage, A2AMessageType
from app.services.pharmacy_service import PharmacyFulfillmentService
from app.models.pharmacy import Medicine

logger = logging.getLogger("app.agents.pharmacy_agent")


class PharmacyAgent:
    """Agent fulfilling medicine orders, checking hyperlocal stock, and recommending Truemeds substitutes."""

    NAME = "PharmacyAgent"

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def handle_a2a_message(self, message: A2AMessage) -> A2AMessage:
        """Handle incoming A2A structured requests."""
        if message.message_type == A2AMessageType.ERROR.value:
            return message

        payload = message.payload or {}
        action = payload.get("action", "check_stock")

        if action == "find_substitutes":
            return self._handle_find_substitutes(message, payload)
        elif action == "fulfill_order":
            return self._handle_fulfill_order(message, payload)
        else:
            return self._handle_check_stock(message, payload)

    def _handle_find_substitutes(self, message: A2AMessage, payload: Dict[str, Any]) -> A2AMessage:
        if self.db is None:
            return message.create_error(self.NAME, "Database session unavailable.")

        med_name = payload.get("medicine_name", "")
        med_id = payload.get("medicine_id")

        target = None
        if med_id:
            target = self.db.query(Medicine).filter(Medicine.medicine_id == med_id).first()
        elif med_name:
            target = self.db.query(Medicine).filter(Medicine.brand_name.ilike(f"%{med_name.strip()}%")).first()

        if not target:
            return message.create_error(self.NAME, f"Medicine '{med_name or med_id}' not found.")

        service = PharmacyFulfillmentService(self.db)
        substitutes = service.find_substitutes(target.medicine_id)

        return message.create_response(
            sender_agent=self.NAME,
            payload={
                "success": True,
                "target_brand": target.brand_name,
                "generic_salt": target.generic_name,
                "substitutes_count": len(substitutes),
                "substitutes": [s.model_dump() for s in substitutes],
            },
        )

    def _handle_check_stock(self, message: A2AMessage, payload: Dict[str, Any]) -> A2AMessage:
        if self.db is None:
            return message.create_error(self.NAME, "Database session unavailable.")

        service = PharmacyFulfillmentService(self.db)
        med_name = payload.get("medicine_name")
        med_id = payload.get("medicine_id")
        lat = payload.get("delivery_latitude", 28.6139)
        lon = payload.get("delivery_longitude", 77.2090)
        qty = payload.get("quantity", 1)

        target = None
        if med_id:
            target = self.db.query(Medicine).filter(Medicine.medicine_id == med_id).first()
        elif med_name:
            target = self.db.query(Medicine).filter(Medicine.brand_name.ilike(f"%{med_name.strip()}%")).first()

        if not target:
            return message.create_error(self.NAME, f"Medicine '{med_name or med_id}' not found.")

        match = service.locate_nearest_stock(
            medicine_id=target.medicine_id,
            delivery_lat=lat,
            delivery_lon=lon,
            quantity_needed=qty,
            allow_substitutes=True,
        )

        if not match:
            return message.create_response(
                sender_agent=self.NAME,
                payload={
                    "success": False,
                    "available": False,
                    "message": "Out of stock across nearby partner pharmacies.",
                },
            )

        return message.create_response(
            sender_agent=self.NAME,
            payload={
                "success": True,
                "available": True,
                "pharmacy_id": match["pharmacy"].pharmacy_id,
                "pharmacy_name": match["pharmacy"].name,
                "distance_km": match["distance_km"],
                "is_substitute": match["is_substitute"],
                "allocated_medicine": match["medicine"].brand_name,
                "unit_price": match["inventory"].unit_price,
            },
        )

    def _handle_fulfill_order(self, message: A2AMessage, payload: Dict[str, Any]) -> A2AMessage:
        if self.db is None:
            return message.create_error(self.NAME, "Database session unavailable.")

        service = PharmacyFulfillmentService(self.db)
        items = payload.get("items", [])
        lat = payload.get("delivery_latitude", 28.6139)
        lon = payload.get("delivery_longitude", 77.2090)
        address = payload.get("delivery_address", "Central District Hospital Delivery")
        urgency = payload.get("urgency", "MEDIUM")

        # Resolve medicine names to IDs if needed
        resolved_items = []
        for it in items:
            med_id = it.get("medicine_id")
            if not med_id and it.get("name"):
                med_obj = self.db.query(Medicine).filter(Medicine.brand_name.ilike(f"%{it['name'].strip()}%")).first()
                if med_obj:
                    med_id = med_obj.medicine_id

            if med_id:
                resolved_items.append({
                    "medicine_id": med_id,
                    "quantity": it.get("quantity", 1),
                    "allow_substitute": it.get("allow_substitute", True),
                })

        if not resolved_items:
            return message.create_error(self.NAME, "No valid medicines identified for order fulfillment.")

        try:
            order = service.reserve_and_create_order(
                user_id=payload.get("user_id"),
                hospital_id=payload.get("hospital_id"),
                delivery_address=address,
                delivery_lat=lat,
                delivery_lon=lon,
                items=resolved_items,
                urgency=urgency,
            )
            return message.create_response(
                sender_agent=self.NAME,
                payload={
                    "success": True,
                    "order_id": order.order_id,
                    "status": order.status,
                    "pharmacy_name": order.pharmacy.name if order.pharmacy else None,
                    "estimated_eta_minutes": order.estimated_eta_minutes,
                    "total_amount": order.total_amount,
                    "items_count": len(order.items),
                },
            )
        except Exception as exc:
            return message.create_error(self.NAME, f"Order fulfillment failed: {str(exc)}")
