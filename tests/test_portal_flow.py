"""Step 8: donor / blood bank accounts, UI answers, and stock coming off the bank on accept."""
import httpx
import pytest

from app.models.blood_request import BloodRequest
from app.models.hospital import Hospital
from app.models.hospital_alert import HospitalAlert
from app.models.user import UserRole
from app.services import party_service
from tests.conftest import auth_headers, make_user
from tests.test_synthetic_data_apis import bank_client, donor_client  # noqa: F401  (fixtures)

BANK_URL, DONOR_URL = party_service.bank_url(), party_service.donor_url()


@pytest.fixture
def world(client, db_session, bank_client, donor_client, monkeypatch):  # noqa: F811
    monkeypatch.delenv("SERVICE_TO_SERVICE_TOKEN", raising=False)

    def fake_request(method, url, params=None, json=None, headers=None, timeout=None):
        target, base = (bank_client, BANK_URL) if url.startswith(BANK_URL) else (donor_client, DONOR_URL)
        r = target.request(method, url[len(base):], params=params, json=json, headers=headers)
        return httpx.Response(r.status_code, json=r.json(), request=httpx.Request(method, url))

    monkeypatch.setattr(party_service.httpx, "request", fake_request)
    db_session.add(Hospital(hospital_id=1, name="City Hospital", latitude=12.97, longitude=77.59, address="MG Road"))
    db_session.add(BloodRequest(request_id=10, hospital_id=1, blood_group="B+", units_required=2, urgency="HIGH", status="PROCESSING"))
    db_session.commit()
    return bank_client, donor_client


def _signup(client, **body):
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    login = client.post("/api/v1/auth/login", json={"email": body["email"], "password": body["password"]})
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


def test_blood_bank_signup_creates_listing_and_stock_decreases_on_accept(client, world, db_session):
    bank_api, _ = world
    before = bank_api.get("/api/v1/blood-banks?limit=1").json()["total"]
    h = _signup(client, email="redcross@bank.test", password="secret12", role="BLOOD_BANK_STAFF", organization_name="Red Cross Centre",
                address="1 Main", city="Bengaluru", latitude=12.95, longitude=77.6, initial_stock={"B+": 5})
    assert bank_api.get("/api/v1/blood-banks?limit=1").json()["total"] == before + 1
    inv = client.get("/api/v1/portal/bank/inventory", headers=h).json()
    assert inv["bank"]["name"] == "Red Cross Centre"
    stock = {i["blood_group"]: i["available_units"] for i in inv["items"]}
    assert stock["B+"] == 5 and stock["O-"] == 0
    bank_id = inv["bank"]["id"]

    n = bank_api.post("/api/v1/blood-bank-notifications", json={
        "blood_bank_id": bank_id, "blood_request_id": 10, "blood_group": "B+", "inventory_blood_group": "B+",
        "component_type": "packed_red_blood_cells", "required_units": 2, "channel": "console",
        "idempotency_key": "key-bank-1", "message": "Need B+"})
    assert n.status_code == 201, n.text
    incoming = client.get("/api/v1/portal/bank/notifications", headers=h).json()["items"]
    assert incoming[0]["hospital_name"] == "City Hospital" and incoming[0]["in_stock_units"] == 5

    nid = incoming[0]["id"]
    over = client.post(f"/api/v1/portal/bank/notifications/{nid}/respond", headers=h, json={"response_status": "accepted", "confirmed_available_units": 9})
    assert over.status_code == 422 and "Only 5" in over.json()["detail"]
    ok = client.post(f"/api/v1/portal/bank/notifications/{nid}/respond", headers=h, json={"response_status": "accepted", "confirmed_available_units": 2})
    assert ok.status_code == 200, ok.text
    after = {i["blood_group"]: i["available_units"] for i in client.get("/api/v1/portal/bank/inventory", headers=h).json()["items"]}
    assert after["B+"] == 3  # 5 - 2
    again = client.post(f"/api/v1/portal/bank/notifications/{nid}/respond", headers=h, json={"response_status": "accepted", "confirmed_available_units": 2})
    assert again.status_code == 409
    assert {i["blood_group"]: i["available_units"] for i in client.get("/api/v1/portal/bank/inventory", headers=h).json()["items"]}["B+"] == 3

    put = client.put("/api/v1/portal/bank/inventory/B+", headers=h, json={"available_units": 12})
    assert put.status_code == 200 and put.json()["available_units"] == 12


def test_bank_cannot_answer_another_banks_notification(client, world):
    bank_api, _ = world
    a = _signup(client, email="a@bank.test", password="secret12", role="BLOOD_BANK_STAFF", organization_name="Bank A", latitude=1, longitude=1, initial_stock={"B+": 4})
    b = _signup(client, email="b@bank.test", password="secret12", role="BLOOD_BANK_STAFF", organization_name="Bank B", latitude=1, longitude=1, initial_stock={"B+": 4})
    bank_a = client.get("/api/v1/portal/bank/inventory", headers=a).json()["bank"]["id"]
    n = bank_api.post("/api/v1/blood-bank-notifications", json={"blood_bank_id": bank_a, "blood_request_id": 10, "blood_group": "B+", "inventory_blood_group": "B+",
        "component_type": "packed_red_blood_cells", "required_units": 1, "channel": "console", "idempotency_key": "key-bank-2", "message": "Need B+"}).json()
    assert client.post(f"/api/v1/portal/bank/notifications/{n['id']}/respond", headers=b, json={"response_status": "accepted", "confirmed_available_units": 1}).status_code == 404


def test_donor_signup_adds_donor_and_accept_reaches_hospital(client, world, db_session):
    _, donor_api = world
    before = donor_api.get("/api/v1/donors?limit=1").json()["total"]
    h = _signup(client, email="asha@donor.test", password="secret12", role="USER", name="Asha Rao", age=30, blood_group="B+", city="Bengaluru", latitude=12.96, longitude=77.6)
    assert donor_api.get("/api/v1/donors?limit=1").json()["total"] == before + 1
    me = client.get("/api/v1/portal/me", headers=h).json()
    assert me["kind"] == "donor" and me["profile"]["blood_group"] == "B+"
    donor_id = me["profile"]["id"]

    n = donor_api.post("/api/v1/donor-notifications/send", json={"donor_id": donor_id, "blood_request_id": 10, "blood_group": "B+", "channel": "console",
        "message": "Need B+", "idempotency_key": "key-donor-1", "hospital_latitude": 12.97, "hospital_longitude": 77.59})
    assert n.status_code == 201, n.text
    items = client.get("/api/v1/portal/donor/notifications", headers=h).json()["items"]
    assert items[0]["hospital_name"] == "City Hospital" and items[0]["response_status"] == "pending"
    r = client.post(f"/api/v1/portal/donor/notifications/{items[0]['id']}/respond", headers=h, json={"response": "accepted"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/portal/donor/notifications", headers=h).json()["items"][0]["response_status"] == "accepted"
    assert client.post(f"/api/v1/portal/donor/notifications/{items[0]['id']}/respond", headers=h, json={"response": "declined"}).status_code == 409
    assert client.patch("/api/v1/portal/donor/availability", headers=h, json={"available": False}).json()["available"] is False


def test_signup_validation_and_data_service_outage(client, world, monkeypatch):
    assert client.post("/api/v1/auth/register", json={"email": "d@x.test", "password": "secret12", "role": "USER", "latitude": 1, "longitude": 1}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"email": "b@x.test", "password": "secret12", "role": "BLOOD_BANK_STAFF"}).status_code == 422

    def boom(*a, **k):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(party_service.httpx, "request", boom)
    r = client.post("/api/v1/auth/register", json={"email": "d@x.test", "password": "secret12", "role": "USER", "blood_group": "A+", "latitude": 1, "longitude": 1})
    assert r.status_code == 503
    # no half-made account is left behind
    assert client.post("/api/v1/auth/login", json={"email": "d@x.test", "password": "secret12"}).status_code == 401


def test_hospital_signup_creates_hospital_and_membership(client, world):
    h = _signup(client, email="new@hosp.test", password="secret12", role="HOSPITAL_STAFF", organization_name="Lakeside Hospital", address="5 Lake Rd", latitude=12.9, longitude=77.5)
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200
    assert any(x["name"] == "Lakeside Hospital" for x in client.get("/api/v1/hospitals", headers=h).json())


def test_donor_cannot_use_bank_portal(client, world):
    h = _signup(client, email="d2@donor.test", password="secret12", role="USER", blood_group="O+", latitude=1, longitude=1)
    assert client.get("/api/v1/portal/bank/inventory", headers=h).status_code == 403
