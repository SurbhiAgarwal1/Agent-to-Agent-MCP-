from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field, model_validator
from datetime import date

class BloodRequestCreate(BaseModel):
    hospital_id: int
    required_blood_group: str = Field(pattern=r"^(A|B|AB|O)[+-]$")
    required_units: int = Field(gt=0, le=500)
    component_type: str = Field(default="packed_red_blood_cells", pattern="^(whole_blood|packed_red_blood_cells)$")
    required_by: Optional[datetime] = None
    priority: str = Field(default="urgent", pattern="^(normal|urgent|emergency)$")
    notes: str = Field(default="", max_length=300)

class BloodRequestPatch(BaseModel):
    required_units: Optional[int] = Field(default=None, gt=0, le=500)
    required_by: Optional[datetime] = None
    priority: Optional[str] = Field(default=None, pattern="^(normal|urgent|emergency)$")
    status: Optional[str] = Field(default=None, pattern="^(pending|processing|fulfilled|partially_fulfilled|cancelled)$")
    notes: Optional[str] = Field(default=None, max_length=300)

class InventoryPatch(BaseModel):
    available_units: int = Field(ge=0, le=10000)
    reserved_units: Optional[int] = Field(default=None, ge=0, le=10000)
    component_type: Optional[str] = Field(default=None, pattern="^(whole_blood|packed_red_blood_cells)$")

    @model_validator(mode="after")
    def validate_reservation(self):
        if self.reserved_units is not None and self.reserved_units > self.available_units:
            raise ValueError("reserved_units cannot exceed available_units")
        return self

T=TypeVar("T")
class Page(BaseModel,Generic[T]):
    items:list[T]
    total:int
    limit:int
    offset:int

class BankResponse(BaseModel):
    id:int; name:str; registration_number:str; address:str; city:str; district:str; state:str; pin_code:str
    latitude:float; longitude:float; contact_number:str; contact_email:str; operating_hours:str
    emergency_available:bool; verification_status:str; bank_type:str; last_updated:datetime
    available_blood_groups:list[str]
    distance_km:Optional[float]=None

class InventoryResponse(BaseModel):
    id:int; blood_bank_id:int; blood_group:str; component_type:str; available_units:int; reserved_units:int
    last_updated:datetime; expiry_date:datetime; availability_status:str
    blood_bank:Optional[dict]=None

class InventoryList(BaseModel): items:list[InventoryResponse]
class InventorySearchPage(Page[InventoryResponse]): pass

class HospitalResponse(BaseModel):
    id:int; name:str; hospital_type:str; address:str; city:str; district:str; state:str; pin_code:str
    latitude:float; longitude:float; emergency_contact:str; contact_email:str
    associated_blood_bank_ids:list[int]; operating_status:str

class BloodRequestResponse(BaseModel):
    id:int; hospital_id:int; required_blood_group:str; required_units:int; component_type:str
    request_date:datetime; required_by:datetime; priority:str; status:str
    assigned_blood_bank_ids:list[int]; notes:str

class InventoryStatistics(BaseModel):
    total_blood_banks:int; total_hospitals:int; units_by_blood_group:dict
    low_inventory_banks:int; zero_inventory_banks:int; inventory_by_city:list[dict]
    pending_requests:int; emergency_requests:int

class NearbyBanks(BaseModel): items:list[BankResponse]; total:int; radius_km:float
class AvailableGroups(BaseModel): blood_groups:list[str]

class BankNotificationCreate(BaseModel):
    blood_bank_id: int = Field(gt=0)
    blood_request_id: int = Field(gt=0)
    blood_group: str = Field(pattern=r"^(A|B|AB|O)[+-]$")
    inventory_blood_group: Optional[str] = Field(default=None, pattern=r"^(A|B|AB|O)[+-]$")
    component_type: str = Field(pattern="^(whole_blood|packed_red_blood_cells)$")
    required_units: int = Field(gt=0, le=500)
    channel: str = Field(pattern="^(email|sms|console)$")
    message: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)

class BankNotificationResponseInput(BaseModel):
    response_status: str = Field(pattern="^(accepted|partially_available|unavailable|rejected|pending)$")
    confirmed_available_units: Optional[int] = Field(default=None, ge=0, le=10000)
    rejection_reason: Optional[str] = Field(default=None, max_length=500)

class BankNotificationRecord(BaseModel):
    id: int; blood_bank_id: int; blood_request_id: int; blood_group: str; inventory_blood_group: str; component_type: str
    required_units: int; channel: str; delivery_status: str; sent_at: Optional[datetime]=None
    delivered_at: Optional[datetime]=None; response_status: str; response_at: Optional[datetime]=None
    confirmed_available_units: Optional[int]=None; rejection_reason: Optional[str]=None
    error_details: Optional[str]=None; idempotency_key: str
