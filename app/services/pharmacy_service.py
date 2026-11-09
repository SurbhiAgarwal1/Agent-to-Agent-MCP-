"""Pharmacy & Medicine inventory fulfillment service.

Implements architectural patterns from:
- Truemeds: Active salt/chemical substitute matching when requested brand is scarce or out of stock.
- Sanvivo / Apollo 24x7: Hyperlocal partner pharmacy selection based on proximity and inventory hold leases.
"""

from datetime import datetime, timezone
import math
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.models.pharmacy import Pharmacy, Medicine, MedicineInventory, MedicineOrder, MedicineOrderItem
from app.models.hospital import Hospital
from app.schemas.pharmacy import MedicineSubstitute, StockItemResponse


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


class PharmacyFulfillmentService:
    """Hyperlocal pharmacy matching, substitute recommendations, and inventory hold leases."""

    def __init__(self, db: Session):
        self.db = db

    def find_substitutes(self, medicine_id: int) -> List[MedicineSubstitute]:
        """Truemeds pattern: find alternate brands with the exact same active generic composition."""
        target = self.db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
        if not target:
            return []

        # Find medicines with matching generic salt/composition but different brand
        equivalents = (
            self.db.query(Medicine)
            .filter(
                func.lower(Medicine.generic_name) == target.generic_name.lower(),
                Medicine.medicine_id != target.medicine_id,
                func.lower(Medicine.dosage_form) == target.dosage_form.lower(),
            )
            .all()
        )

        substitutes = []
        for eq in equivalents:
            # Query current available stock and representative price
            inv_records = (
                self.db.query(MedicineInventory)
                .filter(MedicineInventory.medicine_id == eq.medicine_id)
                .all()
            )
            total_available = sum(inv.units_available for inv in inv_records)
            if inv_records:
                avg_price = sum(inv.unit_price for inv in inv_records) / len(inv_records)
            else:
                avg_price = 0.0

            substitutes.append(
                MedicineSubstitute(
                    medicine_id=eq.medicine_id,
                    brand_name=eq.brand_name,
                    generic_name=eq.generic_name,
                    manufacturer=eq.manufacturer,
                    dosage_form=eq.dosage_form,
                    strength=eq.strength,
                    unit_price=round(avg_price, 2),
                    available_units=total_available,
                )
            )

        return substitutes

    def locate_nearest_stock(
        self,
        medicine_id: int,
        delivery_lat: float,
        delivery_lon: float,
        quantity_needed: int = 1,
        allow_substitutes: bool = True,
    ) -> Optional[Dict]:
        """Hyperlocal routing (Sanvivo/Apollo pattern): locate closest partner pharmacy with available stock."""
        # 1. First search for the exact medicine requested
        eligible_inventories = (
            self.db.query(MedicineInventory, Pharmacy)
            .join(Pharmacy, MedicineInventory.pharmacy_id == Pharmacy.pharmacy_id)
            .filter(
                MedicineInventory.medicine_id == medicine_id,
                Pharmacy.is_active == True,
            )
            .all()
        )

        ranked = []
        for inv, pharm in eligible_inventories:
            if inv.units_available >= quantity_needed:
                dist = haversine_km(delivery_lat, delivery_lon, pharm.latitude, pharm.longitude)
                if dist <= pharm.delivery_radius_km:
                    ranked.append({
                        "inventory": inv,
                        "pharmacy": pharm,
                        "medicine": inv.medicine,
                        "distance_km": dist,
                        "is_substitute": False,
                        "original_medicine": None,
                    })

        ranked.sort(key=lambda x: x["distance_km"])
        if ranked:
            return ranked[0]

        # 2. If exact brand is not available within delivery radius and substitutes allowed, search equivalents
        if allow_substitutes:
            substitutes = self.find_substitutes(medicine_id)
            for sub in substitutes:
                sub_inventories = (
                    self.db.query(MedicineInventory, Pharmacy)
                    .join(Pharmacy, MedicineInventory.pharmacy_id == Pharmacy.pharmacy_id)
                    .filter(
                        MedicineInventory.medicine_id == sub.medicine_id,
                        Pharmacy.is_active == True,
                    )
                    .all()
                )
                for inv, pharm in sub_inventories:
                    if inv.units_available >= quantity_needed:
                        dist = haversine_km(delivery_lat, delivery_lon, pharm.latitude, pharm.longitude)
                        if dist <= pharm.delivery_radius_km:
                            orig_med = self.db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
                            return {
                                "inventory": inv,
                                "pharmacy": pharm,
                                "medicine": inv.medicine,
                                "distance_km": dist,
                                "is_substitute": True,
                                "original_medicine": orig_med.brand_name if orig_med else None,
                            }

        return None

    def reserve_and_create_order(
        self,
        user_id: Optional[int],
        hospital_id: Optional[int],
        delivery_address: str,
        delivery_lat: float,
        delivery_lon: float,
        items: List[Dict],
        urgency: str = "MEDIUM",
    ) -> MedicineOrder:
        """Create order and lock inventory with a reserved stock lease."""
        total_amount = 0.0
        allocated_pharmacy = None
        order_items_to_create = []

        for item in items:
            med_id = item["medicine_id"]
            qty = item["quantity"]
            allow_sub = item.get("allow_substitute", True)

            match = self.locate_nearest_stock(
                medicine_id=med_id,
                delivery_lat=delivery_lat,
                delivery_lon=delivery_lon,
                quantity_needed=qty,
                allow_substitutes=allow_sub,
            )

            if not match:
                raise ValueError(f"Unable to fulfill medicine ID {med_id} within local delivery radius.")

            inv = match["inventory"]
            pharm = match["pharmacy"]
            allocated_pharmacy = pharm

            # Apply stock lease / reservation hold
            inv.units_reserved += qty
            self.db.add(inv)

            cost = round(inv.unit_price * qty, 2)
            total_amount += cost

            order_items_to_create.append({
                "medicine_id": inv.medicine_id,
                "quantity": qty,
                "unit_price": inv.unit_price,
                "is_substitute": match["is_substitute"],
                "original_medicine_name": match["original_medicine"],
            })

        # Calculate ETA (Apollo/PharmEasy quick delivery model: base 15 mins prep + 3 mins per km)
        distance = haversine_km(delivery_lat, delivery_lon, allocated_pharmacy.latitude, allocated_pharmacy.longitude) if allocated_pharmacy else 5.0
        eta_minutes = max(20, int(15 + (distance * 3.5)))

        order = MedicineOrder(
            user_id=user_id,
            hospital_id=hospital_id,
            pharmacy_id=allocated_pharmacy.pharmacy_id if allocated_pharmacy else None,
            status="MATCHED",
            urgency=urgency.upper(),
            delivery_address=delivery_address,
            delivery_latitude=delivery_lat,
            delivery_longitude=delivery_lon,
            estimated_eta_minutes=eta_minutes,
            total_amount=round(total_amount, 2),
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        for oi in order_items_to_create:
            item_record = MedicineOrderItem(
                order_id=order.order_id,
                medicine_id=oi["medicine_id"],
                quantity=oi["quantity"],
                unit_price=oi["unit_price"],
                is_substitute=oi["is_substitute"],
                original_medicine_name=oi["original_medicine_name"],
            )
            self.db.add(item_record)

        self.db.commit()
        self.db.refresh(order)
        return order
