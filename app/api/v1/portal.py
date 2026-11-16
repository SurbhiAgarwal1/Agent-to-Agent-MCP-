"""Donor and blood bank self-service: their own alerts, stock and answers (replaces one-time links in the UI)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.party_link import PartyLink
from app.models.user import User, UserRole
from app.services import party_service as ps

router = APIRouter(prefix="/portal", tags=["Portal"])


def _link(db: Session, user: User, kind: str) -> int:
    row = db.query(PartyLink).filter(PartyLink.user_id == user.id).first()
    if row is None or row.kind != kind:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is not a " + ("donor" if kind == "donor" else "blood bank") + " account.")
    return row.external_id


def _request_info(db: Session, request_id: Optional[int]) -> dict:
    request = db.query(BloodRequest).filter(BloodRequest.request_id == request_id).first() if request_id else None
    hospital = db.get(Hospital, request.hospital_id) if request else None
    return {"hospital_name": hospital.name if hospital else None, "hospital_address": hospital.address if hospital else None,
            "urgency": request.urgency if request else None, "units_needed": request.units_required if request else None}


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(PartyLink).filter(PartyLink.user_id == user.id).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No donor or blood bank profile is linked to this account.")
    if row.kind == "donor":
        d = ps.call("GET", f"{ps.donor_url()}/api/v1/donors/{row.external_id}")
        keep = ("id", "name", "blood_group", "city", "available", "donation_count", "latitude", "longitude")
        return {"kind": "donor", "profile": {k: d.get(k) for k in keep}}
    b = ps.call("GET", f"{ps.bank_url()}/api/v1/blood-banks/{row.external_id}")
    keep = ("id", "name", "address", "city", "contact_number", "latitude", "longitude")
    return {"kind": "blood_bank", "profile": {k: b.get(k) for k in keep}}


# ---------------------------------------------------------------- donor
class Availability(BaseModel):
    available: bool


class DonorAnswer(BaseModel):
    response: str = Field(pattern="^(accepted|declined)$")


@router.get("/donor/notifications")
def donor_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    donor_id = _link(db, user, "donor")
    data = ps.call("GET", f"{ps.donor_url()}/api/v1/donor-notifications", params={"donor_id": donor_id, "limit": 200})
    items = []
    for n in data.get("items", []):
        if not n.get("blood_request_id"):
            continue
        items.append({"id": n["id"], "blood_request_id": n["blood_request_id"], "blood_group": n.get("blood_group"),
                      "attempted_at": n.get("attempted_at"), "response_status": n.get("response_status"),
                      **_request_info(db, n["blood_request_id"])})
    return {"items": items}


@router.post("/donor/notifications/{notification_id}/respond")
def donor_respond(notification_id: int, body: DonorAnswer, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    donor_id = _link(db, user, "donor")
    ps.call("POST", f"{ps.donor_url()}/api/v1/donor-notifications/{notification_id}/answer",
            params={"response": body.response, "donor_id": donor_id})
    return {"ok": True, "response_status": body.response}


@router.patch("/donor/availability")
def donor_availability(body: Availability, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    donor_id = _link(db, user, "donor")
    return ps.call("PATCH", f"{ps.donor_url()}/api/v1/donors/{donor_id}/availability", json={"available": body.available})


# ----------------------------------------------------------- blood bank
class StockBody(BaseModel):
    available_units: int = Field(ge=0, le=10000)
    expiry_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    component_type: str = Field(default="packed_red_blood_cells", pattern="^(whole_blood|packed_red_blood_cells)$")


class BankAnswer(BaseModel):
    response_status: str = Field(pattern="^(accepted|partially_available|rejected)$")
    confirmed_available_units: Optional[int] = Field(default=None, ge=0, le=10000)
    rejection_reason: Optional[str] = Field(default=None, max_length=500)


def _inventory(bank_id: int) -> list[dict]:
    data = ps.call("GET", f"{ps.bank_url()}/api/v1/blood-banks/{bank_id}/inventory")
    return data.get("items", data) if isinstance(data, dict) else data


@router.get("/bank/inventory")
def bank_inventory(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bank_id = _link(db, user, "blood_bank")
    bank = ps.call("GET", f"{ps.bank_url()}/api/v1/blood-banks/{bank_id}")
    items = sorted(_inventory(bank_id), key=lambda i: i["blood_group"])
    return {"bank": bank, "items": items}


@router.put("/bank/inventory/{blood_group}")
def bank_set_stock(blood_group: str, body: StockBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bank_id = _link(db, user, "blood_bank")
    payload = {"available_units": body.available_units, "component_type": body.component_type}
    if body.expiry_date:
        payload["expiry_date"] = body.expiry_date
    return ps.call("PUT", f"{ps.bank_url()}/api/v1/blood-banks/{bank_id}/stock/{blood_group.upper()}", json=payload)


@router.get("/bank/notifications")
def bank_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bank_id = _link(db, user, "blood_bank")
    data = ps.call("GET", f"{ps.bank_url()}/api/v1/blood-bank-notifications", params={"blood_bank_id": bank_id, "limit": 200})
    stock = {(i["blood_group"], i["component_type"]): i["available_units"] for i in _inventory(bank_id)}
    items = []
    for n in data.get("items", []):
        items.append({**{k: n.get(k) for k in ("id", "blood_request_id", "blood_group", "inventory_blood_group", "required_units",
                                              "response_status", "confirmed_available_units", "rejection_reason")},
                      "attempted_at": n.get("sent_at") or n.get("created_at"),
                      "in_stock_units": stock.get((n["inventory_blood_group"], n["component_type"]), 0),
                      **_request_info(db, n.get("blood_request_id"))})
    return {"items": items}


@router.post("/bank/notifications/{notification_id}/respond")
def bank_respond(notification_id: int, body: BankAnswer, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bank_id = _link(db, user, "blood_bank")
    result = ps.call("POST", f"{ps.bank_url()}/api/v1/blood-bank-notifications/{notification_id}/answer",
                     params={"blood_bank_id": bank_id}, json=body.model_dump(exclude_none=True))
    return result
