"""Discover nearby blood banks / donation centres from OpenStreetMap through the Overpass API.

The synthetic data APIs know *inventory*; OpenStreetMap knows *places*. OSM results therefore carry
no stock information and are reported separately as "additional nearby facilities to call".
Failures never raise: the caller gets ``available: False`` and an error string.
"""
from __future__ import annotations

import math
import os
import threading
import time
from typing import Any

import httpx

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "BloodDonationCoordinator/1.0 (hackathon project; OSM Overpass client)"
_CACHE_TTL_SECONDS = 15 * 60
_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def osm_discovery_enabled() -> bool:
    return os.getenv("OSM_DISCOVERY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def build_query(latitude: float, longitude: float, radius_m: int) -> str:
    around = f"(around:{radius_m},{latitude:.6f},{longitude:.6f})"
    return (
        "[out:json][timeout:25];("
        f'nwr["healthcare"="blood_donation"]{around};'
        f'nwr["healthcare"="blood_bank"]{around};'
        f'nwr["amenity"="blood_bank"]{around};'
        f'nwr["amenity"="blood_donation"]{around};'
        ");out center tags 100;"
    )


def _address(tags: dict[str, str]) -> str | None:
    if tags.get("addr:full"):
        return tags["addr:full"]
    parts = [tags.get(k) for k in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city", "addr:postcode")]
    text = ", ".join(p for p in parts if p)
    return text or None


def parse_elements(elements: list[dict[str, Any]], latitude: float, longitude: float) -> list[dict[str, Any]]:
    places: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for element in elements:
        kind, osm_id = element.get("type"), element.get("id")
        if kind is None or osm_id is None or (kind, osm_id) in seen:
            continue
        seen.add((kind, osm_id))
        lat = element.get("lat", (element.get("center") or {}).get("lat"))
        lon = element.get("lon", (element.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        tags = element.get("tags") or {}
        places.append({
            "source": "openstreetmap",
            "osm_id": f"{kind}/{osm_id}",
            "osm_url": f"https://www.openstreetmap.org/{kind}/{osm_id}",
            "name": tags.get("name") or tags.get("operator") or "Unnamed blood donation facility",
            "facility_type": tags.get("healthcare") or tags.get("amenity") or "blood_bank",
            "latitude": float(lat),
            "longitude": float(lon),
            "distance_km": round(haversine_km(latitude, longitude, float(lat), float(lon)), 2),
            "address": _address(tags),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "opening_hours": tags.get("opening_hours"),
            "inventory_known": False,
        })
    places.sort(key=lambda p: p["distance_km"])
    return places


def discover_nearby_blood_banks(
    latitude: float,
    longitude: float,
    radius_km: float = 25.0,
    limit: int = 20,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Return OSM blood banks within ``radius_km`` of a point, nearest first."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return {"source": "openstreetmap", "available": False, "error": "Invalid coordinates", "places": []}
    radius_km = min(max(float(radius_km), 1.0), 100.0)
    limit = min(max(int(limit), 1), 100)
    key = (round(latitude, 3), round(longitude, 3), round(radius_km), limit)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_SECONDS:
            return {**hit[1], "cached": True}

    url = os.getenv("OVERPASS_URL", DEFAULT_OVERPASS_URL)
    timeout = float(os.getenv("OVERPASS_TIMEOUT_SECONDS", "20"))
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout, headers={"User-Agent": _USER_AGENT})
    try:
        response = http.post(url, data={"data": build_query(latitude, longitude, int(radius_km * 1000))})
        response.raise_for_status()
        elements = response.json().get("elements", [])
        places = parse_elements(elements, latitude, longitude)[:limit]
        result = {
            "source": "openstreetmap",
            "available": True,
            "radius_km": radius_km,
            "count": len(places),
            "places": places,
            "attribution": "© OpenStreetMap contributors (ODbL)",
            "note": "OpenStreetMap lists facilities, not stock. Call to confirm availability.",
        }
        with _lock:
            _cache[key] = (now, result)
        return {**result, "cached": False}
    except (httpx.HTTPError, ValueError) as exc:
        return {"source": "openstreetmap", "available": False, "error": f"Overpass request failed: {type(exc).__name__}: {exc}"[:300], "places": []}
    finally:
        if owns_client:
            http.close()


def clear_cache() -> None:
    with _lock:
        _cache.clear()
