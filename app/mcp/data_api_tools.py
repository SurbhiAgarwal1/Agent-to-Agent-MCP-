"""Official FastMCP tools backed by the two independent synthetic data APIs."""
import asyncio
import os
from typing import Any, Literal
import httpx
from mcp.server.fastmcp import FastMCP

BANK_API=os.getenv("BLOOD_BANK_API_URL","http://127.0.0.1:8105").rstrip("/")
DONOR_API=os.getenv("DONOR_API_URL","http://127.0.0.1:8106").rstrip("/")
TIMEOUT=float(os.getenv("DATA_API_TIMEOUT_SECONDS","8"))
RETRIES=max(0,int(os.getenv("DATA_API_MAX_RETRIES","2")))

async def _request(base:str,method:str,path:str,*,params=None,json_body=None):
    last=None
    for attempt in range(RETRIES+1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT,connect=min(TIMEOUT,3))) as client:
                response=await client.request(method,base+path,params=params,json=json_body)
            if (response.status_code>=500 or response.status_code in {408,429}) and attempt<RETRIES:
                await asyncio.sleep(.15*(attempt+1));continue
            if response.is_error:
                try:detail=response.json().get("detail",response.text)
                except ValueError:detail=response.text
                raise ValueError(f"Data API returned HTTP {response.status_code}: {detail}")
            return response.json()
        except (httpx.TimeoutException,httpx.ConnectError) as exc:
            last=exc
            if attempt>=RETRIES:break
            await asyncio.sleep(.15*(attempt+1))
    if isinstance(last,httpx.TimeoutException):raise RuntimeError(f"Data API timed out after {TIMEOUT:g}s ({method} {path})") from last
    raise RuntimeError(f"Data API unavailable ({method} {path}): {last}") from last

def _limit(limit:int,offset:int):
    if not 1<=limit<=200:raise ValueError("limit must be between 1 and 200")
    if offset<0:raise ValueError("offset must be non-negative")

def register_data_api_tools(mcp:FastMCP)->None:
    """Register the requested blood bank and donor data tools on the sole SDK server."""
    @mcp.tool()
    async def list_blood_banks(city:str|None=None,state:str|None=None,blood_group:str|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """List fictional blood banks with optional city, state and blood-group inventory filters. Always paginate; blood group is a search attribute, not a compatibility decision."""
        _limit(limit,offset);return await _request(BANK_API,"GET","/api/v1/blood-banks",params={k:v for k,v in locals().copy().items() if k in {"city","state","blood_group","limit","offset"} and v is not None})
    @mcp.tool()
    async def get_blood_bank_details(blood_bank_id:int)->dict[str, Any]:
        """Retrieve one blood bank's location, fictional contact channels, verification and available blood groups."""
        return await _request(BANK_API,"GET",f"/api/v1/blood-banks/{blood_bank_id}")
    @mcp.tool()
    async def search_blood_banks(city:str|None=None,blood_group:str|None=None,district:str|None=None,state:str|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """Search blood banks by geography or recorded inventory group, with bounded pagination."""
        _limit(limit,offset);return await _request(BANK_API,"GET","/api/v1/blood-banks/search",params={k:v for k,v in locals().copy().items() if k in {"city","blood_group","district","state","limit","offset"} and v is not None})
    @mcp.tool()
    async def find_nearby_blood_banks(latitude:float,longitude:float,radius_km:float=20,limit:int=50)->dict[str, Any]:
        """Find blood banks inside a geographic radius, ordered by distance; coordinates are latitude/longitude and radius is kilometres."""
        if not -90<=latitude<=90 or not -180<=longitude<=180 or not 0<radius_km<=500:raise ValueError("coordinates or radius_km are outside supported bounds")
        _limit(limit,0);return await _request(BANK_API,"GET","/api/v1/blood-banks/nearby",params={"latitude":latitude,"longitude":longitude,"radius_km":radius_km,"limit":limit})
    @mcp.tool()
    async def get_blood_bank_inventory(blood_bank_id:int,component_type:Literal["whole_blood","packed_red_blood_cells"]|None=None)->dict[str, Any]:
        """Get every inventory group and component for one bank; stock is informational and not a clinical recommendation."""
        return await _request(BANK_API,"GET",f"/api/v1/blood-banks/{blood_bank_id}/inventory",params={"component_type":component_type} if component_type else None)
    @mcp.tool()
    async def search_blood_inventory(blood_group:str|None=None,component_type:Literal["whole_blood","packed_red_blood_cells"]|None=None,city:str|None=None,blood_bank_id:int|None=None,minimum_available_units:int=0,availability_status:Literal["available","out_of_stock","expired"]|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """Search Whole Blood or PRBC inventory by group, component, city, bank, availability and unreserved stock. Compatibility decisions remain with qualified clinical workflows."""
        _limit(limit,offset);params={k:v for k,v in locals().copy().items() if k in {"blood_group","component_type","city","blood_bank_id","minimum_available_units","availability_status","limit","offset"} and v is not None};return await _request(BANK_API,"GET","/api/v1/blood-inventory/search",params=params)
    @mcp.tool()
    async def get_available_blood_groups(city:str|None=None)->dict[str, Any]:
        """List blood groups with at least one recorded available unit, optionally for a city."""
        return await _request(BANK_API,"GET","/api/v1/blood-inventory/available-groups",params={"city":city} if city else None)
    @mcp.tool()
    async def get_inventory_statistics(city:str|None=None,blood_group:str|None=None)->dict[str, Any]:
        """Return aggregate blood-bank, hospital, stock, low/zero stock and request statistics."""
        return await _request(BANK_API,"GET","/api/v1/blood-inventory/summary",params={k:v for k,v in {"city":city,"blood_group":blood_group}.items() if v})
    @mcp.tool()
    async def list_hospitals(city:str|None=None,state:str|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """List fictional hospitals with optional city/state filters and pagination."""
        _limit(limit,offset);return await _request(BANK_API,"GET","/api/v1/hospitals",params={k:v for k,v in {"city":city,"state":state,"limit":limit,"offset":offset}.items() if v is not None})
    @mcp.tool()
    async def get_hospital_details(hospital_id:int)->dict[str, Any]:
        """Retrieve one hospital profile, coordinates and associated synthetic bank IDs."""
        return await _request(BANK_API,"GET",f"/api/v1/hospitals/{hospital_id}")
    @mcp.tool()
    async def create_blood_request(hospital_id:int,required_blood_group:str,required_units:int,component_type:Literal["whole_blood","packed_red_blood_cells"]="packed_red_blood_cells",priority:str="urgent",notes:str="")->dict[str, Any]:
        """Create an emergency coordination request at a registered hospital. Does not approve transfusion or guarantee fulfillment."""
        if not 1<=required_units<=500:raise ValueError("required_units must be between 1 and 500")
        body={"hospital_id":hospital_id,"required_blood_group":required_blood_group,"required_units":required_units,"component_type":component_type,"priority":priority,"notes":notes}
        return await _request(BANK_API,"POST","/api/v1/blood-requests",json_body=body)
    @mcp.tool()
    async def get_blood_request(request_id:int)->dict[str, Any]:
        """Retrieve an emergency blood request and its lifecycle fields."""
        return await _request(BANK_API,"GET",f"/api/v1/blood-requests/{request_id}")
    @mcp.tool()
    async def update_blood_request(request_id:int,required_units:int|None=None,priority:str|None=None,status:str|None=None,notes:str|None=None)->dict[str, Any]:
        """Update allowed request quantity, priority, status or notes; status transitions should reflect coordinator workflow."""
        body={k:v for k,v in {"required_units":required_units,"priority":priority,"status":status,"notes":notes}.items() if v is not None}
        if not body:raise ValueError("At least one request field must be provided")
        return await _request(BANK_API,"PATCH",f"/api/v1/blood-requests/{request_id}",json_body=body)
    @mcp.tool()
    async def update_blood_inventory(blood_bank_id:int,blood_group:str,available_units:int,reserved_units:int|None=None,component_type:Literal["whole_blood","packed_red_blood_cells"]="packed_red_blood_cells")->dict[str, Any]:
        """Update a bank's recorded stock counts. Inventory updates are auditable data operations, not medical matching decisions."""
        if not 0<=available_units<=10000:raise ValueError("available_units must be between 0 and 10000")
        body={"available_units":available_units,"component_type":component_type}
        if reserved_units is not None:body["reserved_units"]=reserved_units
        return await _request(BANK_API,"PATCH",f"/api/v1/blood-banks/{blood_bank_id}/inventory/{blood_group}",json_body=body,params={"component_type":component_type})

    @mcp.tool()
    async def search_donors(blood_group:str|None=None,city:str|None=None,district:str|None=None,state:str|None=None,available:bool|None=None,verification_status:str|None=None,eligibility_status:str|None=None,notification_consent:bool|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """Search fictional donors with filters and pagination. Availability and age do not establish clinical eligibility; check verification and qualified review."""
        _limit(limit,offset);params={k:v for k,v in locals().copy().items() if k in {"blood_group","city","district","state","available","verification_status","eligibility_status","limit","offset"} and v is not None}
        if notification_consent is not None:params["notification_consent"]=notification_consent
        return await _request(DONOR_API,"GET","/api/v1/donors/search",params=params)
    @mcp.tool()
    async def get_donor_details(donor_id:int)->dict[str, Any]:
        """Retrieve one fictional donor profile, including consent and verification fields; use only for an authorized operational need."""
        return await _request(DONOR_API,"GET",f"/api/v1/donors/{donor_id}")
    @mcp.tool()
    async def find_nearby_donors(latitude:float,longitude:float,radius_km:float=20,blood_group:str|None=None,available:bool=True,limit:int=50)->dict[str, Any]:
        """Find available donors within a geographic radius ordered by distance. Results are candidates only and require eligibility review."""
        if not -90<=latitude<=90 or not -180<=longitude<=180 or not 0<radius_km<=500:raise ValueError("coordinates or radius_km are outside supported bounds")
        _limit(limit,0);params={"latitude":latitude,"longitude":longitude,"radius_km":radius_km,"available":available,"limit":limit}
        if blood_group:params["blood_group"]=blood_group
        return await _request(DONOR_API,"GET","/api/v1/donors/nearby",params=params)
    @mcp.tool()
    async def get_available_donors(city:str|None=None,blood_group:str|None=None,notification_consent:bool|None=None,limit:int=50,offset:int=0)->dict[str, Any]:
        """List donors marked available with optional city, group and consent filters; availability alone is not eligibility."""
        _limit(limit,offset);params={"limit":limit,"offset":offset}
        if city:params["city"]=city
        if blood_group:params["blood_group"]=blood_group
        if notification_consent is not None:params["notification_consent"]=notification_consent
        return await _request(DONOR_API,"GET","/api/v1/donors/available",params=params)
    @mcp.tool()
    async def get_donors_by_blood_group(blood_group:str,city:str|None=None,available:bool|None=True,limit:int=50,offset:int=0)->dict[str, Any]:
        """Search donors by exact ABO/Rh label with optional geography and availability filters; do not infer compatibility."""
        _limit(limit,offset);return await _request(DONOR_API,"GET","/api/v1/donors/search",params={k:v for k,v in {"blood_group":blood_group,"city":city,"available":available,"limit":limit,"offset":offset}.items() if v is not None})
    @mcp.tool()
    async def get_donor_statistics()->dict[str, Any]:
        """Return aggregate donor counts by blood group and city, verification state, availability and donation month."""
        return await _request(DONOR_API,"GET","/api/v1/donors/statistics")
    @mcp.tool()
    async def get_donation_history(donor_id:int|None=None,blood_bank_id:int|None=None,limit:int=100,offset:int=0)->dict[str, Any]:
        """Retrieve paginated donation history, optionally for one donor or blood bank."""
        _limit(limit,offset);params={"limit":limit,"offset":offset}
        if donor_id is not None:params["donor_id"]=donor_id
        if blood_bank_id is not None:params["blood_bank_id"]=blood_bank_id
        return await _request(DONOR_API,"GET","/api/v1/donation-history",params=params)
    @mcp.tool()
    async def register_donor(name:str,age:int,blood_group:str,city:str,district:str,state:str,pin_code:str,latitude:float,longitude:float,phone:str,email:str,preferred_contact_method:str="email",notification_consent:bool=False)->dict[str, Any]:
        """Register a synthetic donor record. Production registration must use consent, identity checks and clinical eligibility review."""
        body={"name":name,"age":age,"blood_group":blood_group,"city":city,"district":district,"state":state,"pin_code":pin_code,"latitude":latitude,"longitude":longitude,"phone":phone,"email":email,"preferred_contact_method":preferred_contact_method,"notification_consent":notification_consent}
        return await _request(DONOR_API,"POST","/api/v1/donors",json_body=body)
    @mcp.tool()
    async def update_donor(donor_id:int,preferred_contact_method:str|None=None,notification_consent:bool|None=None,verification_status:str|None=None,eligibility_status:str|None=None,temporary_deferral_reason:str|None=None)->dict[str, Any]:
        """Update donor contact preference, consent or staff-managed verification/eligibility fields."""
        body={k:v for k,v in {"preferred_contact_method":preferred_contact_method,"notification_consent":notification_consent,"verification_status":verification_status,"eligibility_status":eligibility_status,"temporary_deferral_reason":temporary_deferral_reason}.items() if v is not None}
        if not body:raise ValueError("At least one donor field must be provided")
        return await _request(DONOR_API,"PATCH",f"/api/v1/donors/{donor_id}",json_body=body)
    @mcp.tool()
    async def update_donor_availability(donor_id:int,available:bool)->dict[str, Any]:
        """Update a donor's self-reported operational availability; this does not alter clinical eligibility."""
        return await _request(DONOR_API,"PATCH",f"/api/v1/donors/{donor_id}/availability",json_body={"available":available})
    @mcp.tool()
    async def record_donation(donor_id:int,donation_date:str,blood_bank_id:int,donation_type:str="whole_blood",donation_status:str="completed",units_collected:int=1,next_eligible_date:str|None=None)->dict[str, Any]:
        """Record a donation event. Any next eligibility date must be supplied by the qualified clinical process."""
        body={"donation_date":donation_date,"blood_bank_id":blood_bank_id,"donation_type":donation_type,"donation_status":donation_status,"units_collected":units_collected,"next_eligible_date":next_eligible_date}
        return await _request(DONOR_API,"POST",f"/api/v1/donors/{donor_id}/donation-history",json_body=body)
    @mcp.tool()
    async def record_donor_notification(donor_id:int,channel:str,request_reference:str,status:str="attempted",response:str|None=None)->dict[str, Any]:
        """Record a donor notification attempt or response. The donor API snapshots consent and marks non-consented attempts blocked; an attempt never implies agreement to donate."""
        body={"channel":channel,"status":status,"response":response,"request_reference":request_reference}
        return await _request(DONOR_API,"POST",f"/api/v1/donors/{donor_id}/notifications",json_body=body)

    @mcp.tool()
    async def send_blood_bank_notification(blood_bank_id:int,blood_request_id:int,blood_group:str,component_type:Literal["whole_blood","packed_red_blood_cells"],required_units:int,channel:Literal["email","sms","console"],message:str,inventory_blood_group:str|None=None,idempotency_key:str|None=None)->dict[str,Any]:
        """Send an idempotent blood-bank request after checking recorded group, component and unreserved stock. A sent message does not confirm availability."""
        key=idempotency_key or f"blood-bank:{blood_request_id}:{blood_bank_id}:{component_type}:{inventory_blood_group or blood_group}:{blood_group}"
        return await _request(BANK_API,"POST","/api/v1/blood-bank-notifications",json_body={"blood_bank_id":blood_bank_id,"blood_request_id":blood_request_id,"blood_group":blood_group,"inventory_blood_group":inventory_blood_group,"component_type":component_type,"required_units":required_units,"channel":channel,"message":message,"idempotency_key":key})

    @mcp.tool()
    async def list_blood_bank_notifications(blood_request_id:int|None=None,blood_bank_id:int|None=None,limit:int=100,offset:int=0)->dict[str,Any]:
        """List persisted blood-bank notification attempts and separate delivery/response states."""
        _limit(limit,offset);return await _request(BANK_API,"GET","/api/v1/blood-bank-notifications",params={k:v for k,v in {"blood_request_id":blood_request_id,"blood_bank_id":blood_bank_id,"limit":limit,"offset":offset}.items() if v is not None})

    @mcp.tool()
    async def get_blood_bank_notification(notification_id:int)->dict[str,Any]:
        """Get a blood-bank notification's delivery status, response and confirmed units."""
        return await _request(BANK_API,"GET",f"/api/v1/blood-bank-notifications/{notification_id}")

    @mcp.tool()
    async def respond_to_blood_bank_notification(notification_id:int,response_token:str,response_status:Literal["accepted","partially_available","unavailable","rejected","pending"],confirmed_available_units:int|None=None,rejection_reason:str|None=None)->dict[str,Any]:
        """Submit an authenticated blood-bank response with an actual confirmed quantity where applicable."""
        return await _request(BANK_API,"POST",f"/api/v1/blood-bank-notifications/{notification_id}/respond",json_body={"response_status":response_status,"confirmed_available_units":confirmed_available_units,"rejection_reason":rejection_reason},params={"token":response_token})

    @mcp.tool()
    async def send_donor_notification(donor_id:int,blood_request_id:int,blood_group:str,component_type:Literal["whole_blood","packed_red_blood_cells"],channel:Literal["email","sms","console"],message:str,hospital_latitude:float,hospital_longitude:float,max_distance_km:float=500,idempotency_key:str|None=None)->dict[str,Any]:
        """Notify a consenting, available, verified and eligible donor only after component-aware group and distance checks."""
        key=idempotency_key or f"donor:{blood_request_id}:{donor_id}:{component_type}:{blood_group}"
        body={"donor_id":donor_id,"blood_request_id":blood_request_id,"blood_group":blood_group,"component_type":component_type,"channel":channel,"message":message,"hospital_latitude":hospital_latitude,"hospital_longitude":hospital_longitude,"max_distance_km":max_distance_km,"idempotency_key":key}
        return await _request(DONOR_API,"POST","/api/v1/donor-notifications/send",json_body=body)

    @mcp.tool()
    async def list_donor_notifications(donor_id:int|None=None,blood_request_id:int|None=None,delivery_status:Literal["pending","sent","delivered","failed","undelivered","simulated"]|None=None,limit:int=100,offset:int=0)->dict[str,Any]:
        """List persisted donor notification records with consent, delivery and response fields."""
        _limit(limit,offset);return await _request(DONOR_API,"GET","/api/v1/donor-notifications",params={k:v for k,v in {"donor_id":donor_id,"blood_request_id":blood_request_id,"delivery_status":delivery_status,"limit":limit,"offset":offset}.items() if v is not None})

    @mcp.tool()
    async def get_donor_notification(notification_id:int)->dict[str,Any]:
        """Get one donor notification's consent snapshot and separate delivery/response states."""
        return await _request(DONOR_API,"GET",f"/api/v1/donor-notifications/{notification_id}")

    @mcp.tool()
    async def respond_to_donor_notification(notification_id:int,response_token:str,response_status:Literal["accepted","declined","unavailable","no_response"])->dict[str,Any]:
        """Submit a donor response through the per-notification response token."""
        return await _request(DONOR_API,"POST",f"/api/v1/donor-notifications/{notification_id}/respond",json_body={"response_status":response_status},params={"token":response_token})
