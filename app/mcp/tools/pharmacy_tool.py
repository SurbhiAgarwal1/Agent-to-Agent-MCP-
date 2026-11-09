"""MCP tools for medicine search, Truemeds-style substitute discovery, and hyperlocal stock check."""

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.services.pharmacy_service import PharmacyFulfillmentService
from app.models.pharmacy import Medicine

FIND_SUBSTITUTES_TOOL_NAME = "find_medicine_substitutes"
FIND_SUBSTITUTES_TOOL_DESC = (
    "Find cheaper generic equivalents and substitutes for a given medicine (Truemeds pattern) "
    "matching the exact active chemical composition/salt."
)

FIND_SUBSTITUTES_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "medicine_id": {
            "type": "integer",
            "description": "Unique identifier of the target medicine",
        },
        "medicine_name": {
            "type": "string",
            "description": "Optional brand name to lookup (e.g. 'Dolo 650', 'Augmentin')",
        },
    },
    "required": [],
}

FIND_SUBSTITUTES_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "target_medicine": {"type": "string"},
        "generic_salt": {"type": "string"},
        "substitutes_count": {"type": "integer"},
        "substitutes": {"type": "array"},
    },
    "required": ["success", "substitutes_count"],
}


def handle_find_medicine_substitutes(
    arguments: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute Truemeds-style substitute matching via MCP."""
    if db is None:
        return {
            "success": False,
            "error": "Database session required for medicine substitute search.",
            "substitutes_count": 0,
            "substitutes": [],
        }

    med_id = arguments.get("medicine_id")
    med_name = arguments.get("medicine_name")

    target = None
    if med_id:
        target = db.query(Medicine).filter(Medicine.medicine_id == med_id).first()
    elif med_name:
        target = db.query(Medicine).filter(Medicine.brand_name.ilike(f"%{med_name.strip()}%")).first()

    if not target:
        return {
            "success": False,
            "error": f"Medicine '{med_name or med_id}' not found in catalog.",
            "substitutes_count": 0,
            "substitutes": [],
        }

    service = PharmacyFulfillmentService(db)
    substitutes = service.find_substitutes(target.medicine_id)

    return {
        "success": True,
        "target_medicine": target.brand_name,
        "generic_salt": target.generic_name,
        "dosage_form": target.dosage_form,
        "substitutes_count": len(substitutes),
        "substitutes": [s.model_dump() for s in substitutes],
    }


CHECK_STOCK_TOOL_NAME = "check_pharmacy_stock"
CHECK_STOCK_TOOL_DESC = (
    "Check live inventory across local partner pharmacies (Sanvivo / Apollo pattern) "
    "with distance calculation and delivery radius validation."
)

CHECK_STOCK_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "medicine_id": {"type": "integer", "description": "Medicine ID to check"},
        "latitude": {"type": "number", "description": "Delivery latitude"},
        "longitude": {"type": "number", "description": "Delivery longitude"},
        "quantity_needed": {"type": "integer", "default": 1},
    },
    "required": ["medicine_id"],
}

CHECK_STOCK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "available": {"type": "boolean"},
        "pharmacy_name": {"type": "string"},
        "distance_km": {"type": "number"},
        "is_substitute": {"type": "boolean"},
    },
    "required": ["success", "available"],
}


def handle_check_pharmacy_stock(
    arguments: Dict[str, Any],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Check hyperlocal stock across partner pharmacies."""
    if db is None:
        return {"success": False, "available": False, "error": "Database session required."}

    med_id = arguments["medicine_id"]
    lat = arguments.get("latitude", 28.6139)
    lon = arguments.get("longitude", 77.2090)
    qty = arguments.get("quantity_needed", 1)

    service = PharmacyFulfillmentService(db)
    match = service.locate_nearest_stock(
        medicine_id=med_id,
        delivery_lat=lat,
        delivery_lon=lon,
        quantity_needed=qty,
        allow_substitutes=True,
    )

    if not match:
        return {
            "success": True,
            "available": False,
            "message": "No nearby partner pharmacy has sufficient stock for this request.",
        }

    return {
        "success": True,
        "available": True,
        "pharmacy_id": match["pharmacy"].pharmacy_id,
        "pharmacy_name": match["pharmacy"].name,
        "pharmacy_address": match["pharmacy"].address,
        "distance_km": match["distance_km"],
        "is_substitute": match["is_substitute"],
        "original_medicine": match.get("original_medicine"),
        "unit_price": match["inventory"].unit_price,
    }
