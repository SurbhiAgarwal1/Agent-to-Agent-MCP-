"""Step 4: a blood bank / donor answer flows back to the hospital staff who asked."""
import logging
import re
from datetime import date, timedelta

import pytest

from app.models.blood_bank import BloodBank
from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.hospital_alert import HospitalAlert
from app.models.user import UserRole
from app.services import response_sync
from tests.conftest import auth_headers, make_user
from tests.test_synthetic_data_apis import bank_client, donor_client  # noqa: F401  (fixtures)


@pytest.fixture
def hospital_world(db_session):
    db_session.add_all([
        Hospital(hospital_id=1, name="City Hospital", latitude=12.97, longitude=77.59, address="x"),
        Hospital(hospital_id=2, name="Other Hospital", latitude=12.90, longitude=77.50, address="y"),
    ])
    db_session.add(BloodRequest(request_id=10, hospital_id=1, blood_group="A+", units_required=3, urgency="HIGH", status="PROCESSING"))
    db_session.commit()
    staff = make_user(db_session, "staff@city.test", UserRole.HOSPITAL_STAFF, hospital_ids=[1])
    outsider = make_user(db_session, "staff@other.test", UserRole.HOSPITAL_STAFF, hospital_ids=[2])
    return staff, outsider


def _fetched(bank_status="accepted", donor_status="accepted"):
    return {"banks": [{"id": 5, "blood_bank_id": 76, "response_status": bank_status, "confirmed_available_units": 2 if bank_status == "accepted" else None,
                       "rejection_reason": None if bank_status == "accepted" else "no stock"}],
            "donors": [{"id": 9, "donor_id": 195, "response_status": donor_status}], "errors": []}


def test_ingest_creates_one_alert_and_is_idempotent(db_session, hospital_world):
    kwargs = dict(request_id=10, source_type="BLOOD_BANK", source_id=76, notification_id=5, response_status="accepted", confirmed_units=2, source_name="Red Bank")
    alert, created = response_sync.ingest_response(db_session, **kwargs)
    again, created_again = response_sync.ingest_response(db_session, **kwargs)
    assert created and not created_again and again.alert_id == alert.alert_id
    assert alert.hospital_id == 1 and "Red Bank accepted and confirmed 2 unit(s)" in alert.message
    assert db_session.query(HospitalAlert).count() == 1


def test_pending_and_unknown_requests_create_no_alert(db_session, hospital_world):
    assert response_sync.ingest_response(db_session, request_id=10, source_type="DONOR", source_id=1, notification_id=1, response_status="pending") == (None, False)
    assert response_sync.ingest_response(db_session, request_id=999, source_type="DONOR", source_id=1, notification_id=2, response_status="accepted") == (None, False)


def test_webhook_requires_service_token(client, db_session, hospital_world, monkeypatch):
    monkeypatch.setenv("SERVICE_TO_SERVICE_TOKEN", "t" * 40)
    body = {"blood_request_id": 10, "source_type": "BLOOD_BANK", "source_id": 76, "notification_id": 5, "response_status": "accepted", "confirmed_units": 2}
    assert client.post("/api/v1/internal/response-events", json=body).status_code == 401
    assert client.post("/api/v1/internal/response-events", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.post("/api/v1/internal/response-events", json=body, headers={"Authorization": "Bearer " + "t" * 40})
    assert ok.status_code == 202 and ok.json() == {"accepted": True, "created": True}


def test_staff_see_alerts_for_their_hospital_only_and_can_mark_read(client, db_session, hospital_world, monkeypatch):
    staff, outsider = hospital_world
    monkeypatch.delenv("SERVICE_TO_SERVICE_TOKEN", raising=False)
    client.post("/api/v1/internal/response-events", json={"blood_request_id": 10, "source_type": "DONOR", "source_id": 195, "notification_id": 9, "response_status": "accepted"})
    mine = client.get("/api/v1/hospital-alerts", headers=auth_headers(staff)).json()
    assert mine["unread"] == 1 and mine["items"][0]["request_id"] == 10
    assert client.get("/api/v1/hospital-alerts", headers=auth_headers(outsider)).json() == {"unread": 0, "items": []}
    alert_id = mine["items"][0]["alert_id"]
    assert client.post(f"/api/v1/hospital-alerts/{alert_id}/read", headers=auth_headers(outsider)).status_code == 404
    assert client.post(f"/api/v1/hospital-alerts/{alert_id}/read", headers=auth_headers(staff)).json()["read"] is True
    assert client.get("/api/v1/hospital-alerts?unread_only=true", headers=auth_headers(staff)).json()["items"] == []


def test_response_summary_counts_units_and_authorizes(client, hospital_world, monkeypatch):
    staff, outsider = hospital_world
    monkeypatch.setattr(response_sync, "fetch_notifications", lambda request_id: _fetched())
    summary = client.get("/api/v1/blood-requests/10/responses", headers=auth_headers(staff)).json()
    assert summary["confirmed_units"] == 3 and summary["units_required"] == 3 and summary["is_covered"] is True
    assert summary["counts"]["accepted"] == 2 and summary["counts"]["pending"] == 0
    assert client.get("/api/v1/blood-requests/10/responses", headers=auth_headers(outsider)).status_code == 403
    assert client.get("/api/v1/blood-requests/404/responses", headers=auth_headers(staff)).status_code == 404
    # The pull created the alerts, so a missed webhook is recovered.
    assert client.get("/api/v1/hospital-alerts", headers=auth_headers(staff)).json()["unread"] == 2


def test_summary_reports_declines_and_data_api_outage(client, hospital_world, monkeypatch):
    staff, _ = hospital_world
    monkeypatch.setattr(response_sync, "fetch_notifications", lambda r: {**_fetched("rejected", "pending"), "errors": ["donor data API unavailable: ConnectError"]})
    summary = client.get("/api/v1/blood-requests/10/responses", headers=auth_headers(staff)).json()
    assert summary["is_covered"] is False and summary["confirmed_units"] == 0
    assert summary["counts"]["declined_or_unavailable"] == 1 and summary["counts"]["pending"] == 1
    assert summary["warnings"]


def test_blood_bank_can_answer_a_console_mode_notification_and_hospital_is_told(bank_client, monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "development")
    events = []
    from app.services.notification_providers import delivery
    monkeypatch.setattr(delivery, "notify_hospital_of_response", events.append)
    bank_id = bank_client.get("/api/v1/blood-banks").json()["items"][0]["id"]
    with caplog.at_level(logging.WARNING):
        sent = bank_client.post("/api/v1/blood-bank-notifications", json={
            "blood_bank_id": bank_id, "blood_request_id": 10, "blood_group": "A+", "component_type": "packed_red_blood_cells",
            "required_units": 2, "channel": "console", "message": "Need blood", "idempotency_key": "bank:10:test:1"})
    assert sent.status_code == 201 and sent.json()["delivery_status"] == "simulated"
    token = re.search(r"respond\?token=([A-Za-z0-9_%-]+)", caplog.text).group(1)
    answered = bank_client.post(f"/api/v1/blood-bank-notifications/{sent.json()['id']}/respond", params={"token": token},
                                json={"response_status": "accepted", "confirmed_available_units": 2})
    assert answered.status_code == 200, answered.text
    assert answered.json()["response_status"] == "accepted"
    assert events and events[0]["source_type"] == "BLOOD_BANK" and events[0]["blood_request_id"] == 10 and events[0]["confirmed_units"] == 2
    again = bank_client.post(f"/api/v1/blood-bank-notifications/{sent.json()['id']}/respond", params={"token": token},
                             json={"response_status": "accepted", "confirmed_available_units": 2})
    assert again.status_code == 409


def test_production_still_refuses_answers_to_undelivered_notifications(bank_client, monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "development")
    bank_id = bank_client.get("/api/v1/blood-banks").json()["items"][0]["id"]
    with caplog.at_level(logging.WARNING):
        sent = bank_client.post("/api/v1/blood-bank-notifications", json={
            "blood_bank_id": bank_id, "blood_request_id": 11, "blood_group": "A+", "component_type": "packed_red_blood_cells",
            "required_units": 1, "channel": "console", "message": "Need blood", "idempotency_key": "bank:11:test:1"})
    token = re.search(r"respond\?token=([A-Za-z0-9_%-]+)", caplog.text).group(1)
    monkeypatch.setenv("ENVIRONMENT", "production")
    refused = bank_client.post(f"/api/v1/blood-bank-notifications/{sent.json()['id']}/respond", params={"token": token},
                               json={"response_status": "accepted", "confirmed_available_units": 1})
    assert refused.status_code == 409


def test_donor_acceptance_reaches_the_hospital(donor_client, monkeypatch, caplog):
    monkeypatch.setenv("ENVIRONMENT", "development")
    events = []
    from app.services.notification_providers import delivery
    monkeypatch.setattr(delivery, "notify_hospital_of_response", events.append)
    donor_id = donor_client.get("/api/v1/donors").json()["items"][0]["id"]
    with caplog.at_level(logging.WARNING):
        sent = donor_client.post("/api/v1/donor-notifications/send", json={
            "donor_id": donor_id, "channel": "console", "blood_request_id": 10, "blood_group": "O+",
            "component_type": "packed_red_blood_cells", "message": "Please donate", "idempotency_key": "donor:10:test:1",
            "hospital_latitude": 12.9716, "hospital_longitude": 77.5946})
    assert sent.status_code == 201, sent.text
    token = re.search(r"respond\?token=([A-Za-z0-9_%-]+)", caplog.text).group(1)
    answered = donor_client.post(f"/api/v1/donor-notifications/{sent.json()['id']}/respond", params={"token": token}, json={"response_status": "accepted"})
    assert answered.status_code == 200
    assert events and events[0]["source_type"] == "DONOR" and events[0]["response_status"] == "accepted" and events[0]["confirmed_units"] == 1
