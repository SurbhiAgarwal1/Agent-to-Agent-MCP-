from datetime import date, datetime, timedelta, timezone
import re
import pytest

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.agents.matching_agent import MatchingAgent
from app.services.notification_providers import delivery
from blood_bank_api.database import get_db as get_bank_db
from blood_bank_api.models import Base as BankBase, BloodBank, BloodInventory
from blood_bank_api.migrations import migrate_component_inventory
from donor_api.database import get_db as get_donor_db
from donor_api.models import Base as DonorBase, Donor


def _session_factory(path):
    engine=create_engine(f"sqlite:///{path}",connect_args={"check_same_thread":False})
    factory=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
    return engine,factory


def test_component_migration_creates_both_supported_rows_without_relabeling_stock(tmp_path):
    engine,factory=_session_factory(tmp_path/"migration.db")
    BankBase.metadata.create_all(engine)
    db=factory()
    now=datetime.now(timezone.utc)
    bank=BloodBank(name="Migration Bank",registration_number="MIG-1",address="Address",city="City",district="District",state="State",pin_code="123456",latitude=1,longitude=2,contact_number="+91-00000-00001",contact_email="migration@example.invalid",operating_hours="24h",emergency_available=True,verification_status="verified",bank_type="public",last_updated=now)
    db.add(bank);db.flush()
    for group in ["A+","A-","B+","B-","AB+","AB-","O+","O-"]:
        db.add(BloodInventory(blood_bank_id=bank.id,blood_group=group,component_type="platelets",available_units=7,reserved_units=1,last_updated=now,expiry_date=now+timedelta(days=5),availability_status="available"))
    db.commit();db.close()
    result=migrate_component_inventory(engine)
    db=factory()
    rows=db.query(BloodInventory).order_by(BloodInventory.blood_group,BloodInventory.component_type).all()
    assert result["before"]==8 and result["after"]==16 and result["unsupported_rows_remaining"]==0
    assert len(rows)==16 and {row.component_type for row in rows}=={"whole_blood","packed_red_blood_cells"}
    assert all(row.available_units==0 and row.reserved_units==0 for row in rows)
    assert db.query(func.count(BloodBank.id)).scalar()==1
    db.close();engine.dispose()


def test_matching_requires_exact_component_and_returns_quantities():
    inventory=[
        {"bank_id":4,"blood_group":"A+","component_type":"whole_blood","units_available":6,"available_units":8,"reserved_units":2,"expiry_date":(date.today()+timedelta(days=5)).isoformat()},
        {"bank_id":4,"blood_group":"A+","component_type":"packed_red_blood_cells","units_available":3,"available_units":5,"reserved_units":2,"expiry_date":(date.today()+timedelta(days=5)).isoformat()},
    ]
    prbc=MatchingAgent().find_matches({"request_id":2,"blood_group":"A+","component_type":"packed_red_blood_cells"},inventories=inventory,donors=[])
    whole=MatchingAgent().find_matches({"request_id":3,"blood_group":"A+","component_type":"whole_blood"},inventories=inventory,donors=[])
    assert len(prbc["matches"])==len(whole["matches"])==1
    assert prbc["matches"][0]["component_type"]=="packed_red_blood_cells"
    assert prbc["matches"][0]["available_units"]==5 and prbc["matches"][0]["reserved_units"]==2
    assert whole["matches"][0]["component_type"]=="whole_blood"
    assert all(row["component_type"]!="platelets" and row["component_type"]!="plasma" for row in prbc["matches"]+whole["matches"])


def test_inventory_patch_rejects_reserved_above_available():
    from blood_bank_api.schemas import InventoryPatch
    try:
        InventoryPatch(available_units=2,reserved_units=3,component_type="whole_blood")
    except ValueError as exc:
        assert "reserved_units" in str(exc)
    else:
        raise AssertionError("invalid reserved quantity was accepted")


def test_smtp_delivery_uses_mock_provider_without_credentials(monkeypatch):
    calls=[]
    class MockSMTP:
        def __init__(self,*args,**kwargs): calls.append(("connect",args,kwargs))
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def starttls(self): calls.append(("starttls",))
        def send_message(self,message): calls.append(("send",message["To"],message["Subject"]))
    monkeypatch.setenv("SMTP_HOST","smtp.test.invalid")
    monkeypatch.setenv("SMTP_FROM","noreply@test.invalid")
    monkeypatch.delenv("SMTP_USER",raising=False);monkeypatch.delenv("SMTP_PASSWORD",raising=False)
    monkeypatch.setattr(delivery.smtplib,"SMTP",MockSMTP)
    result=delivery.deliver_notification("email","recipient@example.test","+15551234567","Test","Message")
    assert result.status=="sent" and any(call[0]=="send" for call in calls)


def test_twilio_delivery_uses_mock_http_provider_without_credentials(monkeypatch):
    calls=[]
    class MockResponse:
        status_code=201
        is_error=False
        def json(self): return {"sid":"SM-test"}
    class MockClient:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def post(self,url,**kwargs): calls.append((url,kwargs));return MockResponse()
    monkeypatch.setenv("TWILIO_ACCOUNT_SID","AC-test")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN","auth-test")
    monkeypatch.setenv("TWILIO_FROM_NUMBER","+15550000000")
    monkeypatch.setattr(delivery.httpx,"Client",MockClient)
    result=delivery.deliver_notification("sms","user@example.test","+15551234567","Test","Message")
    assert result.status=="sent" and result.provider_reference=="SM-test"
    assert calls[0][1]["data"]["To"]=="+15551234567"


def test_blood_bank_notification_is_idempotent_and_requires_response_token(tmp_path,monkeypatch):
    from blood_bank_api import main as bank_api
    from blood_bank_api.schemas import BankNotificationCreate
    engine,factory=_session_factory(tmp_path/"bank.db");BankBase.metadata.create_all(engine)
    db=factory();now=datetime.now(timezone.utc)
    bank=BloodBank(name="Bank",registration_number="BB-1",address="A",city="C",district="D",state="S",pin_code="123456",latitude=1,longitude=2,contact_number="+91-00000-00001",contact_email="bank@example.invalid",operating_hours="24h",emergency_available=True,verification_status="verified",bank_type="public",last_updated=now)
    db.add(bank);db.flush()
    db.add(BloodInventory(blood_bank_id=bank.id,blood_group="A+",component_type="packed_red_blood_cells",available_units=5,reserved_units=1,last_updated=now,expiry_date=now+timedelta(days=30),availability_status="available"));db.commit()
    sent=[]
    def fake_delivery(channel,email,phone,subject,body,**kwargs):
        sent.append(body)
        return delivery.DeliveryOutcome("sent",datetime.now(timezone.utc))
    monkeypatch.setattr(delivery,"deliver_notification",fake_delivery)
    data=BankNotificationCreate(blood_bank_id=bank.id,blood_request_id=7,blood_group="A+",inventory_blood_group="A+",component_type="packed_red_blood_cells",required_units=2,channel="email",message="Request",idempotency_key="request-7-bank-1")
    first=bank_api.send_blood_bank_notification(data,db)
    second=bank_api.send_blood_bank_notification(data,db)
    assert first["delivery_status"]=="sent" and second==first and first["response_status"]=="pending"
    assert len(sent)==1
    notification=db.query(bank_api.BloodBankNotification).filter_by(idempotency_key=data.idempotency_key).one()
    token=re.search(r"token=([^\s]+)",sent[0]).group(1)
    assert token != notification.response_token_hash
    assert not delivery.response_token_expired(notification.response_token_expires_at)
    monkeypatch.setenv("NOTIFICATION_WEBHOOK_TOKEN","test-webhook-secret")
    delivered=bank_api.update_blood_bank_delivery(notification.id,"delivered",None,"test-webhook-secret",db)
    assert delivered["delivery_status"]=="delivered" and delivered["response_status"]=="pending"
    accepted=bank_api._record_bank_response(notification,token,bank_api.BankNotificationResponseInput(response_status="accepted",confirmed_available_units=2),db)
    assert accepted["delivery_status"]=="delivered" and accepted["response_status"]=="accepted"
    assert notification.response_token_hash is None and notification.response_token_expires_at is None
    with pytest.raises(HTTPException) as reused:
        bank_api._record_bank_response(notification,token,bank_api.BankNotificationResponseInput(response_status="accepted",confirmed_available_units=2),db)
    assert reused.value.status_code==409

    rejected_data=data.model_copy(update={"idempotency_key":"request-7-bank-reject"})
    rejected=bank_api.send_blood_bank_notification(rejected_data,db)
    reject_row=db.query(bank_api.BloodBankNotification).filter_by(idempotency_key=rejected_data.idempotency_key).one()
    reject_token=re.search(r"token=([^\s]+)",sent[1]).group(1)
    bank_api._record_bank_response(reject_row,reject_token,bank_api.BankNotificationResponseInput(response_status="rejected",rejection_reason="Stock no longer available"),db)
    assert reject_row.response_status=="rejected" and reject_row.response_token_hash is None

    expired_data=data.model_copy(update={"idempotency_key":"request-7-bank-expired"})
    bank_api.send_blood_bank_notification(expired_data,db)
    expired_row=db.query(bank_api.BloodBankNotification).filter_by(idempotency_key=expired_data.idempotency_key).one()
    expired_token=re.search(r"token=([^\s]+)",sent[2]).group(1)
    expired_row.response_token_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    with pytest.raises(HTTPException) as expired:
        bank_api._record_bank_response(expired_row,expired_token,bank_api.BankNotificationResponseInput(response_status="rejected",rejection_reason="expired"),db)
    assert expired.value.status_code==410
    with pytest.raises(HTTPException) as invalid:
        bank_api._record_bank_response(expired_row,"wrong-token",bank_api.BankNotificationResponseInput(response_status="rejected",rejection_reason="invalid"),db)
    assert invalid.value.status_code==403
    db.close();db=factory()
    persisted=db.query(bank_api.BloodBankNotification).filter_by(id=notification.id).one()
    assert persisted.delivery_status=="delivered" and persisted.response_status=="accepted" and persisted.response_token_hash is None
    db.close();engine.dispose()


def test_donor_notification_full_lifecycle_and_consent(tmp_path,monkeypatch):
    from donor_api import main as donor_api
    from donor_api.schemas import NotificationCreate
    engine,factory=_session_factory(tmp_path/"donor.db");DonorBase.metadata.create_all(engine)
    db=factory();now=datetime.now(timezone.utc)
    donor=Donor(name="Test Donor",age=30,blood_group="A+",city="City",district="District",state="State",pin_code="123456",latitude=1,longitude=2,phone="+91-12345-12345",email="person@example.invalid",registration_date=date.today(),donation_count=0,available=True,preferred_contact_method="email",notification_consent=True,verification_status="verified",eligibility_status="eligible",last_updated=now)
    db.add(donor);db.commit();db.refresh(donor)
    sent=[]
    monkeypatch.setattr(delivery,"deliver_notification",lambda channel,email,phone,subject,body,**kw:(sent.append(body) or delivery.DeliveryOutcome("sent",now)))
    data=NotificationCreate(donor_id=donor.id,blood_request_id=5,blood_group="A+",component_type="packed_red_blood_cells",channel="email",message="Help",hospital_latitude=1,hospital_longitude=2,idempotency_key="donor-request-5")
    result=donor_api.send_donor_notification(data,db)
    duplicate=donor_api.send_donor_notification(data,db)
    notification=db.query(donor_api.DonorNotification).filter_by(idempotency_key=data.idempotency_key).one()
    token=re.search(r"token=([^\s]+)",sent[0]).group(1)
    assert result["delivery_status"]=="sent" and result["response_status"]=="pending" and duplicate==result
    assert len(sent)==1 and token != notification.response_token_hash
    assert not delivery.response_token_expired(notification.response_token_expires_at)
    monkeypatch.setenv("NOTIFICATION_WEBHOOK_TOKEN","test-webhook-secret")
    delivered=donor_api.update_donor_delivery(notification.id,"delivered",None,"test-webhook-secret",db)
    assert delivered["delivery_status"]=="delivered" and delivered["response_status"]=="pending"
    accepted=donor_api._record_donor_response(notification,token,"accepted",db)
    assert accepted["delivery_status"]=="delivered" and accepted["response_status"]=="accepted"
    assert notification.response_token_hash is None and notification.response_token_expires_at is None
    with pytest.raises(HTTPException) as reused:
        donor_api._record_donor_response(notification,token,"declined",db)
    assert reused.value.status_code==409

    rejected_data=data.model_copy(update={"idempotency_key":"donor-request-5-rejected"})
    donor_api.send_donor_notification(rejected_data,db)
    rejected_row=db.query(donor_api.DonorNotification).filter_by(idempotency_key=rejected_data.idempotency_key).one()
    reject_token=re.search(r"token=([^\s]+)",sent[1]).group(1)
    donor_api._record_donor_response(rejected_row,reject_token,"declined",db)
    assert rejected_row.response_status=="declined" and rejected_row.response_token_hash is None

    expired_data=data.model_copy(update={"idempotency_key":"donor-request-5-expired"})
    donor_api.send_donor_notification(expired_data,db)
    expired_row=db.query(donor_api.DonorNotification).filter_by(idempotency_key=expired_data.idempotency_key).one()
    expired_token=re.search(r"token=([^\s]+)",sent[2]).group(1)
    expired_row.response_token_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    with pytest.raises(HTTPException) as expired:
        donor_api._record_donor_response(expired_row,expired_token,"accepted",db)
    assert expired.value.status_code==410
    with pytest.raises(HTTPException) as invalid:
        donor_api._record_donor_response(expired_row,"wrong-token","accepted",db)
    assert invalid.value.status_code==403

    donor.notification_consent=False;db.commit()
    blocked_data=data.model_copy(update={"idempotency_key":"donor-request-5-no-consent"})
    blocked=donor_api.send_donor_notification(blocked_data,db)
    assert blocked["consent_at_attempt"] is False and blocked["delivery_status"]=="failed"
    assert len(sent)==3
    db.close();db=factory()
    persisted=db.query(donor_api.DonorNotification).filter_by(id=notification.id).one()
    assert persisted.delivery_status=="delivered" and persisted.response_status=="accepted" and persisted.response_token_hash is None
    db.close();engine.dispose()
