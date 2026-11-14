"""Nearby blood banks / hospitals from the Geoapify Places API (free key, OpenStreetMap-based data).

Geoapify has no dedicated blood-bank category, so one ``healthcare`` search is made and results are
classified client-side: places whose name looks like a blood bank come first, hospitals (many run an
in-house blood bank) follow, clearly labelled as such. No stock levels are available.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

PLACES_URL = os.getenv("GEOAPIFY_PLACES_URL", "https://api.geoapify.com/v2/places")
_BLOOD_NAME = re.compile(r"blood|raktkosh|rakt\s*kosh|transfusion|plasma|haemato|hematolog", re.IGNORECASE)
_USER_AGENT = "BloodDonationCoordinator/1.0 (hackathon project; Geoapify client)"


def geoapify_key() -> str:
    return os.getenv("GEOAPIFY_API_KEY", "").strip()


def _clean(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _phone(props: dict[str, Any]) -> str | None:
    contact = props.get("contact") or {}
    raw = (props.get("datasource") or {}).get("raw") or {}
    return contact.get("phone") or raw.get("phone") or raw.get("contact:phone")


def classify(props: dict[str, Any]) -> str:
    name = props.get("name") or ""
    categories = props.get("categories") or []
    if _BLOOD_NAME.search(name):
        return "blood_bank"
    if "healthcare.hospital" in categories:
        return "hospital"
    return "other_healthcare"


def parse_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    places: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        lat, lon = props.get("lat"), props.get("lon")
        if lat is None or lon is None or not props.get("name"):
            continue
        kind = classify(props)
        if kind == "other_healthcare":
            continue  # dentists, general clinics: not useful for a blood request
        place_id = props.get("place_id") or f"{lat},{lon}"
        places.append({
            "source": "geoapify",
            "place_id": place_id,
            "name": props["name"],
            "facility_type": kind,
            "latitude": float(lat),
            "longitude": float(lon),
            "distance_km": round(float(props.get("distance", 0)) / 1000.0, 2),
            "address": props.get("formatted") or props.get("address_line2"),
            "phone": _phone(props),
            "website": (props.get("contact") or {}).get("website") or props.get("website"),
            "opening_hours": props.get("opening_hours"),
            "inventory_known": False,
            "note": "Name suggests a blood bank." if kind == "blood_bank" else "Hospital: may have an in-house blood bank; call to confirm.",
        })
    # blood banks first, then by distance
    places.sort(key=lambda p: (p["facility_type"] != "blood_bank", p["distance_km"]))
    return places


def discover_nearby_blood_banks(latitude: float, longitude: float, radius_km: float = 25.0, limit: int = 20,
                                *, client: httpx.Client | None = None) -> dict[str, Any]:
    key = geoapify_key()
    if not key:
        return {"source": "geoapify", "available": False, "error": "GEOAPIFY_API_KEY is not set", "places": []}
    radius_km = min(max(float(radius_km), 1.0), 100.0)
    params = {
        "categories": "healthcare",
        "filter": f"circle:{longitude:.6f},{latitude:.6f},{int(radius_km * 1000)}",
        "bias": f"proximity:{longitude:.6f},{latitude:.6f}",
        "limit": 100,
        "apiKey": key,
    }
    timeout = float(os.getenv("GEOAPIFY_TIMEOUT_SECONDS", "10"))
    owns = client is None
    http = client or httpx.Client(timeout=timeout, headers={"User-Agent": _USER_AGENT})
    try:
        response = http.get(PLACES_URL, params=params)
        response.raise_for_status()
        places = parse_features(response.json().get("features", []))[: max(1, int(limit))]
        return {
            "source": "geoapify", "available": True, "radius_km": radius_km, "count": len(places), "places": places,
            "attribution": "Powered by Geoapify | © OpenStreetMap contributors",
            "note": "Geoapify lists facilities, not stock. Call to confirm availability.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        hint = " (check GEOAPIFY_API_KEY)" if status in (401, 403) else ""
        return {"source": "geoapify", "available": False, "places": [],
                "error": _clean(f"Geoapify request failed: {type(exc).__name__} {status or ''}{hint}", key)[:300]}
    finally:
        if owns:
            http.close()
