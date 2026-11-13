"""Independent synthetic donor and donation-history REST API."""
from datetime import date, datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Optional
import hashlib
import json
from urllib.parse import parse_qs
from fastapi import Depends, FastAPI, HTTPException, Query, Header, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Donor, DonationHistory, DonorNotification
from .schemas import (AvailabilityPatch, DonationCreate, DonationPage, DonationResponse, DonorCreate,
                      DonorPatch, DonorResponse, DonorStatistics, NearbyDonors, NotificationCreate,
                      NotificationPage, NotificationResponse, Page, LegacyNotificationCreate,
                      DonorNotificationResponseInput)
from data_apis.geo import within_box

Base.metadata.create_all(bind=engine)
from .migrations import migrate_donor_notifications
app=FastAPI(title="Synthetic Individual Donor Data API",version="1.0.0",description="Fictional donor records only. Eligibility is informational and must be determined by qualified personnel.")

def _distance(a,b,lat,lon):
    dlat,dlon=radians(a-lat),radians(b-lon)
    return 6371*2*asin(sqrt(sin(dlat/2)**2+cos(radians(lat))*cos(radians(a))*sin(dlon/2)**2))

def _donor(d, distance=None):
    keys=("id","name","age","gender","blood_group","city","district","state","pin_code","latitude","longitude","phone","email","registration_date","last_donation_date","donation_count","available","preferred_contact_method","notification_consent","verification_status","eligibility_status","temporary_deferral_reason","last_updated")
    out={k:getattr(d,k) for k in keys}
    if distance is not None:out["distance_km"]=round(distance,2)
    return out

def _donation(x): return {k:getattr(x,k) for k in ("id","donor_id","donation_date","blood_bank_id","donation_type","donation_status","units_collected","next_eligible_date")}

def _notification(r):
    return {k:getattr(r,k) for k in ("id","donor_id","attempted_at","channel","status","consent_at_attempt","response","request_reference","blood_request_id","blood_group","delivery_status","response_status","sent_at","delivered_at","response_at","error_details","idempotency_key")}

def _validate_donor_response_link(row, token):
    from app.services.notification_providers.delivery import response_token_problem
    problem=response_token_problem(row,token)
    if problem=="used":raise HTTPException(409,"Response link is invalid or has already been used")
    if problem=="invalid":raise HTTPException(403,"Invalid response token")
    if problem=="expired":raise HTTPException(410,"Response link has expired")

def _record_donor_response(row, token, response, db):
    from app.services.notification_providers.delivery import token_digest
    _validate_donor_response_link(row,token)
    if row.delivery_status not in {"sent","delivered"}:raise HTTPException(409,"This notification was not delivered")
    now=datetime.now(timezone.utc)
    changed=db.query(DonorNotification).filter(
        DonorNotification.id==row.id,
        DonorNotification.response_status=="pending",
        DonorNotification.response_token_hash==token_digest(token),
        DonorNotification.response_token_expires_at>now,
        DonorNotification.delivery_status.in_(("sent","delivered")),
    ).update({
        DonorNotification.response_status:response,
        DonorNotification.response_at:now,
        DonorNotification.response:{"accepted":"confirmed","declined":"declined","unavailable":"unavailable","no_response":"no_response"}[response],
        DonorNotification.status:"responded" if response=="accepted" else response,
        DonorNotification.response_token_hash:None,
        DonorNotification.response_token_expires_at:None,
    },synchronize_session=False)
    if changed!=1:
        db.rollback()
        raise HTTPException(409,"Response link is invalid or has already been used")
    db.commit();db.refresh(row)
    return _notification(row)

@app.get("/health")
def health():return {"status":"healthy","api":"donor"}

@app.get("/api/v1/donors/statistics",response_model=DonorStatistics)
def statistics(db:Session=Depends(get_db)):
    group_counts={g:int(n) for g,n in db.query(Donor.blood_group,func.count(Donor.id)).group_by(Donor.blood_group).all()}
    city_counts=[{"city":c,"count":int(n)} for c,n in db.query(Donor.city,func.count(Donor.id)).group_by(Donor.city).order_by(func.count(Donor.id).desc()).all()]
    monthly=[{"month":m,"count":int(n)} for m,n in db.query(func.strftime("%Y-%m",DonationHistory.donation_date),func.count(DonationHistory.id)).group_by(func.strftime("%Y-%m",DonationHistory.donation_date)).order_by(func.strftime("%Y-%m",DonationHistory.donation_date)).all() if m]
    return {"total_donors":db.query(func.count(Donor.id)).scalar(),"donors_by_blood_group":group_counts,"donors_by_city":city_counts,"available_donors":db.query(func.count(Donor.id)).filter(Donor.available.is_(True)).scalar(),"pending_verification":db.query(func.count(Donor.id)).filter(Donor.eligibility_status=="pending_verification").scalar(),"temporarily_deferred":db.query(func.count(Donor.id)).filter(Donor.eligibility_status=="temporarily_deferred").scalar(),"donation_counts_by_month":monthly,"total_donation_records":db.query(func.count(DonationHistory.id)).scalar()}

@app.get("/api/v1/donors/available",response_model=Page[DonorResponse])
def available_donors(blood_group:Optional[str]=None,city:Optional[str]=None,district:Optional[str]=None,state:Optional[str]=None,verification_status:Optional[str]=None,eligibility_status:Optional[str]=None,notification_consent:Optional[bool]=None,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    return _list_donors(db,blood_group,city,district,state,True,verification_status,eligibility_status,notification_consent,limit,offset)

@app.get("/api/v1/donors/search",response_model=Page[DonorResponse])
@app.get("/api/v1/donors",response_model=Page[DonorResponse])
def search_donors(blood_group:Optional[str]=None,city:Optional[str]=None,district:Optional[str]=None,state:Optional[str]=None,available:Optional[bool]=None,verification_status:Optional[str]=None,eligibility_status:Optional[str]=None,notification_consent:Optional[bool]=None,minimum_donation_count:Optional[int]=Query(None,ge=0),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),sort_by:str=Query("updated",pattern="^(updated|availability)$"),db:Session=Depends(get_db)):
    return _list_donors(db,blood_group,city,district,state,available,verification_status,eligibility_status,notification_consent,limit,offset,minimum_donation_count,sort_by)

def _list_donors(db,blood_group=None,city=None,district=None,state=None,available=None,verification_status=None,eligibility_status=None,notification_consent=None,limit=50,offset=0,minimum_donation_count=None,sort_by="updated"):
    q=db.query(Donor)
    if blood_group:q=q.filter(Donor.blood_group==blood_group.upper())
    if city:q=q.filter(func.lower(Donor.city)==city.lower())
    if district:q=q.filter(func.lower(Donor.district)==district.lower())
    if state:q=q.filter(func.lower(Donor.state)==state.lower())
    if available is not None:q=q.filter(Donor.available.is_(available))
    if verification_status:q=q.filter(Donor.verification_status==verification_status)
    if eligibility_status:q=q.filter(Donor.eligibility_status==eligibility_status)
    if notification_consent is not None:q=q.filter(Donor.notification_consent.is_(notification_consent))
    if minimum_donation_count is not None:q=q.filter(Donor.donation_count>=minimum_donation_count)
    total=q.count()
    q=q.order_by(Donor.available.desc(),Donor.last_updated.desc()) if sort_by=="availability" else q.order_by(Donor.last_updated.desc())
    return {"items":[_donor(x) for x in q.offset(offset).limit(limit).all()],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/donors/nearby",response_model=NearbyDonors)
def nearby_donors(latitude:float=Query(ge=-90,le=90),longitude:float=Query(ge=-180,le=180),radius_km:float=Query(20,gt=0,le=500),blood_group:Optional[str]=None,available:Optional[bool]=True,limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    # Bounding-box filtering uses indexed coordinates before the exact haversine calculation.
    dlat=radius_km/110.574; dlon=radius_km/max(1,111.320*cos(radians(latitude)))
    q=db.query(Donor).filter(Donor.latitude.between(latitude-dlat,latitude+dlat),Donor.longitude.between(longitude-dlon,longitude+dlon))
    if blood_group:q=q.filter(Donor.blood_group==blood_group.upper())
    if available is not None:q=q.filter(Donor.available.is_(available))
    found=sorted((( _distance(d.latitude,d.longitude,latitude,longitude),d) for d in q.all()),key=lambda x:x[0])
    found=[x for x in found if x[0]<=radius_km][:limit]
    return {"items":[_donor(d,dist) for dist,d in found],"total":len(found),"radius_km":radius_km}

@app.get("/api/v1/donors/{donor_id}/donation-history",response_model=DonationPage)
def donor_history(donor_id:int,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    if not db.get(Donor,donor_id):raise HTTPException(404,"Donor not found")
    q=db.query(DonationHistory).filter(DonationHistory.donor_id==donor_id).order_by(DonationHistory.donation_date.desc())
    total=q.count()
    return {"items":[_donation(x) for x in q.offset(offset).limit(limit).all()],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/donation-history",response_model=DonationPage)
def donation_history(donor_id:Optional[int]=None,blood_bank_id:Optional[int]=None,donation_status:Optional[str]=None,from_date:Optional[date]=None,to_date:Optional[date]=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    q=db.query(DonationHistory)
    if donor_id:q=q.filter(DonationHistory.donor_id==donor_id)
    if blood_bank_id:q=q.filter(DonationHistory.blood_bank_id==blood_bank_id)
    if donation_status:q=q.filter(DonationHistory.donation_status==donation_status)
    if from_date:q=q.filter(DonationHistory.donation_date>=from_date)
    if to_date:q=q.filter(DonationHistory.donation_date<=to_date)
    total=q.count();rows=q.order_by(DonationHistory.donation_date.desc()).offset(offset).limit(limit).all()
    return {"items":[_donation(x) for x in rows],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/donors/{donor_id}",response_model=DonorResponse)
def donor_details(donor_id:int,db:Session=Depends(get_db)):
    d=db.get(Donor,donor_id)
    if not d:raise HTTPException(404,"Donor not found")
    return _donor(d)

@app.post("/api/v1/donors",status_code=201,response_model=DonorResponse)
def register_donor(payload:DonorCreate,db:Session=Depends(get_db)):
    if db.query(Donor.id).filter(Donor.email==payload.email).first():raise HTTPException(409,"Donor email already exists")
    data=payload.model_dump();data.update(registration_date=date.today(),donation_count=0,available=True,verification_status="pending",eligibility_status="pending_verification",last_updated=datetime.now(timezone.utc))
    d=Donor(**data);db.add(d);db.commit();db.refresh(d);return _donor(d)

@app.patch("/api/v1/donors/{donor_id}",response_model=DonorResponse)
def patch_donor(donor_id:int,payload:DonorPatch,db:Session=Depends(get_db)):
    d=db.get(Donor,donor_id)
    if not d:raise HTTPException(404,"Donor not found")
    for k,v in payload.model_dump(exclude_unset=True).items():setattr(d,k,v)
    d.last_updated=datetime.now(timezone.utc);db.commit();db.refresh(d);return _donor(d)

@app.patch("/api/v1/donors/{donor_id}/availability",response_model=DonorResponse)
def set_availability(donor_id:int,payload:AvailabilityPatch,db:Session=Depends(get_db)):
    d=db.get(Donor,donor_id)
    if not d:raise HTTPException(404,"Donor not found")
    d.available=payload.available;d.last_updated=datetime.now(timezone.utc);db.commit();db.refresh(d);return _donor(d)

@app.post("/api/v1/donors/{donor_id}/donation-history",status_code=201,response_model=DonationResponse)
def record_donation(donor_id:int,payload:DonationCreate,db:Session=Depends(get_db)):
    d=db.get(Donor,donor_id)
    if not d:raise HTTPException(404,"Donor not found")
    row=DonationHistory(donor_id=donor_id,**payload.model_dump());db.add(row)
    if payload.donation_status=="completed":
        d.donation_count+=1
        d.last_donation_date=max(d.last_donation_date or payload.donation_date,payload.donation_date)
        d.available=False
        d.last_updated=datetime.now(timezone.utc)
    db.commit();db.refresh(row);return _donation(row)

@app.get("/api/v1/donors/{donor_id}/notifications",response_model=Page[NotificationResponse])
def donor_notifications(donor_id:int,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    if not db.get(Donor,donor_id):raise HTTPException(404,"Donor not found")
    q=db.query(DonorNotification).filter(DonorNotification.donor_id==donor_id).order_by(DonorNotification.attempted_at.desc())
    rows=q.offset(offset).limit(limit).all()
    total=q.count()
    return {"items":[_notification(r) for r in rows],"total":total,"limit":limit,"offset":offset}

@app.get("/api/v1/donor-notifications",response_model=NotificationPage)
def notification_records(donor_id:Optional[int]=None,status:Optional[str]=None,delivery_status:Optional[str]=Query(None,pattern="^(pending|sent|delivered|failed|undelivered|simulated)$"),blood_request_id:Optional[int]=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    q=db.query(DonorNotification)
    if donor_id:q=q.filter(DonorNotification.donor_id==donor_id)
    if status:q=q.filter(DonorNotification.status==status)
    if delivery_status:q=q.filter(DonorNotification.delivery_status==delivery_status)
    if blood_request_id is not None:q=q.filter(DonorNotification.blood_request_id==blood_request_id)
    total=q.count();rows=q.order_by(DonorNotification.attempted_at.desc()).offset(offset).limit(limit).all()
    return {"items":[_notification(r) for r in rows],"total":total,"limit":limit,"offset":offset}

@app.post("/api/v1/donors/{donor_id}/notifications",status_code=201,response_model=NotificationResponse)
def log_legacy_notification(donor_id:int,payload:LegacyNotificationCreate,db:Session=Depends(get_db)):
    d=db.get(Donor,donor_id)
    if not d:raise HTTPException(404,"Donor not found")
    data=payload.model_dump()
    # Legacy callers can only create an explicitly simulated historical record.
    data["status"]="blocked_no_consent" if not d.notification_consent else "simulated"
    row=DonorNotification(donor_id=donor_id,attempted_at=datetime.now(timezone.utc),channel=data["channel"],status=data["status"],consent_at_attempt=d.notification_consent,response=None,request_reference=data["request_reference"],delivery_status="failed" if not d.notification_consent else "simulated",response_status="pending",error_details="Blocked because the donor had not consented" if not d.notification_consent else "Legacy API records simulation only")
    db.add(row);db.commit();db.refresh(row)
    return _notification(row)

@app.post("/api/v1/donor-notifications/send",status_code=201,response_model=NotificationResponse)
def send_donor_notification(payload:NotificationCreate,db:Session=Depends(get_db)):
    from app.services.notification_providers.delivery import deliver_notification,new_response_token,response_url,token_digest,response_token_expiry,twilio_callback_url
    donor=db.get(Donor,payload.donor_id) if hasattr(payload,"donor_id") else None
    # The recipient ID is deliberately passed as a route-independent field below by the MCP tool.
    donor_id=getattr(payload,"donor_id",None)
    if donor_id is None: raise HTTPException(422,"donor_id is required")
    donor=db.get(Donor,donor_id)
    if not donor:raise HTTPException(404,"Donor not found")
    existing=db.query(DonorNotification).filter_by(idempotency_key=payload.idempotency_key).first()
    if existing:return _notification(existing)
    if not donor.notification_consent:
        row=DonorNotification(donor_id=donor.id,attempted_at=datetime.now(timezone.utc),channel=payload.channel,status="blocked_no_consent",consent_at_attempt=False,request_reference=str(payload.blood_request_id),blood_request_id=payload.blood_request_id,blood_group=payload.blood_group,delivery_status="failed",response_status="pending",error_details="Blocked because the donor had not consented",idempotency_key=payload.idempotency_key)
        db.add(row);db.commit();db.refresh(row);return _notification(row)
    if not donor.available or donor.verification_status!="verified" or donor.eligibility_status!="eligible":
        raise HTTPException(409,"Donor is unavailable, unverified, or ineligible")
    from app.services.eligibility import is_donor_eligible
    if not is_donor_eligible(donor.last_donation_date):raise HTTPException(409,"Donor is within the recorded donation cooldown period")
    from app.services.compatibility import get_compatible_donor_groups
    compatible=get_compatible_donor_groups(payload.blood_group) if payload.component_type=="packed_red_blood_cells" else [payload.blood_group]
    if donor.blood_group not in compatible:raise HTTPException(409,"Donor blood group is not a candidate for this component and recipient group")
    if _distance(donor.latitude,donor.longitude,payload.hospital_latitude,payload.hospital_longitude)>payload.max_distance_km:raise HTTPException(409,"Donor is outside the requested location radius")
    token=new_response_token()
    row=DonorNotification(donor_id=donor.id,attempted_at=datetime.now(timezone.utc),channel=payload.channel,status="attempted",consent_at_attempt=True,response=None,request_reference=str(payload.blood_request_id),blood_request_id=payload.blood_request_id,blood_group=payload.blood_group,delivery_status="pending",response_status="pending",idempotency_key=payload.idempotency_key,response_token_hash=token_digest(token),response_token_expires_at=response_token_expiry())
    db.add(row);db.commit();db.refresh(row)
    body=payload.message+"\nRespond securely: "+response_url("donor",row.id,token)
    outcome=deliver_notification(payload.channel,donor.email,donor.phone,"Blood donation request",body,status_callback=twilio_callback_url("donor",row.id))
    row.delivery_status=outcome.status;row.sent_at=outcome.sent_at;row.error_details=outcome.error;row.status=outcome.status
    db.commit();db.refresh(row)
    return _notification(row)

@app.get("/api/v1/donor-notifications/{notification_id}",response_model=NotificationResponse)
def get_donor_notification(notification_id:int,db:Session=Depends(get_db)):
    row=db.get(DonorNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    return _notification(row)

@app.get("/api/v1/donor-notifications/{notification_id}/respond",response_class=HTMLResponse)
def donor_response_form(notification_id:int,token:str,db:Session=Depends(get_db)):
    row=db.get(DonorNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    _validate_donor_response_link(row,token)
    if row.delivery_status not in {"sent","delivered"}:raise HTTPException(409,"This notification was not delivered")
    return HTMLResponse(f"""<!doctype html><meta name='viewport' content='width=device-width'><h1>Donation request response</h1><form method='post' action='/api/v1/donor-notifications/{notification_id}/respond?token={token}'><label>Response <select name='response_status'><option value='accepted'>Accept</option><option value='declined'>Decline</option><option value='unavailable'>Unavailable</option><option value='no_response'>No response</option></select></label><button type='submit'>Submit response</button></form>""",headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

@app.post("/api/v1/donor-notifications/{notification_id}/respond",response_model=NotificationResponse)
async def respond_to_donor_notification(notification_id:int,request:Request,token:Optional[str]=None,x_response_token:Optional[str]=Header(default=None,alias="X-Response-Token"),db:Session=Depends(get_db)):
    row=db.get(DonorNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    secret=x_response_token or token
    raw=await request.body()
    try:
        if request.headers.get("content-type","").startswith("application/json"):
            values=json.loads(raw or b"{}")
        else:
            values={k:v[-1] for k,v in parse_qs(raw.decode()).items()}
        response=DonorNotificationResponseInput.model_validate(values).response_status
    except Exception as exc:raise HTTPException(422,"Invalid response status") from exc
    return _record_donor_response(row,secret,response,db)

@app.patch("/api/v1/donor-notifications/{notification_id}/delivery",response_model=NotificationResponse)
def update_donor_delivery(notification_id:int,delivery_status:str=Query(pattern="^(delivered|undelivered)$"),error_details:Optional[str]=None,x_provider_token:Optional[str]=Header(default=None,alias="X-Provider-Token"),db:Session=Depends(get_db)):
    import os,hmac
    expected=os.getenv("NOTIFICATION_WEBHOOK_TOKEN","")
    if not expected or not x_provider_token or not hmac.compare_digest(expected,x_provider_token):raise HTTPException(403,"Provider callback is not authorized")
    row=db.get(DonorNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    if row.delivery_status not in {"sent","delivered","undelivered"}:raise HTTPException(409,"Only sent notifications can receive delivery callbacks")
    row.delivery_status=delivery_status;row.delivered_at=datetime.now(timezone.utc) if delivery_status=="delivered" else None;row.error_details=error_details
    db.commit();db.refresh(row);return _notification(row)

@app.post("/api/v1/donor-notifications/{notification_id}/twilio-status")
async def donor_twilio_status(notification_id:int,request:Request,db:Session=Depends(get_db)):
    from app.services.notification_providers.delivery import twilio_signature_valid
    raw=await request.body();params={k:v[-1] for k,v in parse_qs(raw.decode()).items()}
    if not twilio_signature_valid("donor",notification_id,params,request.headers.get("X-Twilio-Signature","")):
        raise HTTPException(403,"Invalid SMS provider signature")
    row=db.get(DonorNotification,notification_id)
    if not row:raise HTTPException(404,"Notification not found")
    state=params.get("MessageStatus","").lower()
    if state=="delivered":row.delivery_status="delivered";row.delivered_at=datetime.now(timezone.utc)
    elif state in {"undelivered","failed"}:
        row.delivery_status="undelivered";row.delivered_at=None;row.error_details=params.get("ErrorMessage") or params.get("ErrorCode")
    db.commit();return {"accepted":True}

if __name__=="__main__":
    import os,uvicorn
    uvicorn.run("donor_api.main:app",host="0.0.0.0",port=int(os.getenv("DONOR_API_PORT","8106")))
