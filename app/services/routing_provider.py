"""Routing Provider Service for Real Road Network Routing and Fallback.

Part 11: Swappable routing architecture supporting:
- RealRoutingProvider: Real road-network distance & ETA (OSRM or HTTP service)
- HaversineRoutingProvider: Straight-line fallback / offline calculations
- Automatic graceful fallback if real routing API is unavailable or times out.
"""

from abc import ABC, abstractmethod
import logging
import math
import os
from typing import Any, Dict, Optional
import urllib.request
import json

logger = logging.getLogger("RoutingProvider")


class RoutingProvider(ABC):
    """Abstract interface for routing and travel distance providers."""

    @abstractmethod
    def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> Dict[str, Any]:
        """Compute route between origin and destination coordinates.
        
        Returns:
            Dictionary with distance_km, eta_minutes, and source metadata.
        """
        pass

    def route_many(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: "list[tuple[float, float]]",
    ) -> "list[Dict[str, Any]]":
        """Route from one origin to many destinations (providers with a batch API override this)."""
        return [self.route(origin_lat, origin_lon, lat, lon) for lat, lon in destinations]


class HaversineRoutingProvider(RoutingProvider):
    """Straight-line distance calculation using the Haversine formula."""

    EARTH_RADIUS_KM: float = 6371.0
    DEFAULT_URBAN_SPEED_KMH: float = 30.0

    def calculate_distance(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> float:
        """Great-circle distance in kilometers."""
        phi1 = math.radians(origin_lat)
        phi2 = math.radians(dest_lat)
        delta_phi = math.radians(dest_lat - origin_lat)
        delta_lambda = math.radians(dest_lon - origin_lon)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        )
        a = min(1.0, max(0.0, a))
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return self.EARTH_RADIUS_KM * c

    def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> Dict[str, Any]:
        """Calculate Haversine approximation route."""
        dist = self.calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        rounded_dist = round(dist, 2)
        mins = max(1, round((dist / self.DEFAULT_URBAN_SPEED_KMH) * 60)) if dist > 0 else 0
        return {
            "distance_km": rounded_dist,
            "eta_minutes": None,
            "estimated_time": f"~{mins} mins (approx straight-line)" if dist > 0 else "0 mins (approx straight-line)",
            "source": "HAVERSINE_APPROXIMATION",
        }


class RealRoutingProvider(RoutingProvider):
    """Real road-network routing provider using OSRM or custom routing service."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout_seconds: float = 3.0,
        fallback_provider: Optional[RoutingProvider] = None,
    ):
        """Initialize RealRoutingProvider.
        
        Args:
            api_url: OSRM route service endpoint URL template or base URL.
            timeout_seconds: HTTP request timeout before falling back.
            fallback_provider: Fallback provider on failure (defaults to Haversine).
        """
        self.api_url = api_url or os.getenv(
            "ROUTING_API_URL",
            "http://router.project-osrm.org/route/v1/driving",
        )
        self.timeout_seconds = timeout_seconds
        self.fallback = fallback_provider or HaversineRoutingProvider()

    def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> Dict[str, Any]:
        """Query real road-network routing API with automatic fallback."""
        try:
            # OSRM coordinate order is {lon},{lat};{lon},{lat}
            req_url = (
                f"{self.api_url.rstrip('/')}/"
                f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
                "?overview=false"
            )

            req = urllib.request.Request(
                req_url,
                headers={"User-Agent": "BloodDonationCoordinationSystem/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") == "Ok" and data.get("routes"):
                route_obj = data["routes"][0]
                distance_km = round(route_obj["distance"] / 1000.0, 2)
                eta_minutes = max(1, round(route_obj["duration"] / 60.0))
                return {
                    "distance_km": distance_km,
                    "eta_minutes": eta_minutes,
                    "estimated_time": f"{eta_minutes} mins (road routing)",
                    "source": "REAL_ROUTING",
                }
            else:
                logger.warning(
                    f"Real routing service returned non-OK response code: {data.get('code')}. Falling back to Haversine."
                )
                return self.fallback.route(origin_lat, origin_lon, dest_lat, dest_lon)

        except Exception as exc:
            logger.warning("Real routing request failed (%s); using configured fallback", type(exc).__name__)
            fallback_res = self.fallback.route(origin_lat, origin_lon, dest_lat, dest_lon)
            fallback_res["fallback_reason"] = str(exc)
            return fallback_res


class OpenRouteServiceProvider(RoutingProvider):
    """Road distance and ETA from the OpenRouteService hosted API (free key).

    ``route_many`` uses the Matrix endpoint so one request covers every candidate; the free plan
    rate-limits per request, so per-candidate Directions calls would be throttled.
    Any failure falls back to straight-line estimates and says so in ``fallback_reason``.
    """

    BASE_URL = "https://api.openrouteservice.org/v2"

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 10.0,
                 fallback_provider: Optional[RoutingProvider] = None, profile: Optional[str] = None, client: Any = None):
        self.api_key = api_key or os.getenv("ORS_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.profile = profile or os.getenv("ORS_PROFILE", "driving-car")
        self.base_url = os.getenv("ORS_BASE_URL", self.BASE_URL).rstrip("/")
        self.fallback = fallback_provider or HaversineRoutingProvider()
        self._client = client

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        headers = {"Authorization": self.api_key, "Content-Type": "application/json",
                   "User-Agent": "BloodDonationCoordinationSystem/1.0"}
        if self._client is not None:
            response = self._client.post(f"{self.base_url}{path}", json=body, headers=headers)
        else:
            response = httpx.post(f"{self.base_url}{path}", json=body, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _entry(distance_m: float, duration_s: float) -> Dict[str, Any]:
        minutes = max(1, round(duration_s / 60.0))
        return {
            "distance_km": round(distance_m / 1000.0, 2),
            "eta_minutes": minutes,
            "estimated_time": f"{minutes} mins (road routing, OpenRouteService)",
            "source": "OPENROUTESERVICE",
        }

    def _fallback_for(self, origin_lat, origin_lon, lat, lon, reason: str) -> Dict[str, Any]:
        result = self.fallback.route(origin_lat, origin_lon, lat, lon)
        result["fallback_reason"] = reason
        return result

    def route(self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> Dict[str, Any]:
        return self.route_many(origin_lat, origin_lon, [(dest_lat, dest_lon)])[0]

    def route_many(self, origin_lat: float, origin_lon: float, destinations: "list[tuple[float, float]]") -> "list[Dict[str, Any]]":
        if not destinations:
            return []
        if not self.api_key:
            return [self._fallback_for(origin_lat, origin_lon, la, lo, "ORS_API_KEY is not set") for la, lo in destinations]
        try:
            body = {
                "locations": [[origin_lon, origin_lat], *[[lo, la] for la, lo in destinations]],
                "sources": [0],
                "destinations": list(range(1, len(destinations) + 1)),
                "metrics": ["distance", "duration"],
            }
            data = self._post(f"/matrix/{self.profile}", body)
            distances, durations = data["distances"][0], data["durations"][0]
        except Exception as exc:  # network, quota (429), bad key (401/403), malformed reply
            reason = f"OpenRouteService unavailable: {type(exc).__name__}"
            logger.warning("%s; using straight-line fallback", reason)
            return [self._fallback_for(origin_lat, origin_lon, la, lo, reason) for la, lo in destinations]
        results = []
        for (la, lo), dist, dur in zip(destinations, distances, durations):
            if dist is None or dur is None:  # no road connection found for this point
                results.append(self._fallback_for(origin_lat, origin_lon, la, lo, "no road route found"))
            else:
                results.append(self._entry(dist, dur))
        return results


def get_routing_provider(provider_type: Optional[str] = None) -> RoutingProvider:
    """Factory function to instantiate routing provider based on configuration.
    
    Reads ROUTING_PROVIDER environment variable ('ors', 'real' or 'haversine').
    Defaults to HaversineRoutingProvider for safety and zero external dependencies.
    """
    configured = provider_type or os.getenv("ROUTING_PROVIDER", "haversine")
    cleaned = configured.strip().lower()

    if cleaned in ("ors", "openrouteservice"):
        if not os.getenv("ORS_API_KEY", "").strip():
            logger.warning("ROUTING_PROVIDER=ors but ORS_API_KEY is not set; using straight-line estimates")
        return OpenRouteServiceProvider()
    if cleaned in ("real", "osrm"):
        return RealRoutingProvider()
    return HaversineRoutingProvider()
