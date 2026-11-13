"""Independent synthetic blood-bank and emergency request REST API."""
import json
import os
import hmac
from urllib.parse import parse_qs
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Query, Header, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from .database import Base, engine, get_db
from .models import BloodBank, BloodInventory, BloodRequest, BloodBankNotification, Hospital
from .schemas import (AvailableGroups, BankResponse, BloodRequestCreate, BloodRequestPatch, BloodRequestResponse,
                      HospitalResponse, InventoryList, InventoryPatch, InventoryResponse, InventorySearchPage,
                      InventoryStatistics, NearbyBanks, Page, BankNotificationCreate,
                      BankNotificationResponseInput, BankNotificationRecord)
from data_apis.geo import within_box

Base.metadata.create_all(bind=engine)
from .migrations import migrate_component_inventory
app = FastAPI(title="Synthetic Blood Bank Data API", version="1.0.0", description="Fictional blood bank, inventory, hospital and request data. Blood group search is informational and does not make clinical compatibility decisions.")

def _distance(a, b, lat, lon):
    dlat, dlon = radians(a-lat), radians(b-lon)
    x = sin(dlat/2)**2 + cos(radians(lat))*cos(radians(a))*sin(dlon/2)**2
    return 6371 * 2 * asin(sqrt(x))

def _bank(b, distance=None):
    result = {k: getattr(b, k) for k in ("id", "name", "registration_number", "address", "city", "district", "state", "pin_code", "latitude", "longitude", "contact_number", "contact_email", "operating_hours", "emergency_available", "verification_status", "bank_type", "last_updated")}
    today=datetime.now(timezone.utc).date()
    result["available_blood_groups"] = sorted({i.blood_group for i in b.inventory if i.component_type in {"whole_blood","packed_red_blood_cells"} and i.available_units > i.reserved_units and i.availability_status=="available" and i.expiry_date.date()>=today})
    if distance is not None: result["distance_km"] = round(distance, 2)
    return result

def _inventory(i):
    return {k: getattr(i, k) for k in ("id", "blood_bank_id", "blood_group", "component_type", "available_units", "reserved_units", "last_updated", "expiry_date", "availability_status")}

def _hospital(h):
    result = {k: getattr(h, k) for k in ("id", "name", "hospital_type", "address", "city", "district", "state", "pin_code", "latitude", "longitude", "emergency_contact", "contact_email", "operating_status")}
    result["associated_blood_bank_ids"] = json.loads(h.associated_blood_bank_ids or "[]")
    return result

def _request(r):
    result = {k: getattr(r, k) for k in ("id", "hospital_id", "required_blood_group", "required_units", "component_type", "request_date", "required_by", "priority", "status", "notes")}
    result["assigned_blood_bank_ids"] = json.loads(r.assigned_blood_bank_ids or "[]")
    return result

@app.get("/health")
def health(): return {"status": "healthy", "api": "blood_bank"}

@app.get("/api/v1/blood-banks",response_model=Page[BankResponse])
def list_blood_banks(city: Optional[str] = None, district: Optional[str] = None, state: Optional[str] = None, blood_group: Optional[str] = None, verification_status: Optional[str] = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q = db.query(BloodBank)
    if city: q = q.filter(func.lower(BloodBank.city) == city.lower())
    if district: q = q.filter(func.lower(BloodBank.district) == district.lower())
    if state: q = q.filter(func.lower(BloodBank.state) == state.lower())
    if blood_group: q = q.join(BloodInventory).filter(BloodInventory.blood_group == blood_group.upper(), BloodInventory.available_units > 0)
    if verification_status: q = q.filter(BloodBank.verification_status == verification_status)
    total = q.distinct().count()
    rows = q.options(joinedload(BloodBank.inventory)).order_by(BloodBank.id).offset(offset).limit(limit).all()
    return {"items": [_bank(b) for b in rows], "total": total, "limit": limit, "offset": offset}

@app.get("/api/v1/blood-banks/search",response_model=Page[BankResponse])
def search_blood_banks(city: Optional[str] = None, blood_group: Optional[str] = None, district: Optional[str] = None, state: Optional[str] = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return list_blood_banks(city, district, state, blood_group, None, limit, offset, db)

@app.get("/api/v1/blood-banks/nearby",response_model=NearbyBanks)
def nearby_banks(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), radius_km: float = Query(20, gt=0, le=500), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    dlat=radius_km/110.574; dlon=radius_km/max(1,111.320*cos(radians(latitude)))
    candidates = db.query(BloodBank).options(joinedload(BloodBank.inventory)).filter(BloodBank.latitude.between(latitude-dlat,latitude+dlat),BloodBank.longitude.between(longitude-dlon,longitude+dlon)).all()
    found = [(_distance(b.latitude,b.longitude,latitude,longitude), b) for b in candidates]
    found = sorted((x for x in found if x[0] <= radius_km), key=lambda x:x[0])[:limit]
    return {"items": [_bank(b,d) for d,b in found], "total": len(found), "radius_km": radius_km}

@app.get("/api/v1/blood-banks/{blood_bank_id}",response_model=BankResponse)
def get_blood_bank(blood_bank_id: int, db: Session = Depends(get_db)):
    b = db.query(BloodBank).options(joinedload(BloodBank.inventory)).filter(BloodBank.id==blood_bank_id).first()
    if not b: raise HTTPException(404,"Blood bank not found")
    return _bank(b)

@app.get("/api/v1/blood-banks/{blood_bank_id}/inventory",response_model=InventoryList)
def bank_inventory(blood_bank_id: int, component_type: Optional[str] = Query(None, pattern="^(whole_blood|packed_red_blood_cells)$"), db: Session = Depends(get_db)):
    if not db.query(BloodBank.id).filter(BloodBank.id==blood_bank_id).first(): raise HTTPException(404,"Blood bank not found")
    q=db.query(BloodInventory).filter(BloodInventory.blood_bank_id==blood_bank_id)
    if component_type: q=q.filter(BloodInventory.component_type==component_type)
    return {"items": [_inventory(i) for i in q.order_by(BloodInventory.blood_group).all()]}

@app.get("/api/v1/blood-inventory/search",response_model=InventorySearchPage)
def search_inventory(blood_group: Optional[str] = None, component_type: Optional[str] = Query(None, pattern="^(whole_blood|packed_red_blood_cells)$"), city: Optional[str] = None, blood_bank_id: Optional[int] = Query(None, gt=0), minimum_available_units: int = Query(0, ge=0), availability_status: Optional[str] = Query(None, pattern="^(available|out_of_stock|expired)$"), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q=db.query(BloodInventory).join(BloodBank).filter(BloodInventory.available_units-BloodInventory.reserved_units>=minimum_available_units, BloodInventory.component_type.in_(["whole_blood","packed_red_blood_cells"]))
    if blood_group: q=q.filter(BloodInventory.blood_group==blood_group.upper())
    if component_type: q=q.filter(BloodInventory.component_type==component_type)
    if city: q=q.filter(func.lower(BloodBank.city)==city.lower())
    if blood_bank_id is not None: q=q.filter(BloodInventory.blood_bank_id==blood_bank_id)
    if availability_status:
        q=q.filter(BloodInventory.availability_status==availability_status)
        if availability_status=="available":q=q.filter(BloodInventory.expiry_date>=datetime.now(timezone.utc))
    total=q.count(); rows=q.order_by(BloodBank.id,BloodInventory.blood_group,BloodInventory.component_type).offset(offset).limit(limit).all()
    return {"items": [_inventory(i) | {"units_available":max(0,i.available_units-i.reserved_units),"blood_bank": {"id":i.blood_bank.id,"name":i.blood_bank.name,"city":i.blood_bank.city,"latitude":i.blood_bank.latitude,"longitude":i.blood_bank.longitude}} for i in rows], "total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/blood-inventory/summary",response_model=InventoryStatistics)
def inventory_summary(city: Optional[str] = None, blood_group: Optional[str] = None, db: Session = Depends(get_db)):
    q=db.query(BloodInventory.blood_group,func.sum(BloodInventory.available_units),func.sum(BloodInventory.reserved_units)).join(BloodBank).filter(BloodInventory.availability_status=="available",BloodInventory.expiry_date>=datetime.now(timezone.utc))
    if city: q=q.filter(func.lower(BloodBank.city)==city.lower())
    if blood_group: q=q.filter(BloodInventory.blood_group==blood_group.upper())
    by_group={g:{"available_units":int(a or 0),"reserved_units":int(r or 0)} for g,a,r in q.group_by(BloodInventory.blood_group).all()}
    zero = db.query(func.count(func.distinct(BloodBank.id))).join(BloodInventory).filter(or_(BloodInventory.available_units==0,BloodInventory.availability_status!="available",BloodInventory.expiry_date<datetime.now(timezone.utc)))
    if blood_group: zero=zero.filter(BloodInventory.blood_group==blood_group.upper())
    return {"total_blood_banks":db.query(func.count(BloodBank.id)).scalar(),"total_hospitals":db.query(func.count(Hospital.id)).scalar(),"units_by_blood_group":by_group,"low_inventory_banks":db.query(func.count(func.distinct(BloodInventory.blood_bank_id))).filter(BloodInventory.available_units.between(1,5)).scalar(),"zero_inventory_banks":zero.scalar(),"inventory_by_city":[{"city":c,"available_units":int(u or 0)} for c,u in db.query(BloodBank.city,func.sum(BloodInventory.available_units)).join(BloodInventory).group_by(BloodBank.city).all()],"pending_requests":db.query(func.count(BloodRequest.id)).filter(BloodRequest.status=="pending").scalar(),"emergency_requests":db.query(func.count(BloodRequest.id)).filter(BloodRequest.priority=="emergency").scalar()}

@app.get("/api/v1/blood-inventory/available-groups",response_model=AvailableGroups)
def available_groups(city: Optional[str] = None, db: Session = Depends(get_db)):
    q=db.query(BloodInventory.blood_group).filter(BloodInventory.available_units>BloodInventory.reserved_units,BloodInventory.component_type.in_(["whole_blood","packed_red_blood_cells"]),BloodInventory.availability_status=="available",BloodInventory.expiry_date>=datetime.now(timezone.utc))
    if city: q=q.join(BloodBank).filter(func.lower(BloodBank.city)==city.lower())
    return {"blood_groups":sorted({r[0] for r in q.distinct().all()})}

@app.patch("/api/v1/blood-banks/{blood_bank_id}/inventory/{blood_group}",response_model=InventoryResponse)
def update_inventory(blood_bank_id: int, blood_group: str, payload: InventoryPatch, component_type: str = Query("packed_red_blood_cells", pattern="^(whole_blood|packed_red_blood_cells)$"), db: Session = Depends(get_db)):
    if blood_group.upper() not in {"A+","A-","B+","B-","AB+","AB-","O+","O-"}: raise HTTPException(422,"Unsupported blood group")
    row=db.query(BloodInventory).filter_by(blood_bank_id=blood_bank_id,blood_group=blood_group.upper(),component_type=payload.component_type or component_type).first()
    if not row: raise HTTPException(404,"Inventory record not found")
    new_reserved=payload.reserved_units if payload.reserved_units is not None else row.reserved_units
    if new_reserved>payload.available_units:raise HTTPException(422,"reserved_units cannot exceed available_units")
    row.available_units=payload.available_units
    if payload.reserved_units is not None: row.reserved_units=payload.reserved_units
    row.availability_status="available" if row.available_units>row.reserved_units else "out_of_stock"
    row.last_updated=datetime.now(timezone.utc); db.commit(); db.refresh(row)
    return _inventory(row)

def _bank_notification(row):
    return {k:getattr(row,k) for k in ("id","blood_bank_id","blood_request_id","blood_group","inventory_blood_group","component_type","required_units","channel","delivery_status","sent_at","delivered_at","response_status","response_at","confirmed_available_units","rejection_reason","error_details","idempotency_key")}

def _validate_bank_response_link(row, token):
    from app.services.notification_providers.delivery import response_token_problem
    problem=response_token_problem(row,token)
    if problem=="used":raise HTTPException(409,"Response link is invalid or has already been used")
    if problem=="invalid":raise HTTPException(403,"Invalid response token")
    if problem=="expired":raise HTTPException(410,"Response link has expired")

def _record_bank_response(row, token, payload, db):
    from app.services.notification_providers.delivery import token_digest
    _validate_bank_response_link(row,token)
    if row.delivery_status not in {"sent","delivered"}:raise HTTPException(409,"This notification was not delivered to the recipient")
    if payload.response_status=="accepted" and not payload.confirmed_available_units:raise HTTPException(422,"Accepted response requires confirmed available units")
    if payload.response_status=="partially_available" and (payload.confirmed_available_units is None or not 0<payload.confirmed_available_units<row.required_units):raise HTTPException(422,"Partial response requires a positive quantity below the requested units")
    if payload.response_status in {"unavailable","rejected"} and not payload.rejection_reason:raise HTTPException(422,"Unavailable or rejected responses require a reason")
    now=datetime.now(timezone.utc)
    changed=db.query(BloodBankNotification).filter(
        BloodBankNotification.id==row.id,
        BloodBankNotification.response_status=="pending",
        BloodBankNotification.response_token_hash==token_digest(token),
        BloodBankNotification.response_token_expires_at>now,
        BloodBankNotification.delivery_status.in_(("sent","delivered")),
    ).update({
        BloodBankNotification.response_status:payload.response_status,
        BloodBankNotification.response_at:now,
        BloodBankNotification.confirmed_available_units:payload.confirmed_available_units,
        BloodBankNotification.rejection_reason:payload.rejection_reason,
        BloodBankNotification.response_token_hash:None,
        BloodBankNotification.response_token_expires_at:None,
    },synchronize_session=False)
    if changed!=1:
        db.rollback()
        raise HTTPException(409,"Response link is invalid or has already been used")
    db.commit();db.refresh(row)
    return _bank_notification(row)

@app.post("/api/v1/blood-bank-notifications", status_code=201, response_model=BankNotificationRecord)
def send_blood_bank_notification(payload: BankNotificationCreate, db: Session = Depends(get_db)):
    from app.services.notification_providers.delivery import deliver_notification, new_response_token, token_digest, response_token_expiry, response_url, twilio_callback_url

    existing=db.query(BloodBankNotification).filter_by(idempotency_key=payload.idempotency_key).first()
    if existing: return _bank_notification(existing)
    bank=db.get(BloodBank,payload.blood_bank_id)
    if not bank: raise HTTPException(404,"Blood bank not found")
    if not bank.emergency_available: raise HTTPException(409,"Blood bank is not marked emergency-available")
    inventory_group=payload.inventory_blood_group or payload.blood_group
    from app.services.compatibility import get_compatible_donor_groups
    compatible=[payload.blood_group] if payload.component_type=="whole_blood" else get_compatible_donor_groups(payload.blood_group)
    if inventory_group not in compatible:raise HTTPException(409,"Inventory group is not a candidate for the requested recipient group")
    stock=db.query(BloodInventory).filter_by(blood_bank_id=bank.id,blood_group=inventory_group,component_type=payload.component_type).first()
    if not stock or stock.availability_status!="available" or stock.expiry_date.date()<datetime.now(timezone.utc).date() or stock.available_units-stock.reserved_units<payload.required_units:
        raise HTTPException(409,"Insufficient current unreserved inventory for this group and component")
    token=new_response_token()
    row=BloodBankNotification(blood_bank_id=bank.id,blood_request_id=payload.blood_request_id,blood_group=payload.blood_group,inventory_blood_group=inventory_group,component_type=payload.component_type,required_units=payload.required_units,channel=payload.channel,delivery_status="pending",response_status="pending",idempotency_key=payload.idempotency_key,response_token_hash=token_digest(token),response_token_expires_at=response_token_expiry())
    db.add(row);db.commit();db.refresh(row)
    message=payload.message+f"\nRequested group: {payload.blood_group}; matching inventory: {inventory_group} {payload.component_type}.\nRespond securely: "+response_url("bank",row.id,token)
    outcome=deliver_notification(payload.channel,bank.contact_email,bank.contact_number,"Blood request response required",message,status_callback=twilio_callback_url("bank",row.id))
    row.delivery_status=outcome.status;row.sent_at=outcome.sent_at;row.error_details=outcome.error
    db.commit();db.refresh(row)
    return _bank_notification(row)

@app.get("/api/v1/blood-bank-notifications/{notification_id}",response_model=BankNotificationRecord)
def get_blood_bank_notification(notification_id:int,db:Session=Depends(get_db)):
    row=db.get(BloodBankNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    return _bank_notification(row)

@app.get("/api/v1/blood-bank-notifications",response_model=Page[BankNotificationRecord])
def list_blood_bank_notifications(blood_request_id:Optional[int]=None,blood_bank_id:Optional[int]=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    q=db.query(BloodBankNotification)
    if blood_request_id is not None:q=q.filter(BloodBankNotification.blood_request_id==blood_request_id)
    if blood_bank_id is not None:q=q.filter(BloodBankNotification.blood_bank_id==blood_bank_id)
    total=q.count();rows=q.order_by(BloodBankNotification.created_at.desc()).offset(offset).limit(limit).all()
    return {"items":[_bank_notification(x) for x in rows],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/blood-bank-notifications/{notification_id}/respond",response_class=HTMLResponse)
def blood_bank_response_form(notification_id:int,token:str,db:Session=Depends(get_db)):
    row=db.get(BloodBankNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    _validate_bank_response_link(row,token)
    if row.delivery_status not in {"sent","delivered"}:raise HTTPException(409,"This notification was not delivered")
    return HTMLResponse(f"""<!doctype html><meta name='viewport' content='width=device-width'><h1>Blood bank request response</h1><p>Request {row.blood_group} {row.component_type}: {row.required_units} unit(s)</p><form method='post' action='/api/v1/blood-bank-notifications/{notification_id}/respond?token={token}'><label>Response <select name='response_status'><option value='accepted'>Accepted</option><option value='partially_available'>Partially available</option><option value='unavailable'>Unavailable</option><option value='rejected'>Rejected</option></select></label><p>Confirmed available units <input type='number' name='confirmed_available_units' min='0'></p><p>Reason <input name='rejection_reason' maxlength='500'></p><button type='submit'>Submit response</button></form>""",headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

@app.post("/api/v1/blood-bank-notifications/{notification_id}/respond",response_model=BankNotificationRecord)
async def respond_to_blood_bank_notification(notification_id:int,request:Request,token:Optional[str]=None,x_response_token:Optional[str]=Header(default=None,alias="X-Response-Token"),db:Session=Depends(get_db)):
    row=db.get(BloodBankNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    secret=x_response_token or token
    raw=await request.body()
    try:
        if request.headers.get("content-type","").startswith("application/json"):
            values=json.loads(raw or b"{}")
        else:
            values={k:v[-1] for k,v in parse_qs(raw.decode()).items()}
            if values.get("confirmed_available_units") == "":
                values["confirmed_available_units"] = None
        payload=BankNotificationResponseInput.model_validate(values)
    except Exception as exc:raise HTTPException(422,"Invalid blood-bank response") from exc
    return _record_bank_response(row,secret,payload,db)

@app.patch("/api/v1/blood-bank-notifications/{notification_id}/delivery",response_model=BankNotificationRecord)
def update_blood_bank_delivery(notification_id:int,delivery_status:str=Query(pattern="^(delivered|undelivered)$"),error_details:Optional[str]=None,x_provider_token:Optional[str]=Header(default=None,alias="X-Provider-Token"),db:Session=Depends(get_db)):
    expected=os.getenv("NOTIFICATION_WEBHOOK_TOKEN","")
    if not expected or not x_provider_token or not hmac.compare_digest(expected,x_provider_token):raise HTTPException(403,"Provider callback is not authorized")
    row=db.get(BloodBankNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    if row.delivery_status not in {"sent","delivered","undelivered"}:raise HTTPException(409,"Only sent notifications can receive delivery callbacks")
    row.delivery_status=delivery_status;row.delivered_at=datetime.now(timezone.utc) if delivery_status=="delivered" else None;row.error_details=error_details
    db.commit();db.refresh(row);return _bank_notification(row)

@app.post("/api/v1/blood-bank-notifications/{notification_id}/twilio-status")
async def blood_bank_twilio_status(notification_id:int,request:Request,db:Session=Depends(get_db)):
    from app.services.notification_providers.delivery import twilio_signature_valid
    raw=await request.body();params={k:v[-1] for k,v in parse_qs(raw.decode()).items()}
    if not twilio_signature_valid("bank",notification_id,params,request.headers.get("X-Twilio-Signature","")):
        raise HTTPException(403,"Invalid SMS provider signature")
    row=db.get(BloodBankNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    state=params.get("MessageStatus","").lower()
    if state=="delivered":row.delivery_status="delivered";row.delivered_at=datetime.now(timezone.utc)
    elif state in {"undelivered","failed"}:
        row.delivery_status="undelivered";row.delivered_at=None;row.error_details=params.get("ErrorMessage") or params.get("ErrorCode")
    db.commit();return {"accepted":True}

@app.get("/api/v1/hospitals",response_model=Page[HospitalResponse])
def list_hospitals(city: Optional[str] = None, state: Optional[str] = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q=db.query(Hospital)
    if city:q=q.filter(func.lower(Hospital.city)==city.lower())
    if state:q=q.filter(func.lower(Hospital.state)==state.lower())
    total=q.count(); rows=q.order_by(Hospital.id).offset(offset).limit(limit).all()
    return {"items":[_hospital(h) for h in rows],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/hospitals/{hospital_id}",response_model=HospitalResponse)
def get_hospital(hospital_id:int,db:Session=Depends(get_db)):
    h=db.get(Hospital,hospital_id)
    if not h: raise HTTPException(404,"Hospital not found")
    return _hospital(h)

@app.get("/api/v1/blood-requests",response_model=Page[BloodRequestResponse])
def list_requests(hospital_id:Optional[int]=None,status:Optional[str]=None,priority:Optional[str]=None,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    q=db.query(BloodRequest)
    if hospital_id:q=q.filter(BloodRequest.hospital_id==hospital_id)
    if status:q=q.filter(BloodRequest.status==status)
    if priority:q=q.filter(BloodRequest.priority==priority)
    total=q.count(); rows=q.order_by(BloodRequest.request_date.desc()).offset(offset).limit(limit).all()
    return {"items":[_request(r) for r in rows],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/blood-requests/{request_id}",response_model=BloodRequestResponse)
def get_request(request_id:int,db:Session=Depends(get_db)):
    r=db.get(BloodRequest,request_id)
    if not r: raise HTTPException(404,"Blood request not found")
    return _request(r)

@app.post("/api/v1/blood-requests",status_code=201,response_model=BloodRequestResponse)
def create_request(payload:BloodRequestCreate,db:Session=Depends(get_db)):
    h=db.get(Hospital,payload.hospital_id)
    if not h: raise HTTPException(404,"Hospital not found")
    now=datetime.now(timezone.utc); r=BloodRequest(hospital_id=h.id,required_blood_group=payload.required_blood_group.upper(),required_units=payload.required_units,component_type=payload.component_type,request_date=now,required_by=payload.required_by or now+timedelta(hours=24),priority=payload.priority,status="pending",assigned_blood_bank_ids="[]",notes=payload.notes)
    db.add(r); db.commit(); db.refresh(r); return _request(r)

@app.patch("/api/v1/blood-requests/{request_id}",response_model=BloodRequestResponse)
def patch_request(request_id:int,payload:BloodRequestPatch,db:Session=Depends(get_db)):
    r=db.get(BloodRequest,request_id)
    if not r: raise HTTPException(404,"Blood request not found")
    for k,v in payload.model_dump(exclude_unset=True).items(): setattr(r,k,v)
    db.commit(); db.refresh(r); return _request(r)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("blood_bank_api.main:app", host="0.0.0.0", port=int(__import__("os").getenv("BLOOD_BANK_API_PORT","8105")))
