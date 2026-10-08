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
            logger.warning(
                f"Real routing service request failed ({exc}). Falling back to Haversine."
            )
            fallback_res = self.fallback.route(origin_lat, origin_lon, dest_lat, dest_lon)
            fallback_res["fallback_reason"] = str(exc)
            return fallback_res


def get_routing_provider(provider_type: Optional[str] = None) -> RoutingProvider:
    """Factory function to instantiate routing provider based on configuration.
    
    Reads ROUTING_PROVIDER environment variable ('real' or 'haversine').
    Defaults to HaversineRoutingProvider for safety and zero external dependencies.
    """
    configured = provider_type or os.getenv("ROUTING_PROVIDER", "haversine")
    cleaned = configured.strip().lower()

    if cleaned in ("real", "osrm"):
        return RealRoutingProvider()
    return HaversineRoutingProvider()
