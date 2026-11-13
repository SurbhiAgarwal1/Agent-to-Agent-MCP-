from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from blood_bank_api.database import Base as BankBase, get_db as get_bank_db
from blood_bank_api.main import app as bank_app
from blood_bank_api.models import BloodBank, BloodInventory, Hospital
from donor_api.database import Base as DonorBase, get_db as get_donor_db
from donor_api.main import app as donor_app
from donor_api.models import Donor, DonationHistory


@pytest.fixture
def bank_client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    BankBase.metadata.create_all(engine);factory=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
    def override():
        db=factory()
        try:yield db
        finally:db.close()
    bank_app.dependency_overrides[get_bank_db]=override
    db=factory();now=datetime.now(timezone.utc)
    bank=BloodBank(name="Fictional Bengaluru Bank",registration_number="TEST-BB-1",address="1 Civic Road",city="Bengaluru",district="Bengaluru Urban",state="Karnataka",pin_code="560001",latitude=12.9716,longitude=77.5946,contact_number="+91-00000-00001",contact_email="bank@test.invalid",operating_hours="24 hours",emergency_available=True,verification_status="verified",bank_type="government",last_updated=now)
    hospital=Hospital(name="Fictional Hospital",hospital_type="public",address="2 Clinic Road",city="Bengaluru",district="Bengaluru Urban",state="Karnataka",pin_code="560002",latitude=12.97,longitude=77.59,emergency_contact="+91-00000-00002",contact_email="hospital@test.invalid",associated_blood_bank_ids="[]",operating_status="operational")
    db.add_all([bank,hospital]);db.flush()
    for group in ("A+","A-","B+","B-","AB+","AB-","O+","O-"):
        db.add(BloodInventory(blood_bank_id=bank.id,blood_group=group,component_type="packed_red_blood_cells",available_units=6,reserved_units=1,last_updated=now,expiry_date=now+timedelta(days=20),availability_status="available"))
    db.commit();db.close()
    with TestClient(bank_app) as client:yield client
    bank_app.dependency_overrides.clear();engine.dispose()


@pytest.fixture
def donor_client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    DonorBase.metadata.create_all(engine);factory=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
    def override():
        db=factory()
        try:yield db
        finally:db.close()
    donor_app.dependency_overrides[get_donor_db]=override
    db=factory();today=date.today()
    donor=Donor(name="Fictional Donor 001",age=30,gender="female",blood_group="O+",city="Bengaluru",district="Bengaluru Urban",state="Karnataka",pin_code="560001",latitude=12.9716,longitude=77.5946,phone="+91-00000-00001",email="donor-1@example.invalid",registration_date=today-timedelta(days=500),last_donation_date=today-timedelta(days=120),donation_count=1,available=True,preferred_contact_method="email",notification_consent=True,verification_status="verified",eligibility_status="eligible",temporary_deferral_reason=None,last_updated=datetime.now(timezone.utc))
    db.add(donor);db.flush();db.add(DonationHistory(donor_id=donor.id,donation_date=donor.last_donation_date,blood_bank_id=1,donation_type="whole_blood",donation_status="completed",units_collected=1,next_eligible_date=None));db.commit();db.close()
    with TestClient(donor_app) as client:yield client
    donor_app.dependency_overrides.clear();engine.dispose()


def test_blood_bank_search_nearby_inventory_and_summary(bank_client):
    c=bank_client
    assert c.get("/health").json()["status"]=="healthy"
    assert c.get("/api/v1/blood-banks",params={"city":"Bengaluru"}).json()["total"]==1
    nearby=c.get("/api/v1/blood-banks/nearby",params={"latitude":12.9716,"longitude":77.5946,"radius_km":2}).json()
    assert nearby["items"][0]["distance_km"]==0
    assert len(c.get("/api/v1/blood-banks/1/inventory").json()["items"])==8
    assert c.get("/api/v1/blood-inventory/search",params={"blood_group":"O+","minimum_available_units":3}).json()["total"]==1
    assert "O+" in c.get("/api/v1/blood-inventory/available-groups").json()["blood_groups"]
    assert c.get("/api/v1/blood-inventory/summary").json()["total_blood_banks"]==1
    assert c.get("/api/v1/blood-banks/999").status_code==404


def test_blood_requests_and_hospital_routes(bank_client):
    c=bank_client
    assert c.get("/api/v1/hospitals/1").json()["city"]=="Bengaluru"
    created=c.post("/api/v1/blood-requests",json={"hospital_id":1,"required_blood_group":"O+","required_units":2,"priority":"emergency"})
    assert created.status_code==201
    request_id=created.json()["id"]
    assert c.get(f"/api/v1/blood-requests/{request_id}").json()["required_units"]==2
    assert c.patch(f"/api/v1/blood-requests/{request_id}",json={"status":"processing","notes":"Synthetic update"}).json()["status"]=="processing"
    assert c.get("/api/v1/blood-requests",params={"status":"processing"}).json()["total"]==1
    assert c.patch("/api/v1/blood-banks/1/inventory/O+",json={"available_units":9,"reserved_units":2}).json()["available_units"]==9
    assert c.post("/api/v1/blood-requests",json={"hospital_id":999,"required_blood_group":"O+","required_units":1}).status_code==404


def test_donor_search_nearby_history_and_statistics(donor_client):
    c=donor_client
    assert c.get("/health").json()["api"]=="donor"
    assert c.get("/api/v1/donors/search",params={"blood_group":"O+","city":"Bengaluru"}).json()["total"]==1
    assert c.get("/api/v1/donors/available").json()["total"]==1
    assert c.get("/api/v1/donors/nearby",params={"latitude":12.9716,"longitude":77.5946,"radius_km":1}).json()["items"][0]["distance_km"]==0
    assert len(c.get("/api/v1/donors/1/donation-history").json()["items"])==1
    assert c.get("/api/v1/donation-history").json()["total"]==1
    assert c.get("/api/v1/donors/statistics").json()["total_donors"]==1


def test_donor_registration_updates_and_notification_audit(donor_client):
    c=donor_client
    body={"name":"Fictional New Donor","age":25,"blood_group":"A-","city":"Mysuru","district":"Mysuru","state":"Karnataka","pin_code":"570001","latitude":12.30,"longitude":76.64,"phone":"+91-00000-12345","email":"new-donor@example.invalid","notification_consent":True}
    created=c.post("/api/v1/donors",json=body);assert created.status_code==201
    donor_id=created.json()["id"]
    assert created.json()["eligibility_status"]=="pending_verification"
    assert c.patch(f"/api/v1/donors/{donor_id}/availability",json={"available":False}).json()["available"] is False
    assert c.patch(f"/api/v1/donors/{donor_id}",json={"eligibility_status":"eligible","verification_status":"verified"}).status_code==200
    donation=c.post(f"/api/v1/donors/{donor_id}/donation-history",json={"donation_date":date.today().isoformat(),"blood_bank_id":1})
    assert donation.status_code==201
    assert c.get(f"/api/v1/donors/{donor_id}").json()["donation_count"]==1
    notification=c.post(f"/api/v1/donors/{donor_id}/notifications",json={"channel":"email","status":"delivered"})
    assert notification.status_code==201 and notification.json()["consent_at_attempt"] is True
    history=c.get(f"/api/v1/donors/{donor_id}/notifications")
    assert history.status_code==200 and history.json()["total"]==1
    no_consent={**body,"email":"no-consent@example.invalid","notification_consent":False}
    blocked=c.post("/api/v1/donors",json=no_consent);blocked_id=blocked.json()["id"]
    blocked_log=c.post(f"/api/v1/donors/{blocked_id}/notifications",json={"channel":"sms","status":"attempted"})
    assert blocked_log.json()["status"]=="blocked_no_consent"
    assert blocked_log.json()["consent_at_attempt"] is False
    assert c.get("/api/v1/donors/999").status_code==404


def test_official_mcp_server_discovers_all_data_tools():
    from app.mcp.protocol_server import mcp
    tools={tool.name:tool for tool in mcp._tool_manager.list_tools()}
    required={"list_blood_banks","get_blood_bank_details","search_blood_banks","find_nearby_blood_banks","get_blood_bank_inventory","search_blood_inventory","get_available_blood_groups","get_inventory_statistics","list_hospitals","get_hospital_details","create_blood_request","get_blood_request","update_blood_request","update_blood_inventory","search_donors","get_donor_details","find_nearby_donors","get_available_donors","get_donors_by_blood_group","get_donor_statistics","get_donation_history","register_donor","update_donor","update_donor_availability","record_donation"}
    assert required <= set(tools)
    assert "record_donor_notification" in tools
    blood_group_schema=tools["search_blood_inventory"].parameters["properties"]["blood_group"]
    assert blood_group_schema["anyOf"][0]["type"]=="string"
    assert "clinical" in tools["search_donors"].description.lower()
