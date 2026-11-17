"""Create and talk to the donor / blood bank records that back portal accounts."""
import os
import secrets
from typing import Any

import httpx
from fastapi import HTTPException

from app.security.service_auth import service_auth_headers

GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}


def bank_url() -> str:
    return os.getenv("BLOOD_BANK_API_URL", "http://127.0.0.1:8105").rstrip("/")


def donor_url() -> str:
    return os.getenv("DONOR_API_URL", "http://127.0.0.1:8106").rstrip("/")


def call(method: str, url: str, *, params: dict | None = None, json: Any = None) -> Any:
    """One call to a data service. Its own error messages are passed through; an outage becomes 503."""
    try:
        response = httpx.request(method, url, params=params, json=json, headers=service_auth_headers(),
                                 timeout=float(os.getenv("DATA_API_TIMEOUT_SECONDS", "8")))
    except httpx.HTTPError as exc:
        raise HTTPException(503, "The blood bank / donor data service is not reachable right now. Try again shortly.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, list):
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        raise HTTPException(response.status_code if response.status_code in (404, 409, 422) else 502, detail or "Data service error.")
    return response.json()


def create_donor(*, name: str, age: int, blood_group: str, city: str, district: str, state: str, pin_code: str,
                 latitude: float, longitude: float) -> int:
    """Adds one donor to the donor service. Its contact fields only accept fictional values, so placeholders are used;
    the real email stays on the login account and the donor is reached inside the app."""
    body = {"name": name, "age": age, "blood_group": blood_group, "city": city, "district": district, "state": state,
            "pin_code": pin_code, "latitude": latitude, "longitude": longitude,
            "phone": f"+91-00000-{secrets.randbelow(100000):05d}", "email": f"app-{secrets.token_hex(6)}@example.invalid",
            "preferred_contact_method": "email", "notification_consent": True}
    donor_id = int(call("POST", donor_url() + "/api/v1/donors", json=body)["id"])
    # The donor service starts everyone as "pending verification", and pending donors are never notified.
    # For this demo a signed-up donor is treated as verified and eligible (a real deployment would screen first).
    call("PATCH", f"{donor_url()}/api/v1/donors/{donor_id}", json={"verification_status": "verified", "eligibility_status": "eligible"})
    return donor_id


def create_bank(*, name: str, address: str, city: str, district: str, state: str, pin_code: str, latitude: float,
                longitude: float, contact_number: str | None, contact_email: str, initial_stock: dict[str, int]) -> int:
    body = {"name": name, "address": address, "city": city, "district": district, "state": state, "pin_code": pin_code,
            "latitude": latitude, "longitude": longitude, "contact_email": contact_email, "initial_stock": initial_stock}
    if contact_number:
        body["contact_number"] = contact_number
    return int(call("POST", bank_url() + "/api/v1/blood-banks", json=body)["id"])


def find_bank_by_name(name: str) -> int | None:
    """Id of the listed blood bank with exactly this name (case-insensitive), if any."""
    items = call("GET", bank_url() + "/api/v1/blood-banks", params={"name": name.strip(), "limit": 1}).get("items") or []
    return int(items[0]["id"]) if items else None


def find_donor_by_name(name: str) -> int | None:
    """Id of the listed donor with exactly this name (case-insensitive), if any."""
    items = call("GET", donor_url() + "/api/v1/donors", params={"name": name.strip(), "limit": 1}).get("items") or []
    return int(items[0]["id"]) if items else None
