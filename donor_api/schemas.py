from datetime import date
from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field

class DonorCreate(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    age:int=Field(ge=18,le=65)
    blood_group:str=Field(pattern=r"^(A|B|AB|O)[+-]$")
    city:str; district:str; state:str; pin_code:str
    latitude:float=Field(ge=-90,le=90); longitude:float=Field(ge=-180,le=180)
    phone:str=Field(pattern=r"^\+91-00000-\d{5}$")
    email:str=Field(pattern=r"^[^@]+@example\.invalid$")
    preferred_contact_method:str=Field(default="email",pattern="^(email|sms|phone)$")
    notification_consent:bool=False

class DonorPatch(BaseModel):
    available:Optional[bool]=None
    preferred_contact_method:Optional[str]=Field(default=None,pattern="^(email|sms|phone)$")
    notification_consent:Optional[bool]=None
    verification_status:Optional[str]=Field(default=None,pattern="^(pending|verified|rejected)$")
    eligibility_status:Optional[str]=Field(default=None,pattern="^(pending_verification|eligible|temporarily_deferred|permanently_deferred)$")
    temporary_deferral_reason:Optional[str]=Field(default=None,max_length=100)

class AvailabilityPatch(BaseModel): available:bool

class DonationCreate(BaseModel):
    donation_date:date
    blood_bank_id:int=Field(gt=0)
    donation_type:str=Field(default="whole_blood",pattern="^(whole_blood|packed_red_blood_cells)$")
    donation_status:str=Field(default="completed",pattern="^(completed|deferred|cancelled)$")
    units_collected:int=Field(default=1,ge=0,le=2)
    next_eligible_date:Optional[date]=None

class NotificationCreate(BaseModel):
    donor_id:int=Field(gt=0)
    channel:str=Field(default="email",pattern="^(email|sms|console)$")
    blood_request_id:int=Field(gt=0)
    blood_group:str=Field(pattern=r"^(A|B|AB|O)[+-]$")
    component_type:str=Field(default="packed_red_blood_cells",pattern="^(whole_blood|packed_red_blood_cells)$")
    message:str=Field(min_length=1,max_length=4000)
    idempotency_key:str=Field(min_length=8,max_length=160)
    hospital_latitude:float=Field(ge=-90,le=90)
    hospital_longitude:float=Field(ge=-180,le=180)
    max_distance_km:float=Field(default=500,gt=0,le=500)

class LegacyNotificationCreate(BaseModel):
    channel:str=Field(default="email",pattern="^(email|sms|phone)$")
    status:str=Field(default="simulated",pattern="^(attempted|delivered|failed|no_response|responded|blocked_no_consent|simulated)$")
    response:Optional[str]=Field(default=None,pattern="^(confirmed|declined|delayed|en_route|no_response)$")
    request_reference:str=Field(default="synthetic",max_length=40)

class DonorNotificationResponseInput(BaseModel):
    response_status:str=Field(pattern="^(accepted|declined|unavailable|no_response)$")

T=TypeVar("T")
class Page(BaseModel,Generic[T]):
    items:list[T]; total:int; limit:int; offset:int

class DonorResponse(BaseModel):
    id:int; name:str; age:int; gender:Optional[str]=None; blood_group:str
    city:str; district:str; state:str; pin_code:str; latitude:float; longitude:float
    phone:str; email:str; registration_date:date; last_donation_date:Optional[date]=None
    donation_count:int; available:bool; preferred_contact_method:str; notification_consent:bool
    verification_status:str; eligibility_status:str; temporary_deferral_reason:Optional[str]=None
    last_updated:datetime; distance_km:Optional[float]=None

class NearbyDonors(BaseModel): items:list[DonorResponse]; total:int; radius_km:float
class DonationResponse(BaseModel):
    id:int; donor_id:int; donation_date:date; blood_bank_id:int; donation_type:str
    donation_status:str; units_collected:int; next_eligible_date:Optional[date]=None
class DonationPage(Page[DonationResponse]): pass
class NotificationResponse(BaseModel):
    id:int; donor_id:int; attempted_at:datetime; channel:str; status:str
    consent_at_attempt:bool; response:Optional[str]=None; request_reference:str
    blood_request_id:Optional[int]=None; blood_group:Optional[str]=None
    delivery_status:str="simulated"; response_status:str="pending"
    sent_at:Optional[datetime]=None; delivered_at:Optional[datetime]=None; response_at:Optional[datetime]=None
    error_details:Optional[str]=None; idempotency_key:Optional[str]=None
class NotificationPage(Page[NotificationResponse]): pass
class DonorStatistics(BaseModel):
    total_donors:int; donors_by_blood_group:dict[str,int]; donors_by_city:list[dict]
    available_donors:int; pending_verification:int; temporarily_deferred:int
    donation_counts_by_month:list[dict]; total_donation_records:int
