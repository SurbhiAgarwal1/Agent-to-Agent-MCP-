"""FastAPI endpoints for local pharmacies, medicine catalog, and order fulfillment.

Implements online pharmacy delivery APIs (Netmeds / PharmEasy / Truemeds / Sanvivo).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.session import get_db
from app.models.pharmacy import Pharmacy, Medicine, MedicineInventory, MedicineOrder
from app.models.user import User, UserRole
from app.auth.dependencies import get_current_user, require_role
from app.schemas.pharmacy import (
    PharmacyResponse,
    PharmacyCreate,
    MedicineResponse,
    MedicineCreate,
    MedicineSubstitute,
    StockItemResponse,
    MedicineOrderCreate,
    MedicineOrderResponse,
    OrderItemResponse,
)
from app.services.pharmacy_service import PharmacyFulfillmentService, haversine_km

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy & Medicine Delivery"])


@router.get("/partners", response_model=List[PharmacyResponse])
def list_partner_pharmacies(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """List all registered local partner pharmacies (Sanvivo network)."""
    query = db.query(Pharmacy)
    if active_only:
        query = query.filter(Pharmacy.is_active == True)
    return query.all()


@router.post("/partners", response_model=PharmacyResponse, status_code=status.HTTP_201_CREATED)
def register_partner_pharmacy(
    payload: PharmacyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Onboard a new local pharmacy into the fulfillment network (Admin only)."""
    existing = db.query(Pharmacy).filter(Pharmacy.license_number == payload.license_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pharmacy with license {payload.license_number} is already registered.",
        )
    pharmacy = Pharmacy(**payload.model_dump())
    db.add(pharmacy)
    db.commit()
    db.refresh(pharmacy)
    return pharmacy


@router.get("/medicines", response_model=List[MedicineResponse])
def search_medicines(
    query: Optional[str] = Query(None, description="Search by brand name or active chemical salt"),
    rx_only: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """Search medications catalog with generic composition support."""
    q = db.query(Medicine)
    if query:
        term = f"%{query.strip()}%"
        q = q.filter(or_(Medicine.brand_name.ilike(term), Medicine.generic_name.ilike(term)))
    if rx_only is not None:
        q = q.filter(Medicine.rx_required == rx_only)
    return q.all()


@router.get("/medicines/{medicine_id}/substitutes", response_model=List[MedicineSubstitute])
def get_medicine_substitutes(
    medicine_id: int,
    db: Session = Depends(get_db),
):
    """Truemeds pattern: find cheaper generic equivalents sharing the exact active salt."""
    service = PharmacyFulfillmentService(db)
    substitutes = service.find_substitutes(medicine_id)
    return substitutes


@router.get("/stock", response_model=List[StockItemResponse])
def check_medicine_stock(
    medicine_id: int,
    user_lat: Optional[float] = Query(None, description="User latitude for distance calculation"),
    user_lon: Optional[float] = Query(None, description="User longitude for distance calculation"),
    db: Session = Depends(get_db),
):
    """Check live stock availability across all local partner pharmacies."""
    inventories = (
        db.query(MedicineInventory)
        .join(Pharmacy)
        .filter(MedicineInventory.medicine_id == medicine_id, Pharmacy.is_active == True)
        .all()
    )

    results = []
    for inv in inventories:
        distance = None
        if user_lat is not None and user_lon is not None:
            distance = haversine_km(user_lat, user_lon, inv.pharmacy.latitude, inv.pharmacy.longitude)

        results.append(
            StockItemResponse(
                inventory_id=inv.inventory_id,
                pharmacy_id=inv.pharmacy_id,
                pharmacy_name=inv.pharmacy.name,
                pharmacy_address=inv.pharmacy.address,
                distance_km=distance,
                medicine_id=inv.medicine_id,
                brand_name=inv.medicine.brand_name,
                generic_name=inv.medicine.generic_name,
                unit_price=inv.unit_price,
                units_available=inv.units_available,
                batch_number=inv.batch_number,
                expiry_date=inv.expiry_date,
            )
        )

    if user_lat is not None and user_lon is not None:
        results.sort(key=lambda x: (x.distance_km if x.distance_km is not None else 9999.0))
    return results


@router.post("/orders", response_model=MedicineOrderResponse, status_code=status.HTTP_201_CREATED)
def place_medicine_order(
    payload: MedicineOrderCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Place a quick hyperlocal medicine delivery order with automatic pharmacy allocation."""
    service = PharmacyFulfillmentService(db)

    # Default to central coords if not provided
    delivery_lat = payload.delivery_latitude or 28.6139
    delivery_lon = payload.delivery_longitude or 77.2090

    try:
        order = service.reserve_and_create_order(
            user_id=current_user.id if current_user else None,
            hospital_id=payload.hospital_id,
            delivery_address=payload.delivery_address,
            delivery_lat=delivery_lat,
            delivery_lon=delivery_lon,
            items=[item.model_dump() for item in payload.items],
            urgency=payload.urgency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Format response
    item_responses = [
        OrderItemResponse(
            item_id=it.item_id,
            medicine_id=it.medicine_id,
            brand_name=it.medicine.brand_name,
            generic_name=it.medicine.generic_name,
            quantity=it.quantity,
            unit_price=it.unit_price,
            is_substitute=it.is_substitute,
            original_medicine_name=it.original_medicine_name,
        )
        for it in order.items
    ]

    return MedicineOrderResponse(
        order_id=order.order_id,
        status=order.status,
        urgency=order.urgency,
        delivery_address=order.delivery_address,
        pharmacy_id=order.pharmacy_id,
        pharmacy_name=order.pharmacy.name if order.pharmacy else None,
        estimated_eta_minutes=order.estimated_eta_minutes,
        total_amount=order.total_amount,
        items=item_responses,
        created_at=order.created_at,
        delivered_at=order.delivered_at,
    )


@router.get("/orders/{order_id}", response_model=MedicineOrderResponse)
def get_order_tracking(
    order_id: int,
    db: Session = Depends(get_db),
):
    """Track live dispatch ETA and fulfillment status for an order."""
    order = db.query(MedicineOrder).filter(MedicineOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    item_responses = [
        OrderItemResponse(
            item_id=it.item_id,
            medicine_id=it.medicine_id,
            brand_name=it.medicine.brand_name,
            generic_name=it.medicine.generic_name,
            quantity=it.quantity,
            unit_price=it.unit_price,
            is_substitute=it.is_substitute,
            original_medicine_name=it.original_medicine_name,
        )
        for it in order.items
    ]

    return MedicineOrderResponse(
        order_id=order.order_id,
        status=order.status,
        urgency=order.urgency,
        delivery_address=order.delivery_address,
        pharmacy_id=order.pharmacy_id,
        pharmacy_name=order.pharmacy.name if order.pharmacy else None,
        estimated_eta_minutes=order.estimated_eta_minutes,
        total_amount=order.total_amount,
        items=item_responses,
        created_at=order.created_at,
        delivered_at=order.delivered_at,
    )
