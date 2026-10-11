"""Location Agent for Blood Donation Matching System.

Responsible for calculating geographic straight-line distances and approximate
transit times between hospitals, blood banks, and donors using a pluggable routing provider.

Architecture & Future Extensibility:
- All routing logic lives in `app.services.routing_provider` (single source of truth).
- Defaults to the provider selected by `get_routing_provider()` (Haversine unless
  ROUTING_PROVIDER=real/osrm is configured).
- Inject any `RoutingProvider` (OSRM, OpenRouteService, ...) via `routing_provider=`
  without modifying the Location Agent's callers or downstream agents.
"""

from typing import Any, Dict, Optional, Union


# -----------------------------------------------------------------------------
# Location Agent
# -----------------------------------------------------------------------------

class LocationAgent:
    """Agent responsible for spatial calculations and location verification.
    
    Accepts geographic coordinates and calculates straight-line distances.
    Supports dependency injection for alternative routing backends.
    """

    def __init__(
        self,
        routing_provider: Optional[Any] = None,
        bus: Optional[Any] = None,
    ):
        """Initialize the Location Agent.

        Args:
            routing_provider: Optional RoutingProvider (see app.services.routing_provider).
                Defaults to get_routing_provider().
            bus: Optional MessageBus instance for A2A communication.
        """
        if routing_provider is None:
            from app.services.routing_provider import get_routing_provider
            routing_provider = get_routing_provider()
        self.routing_provider = routing_provider
        self.bus = bus

    def handle_a2a_message(self, message: Any) -> Any:
        """Handle incoming A2A message for distance and transit time calculations.
        
        Validates message schema, extracts hospital coordinates and candidate sources,
        and annotates each candidate with straight-line distance and ETA.
        """
        from app.agents.a2a.message import A2AMessage, A2AMessageType

        if not hasattr(message, "payload") or not isinstance(message.payload, dict):
            return message.create_error(
                sender_agent="LocationAgent",
                error_message="Malformed message: payload must be a dictionary.",
            )

        if getattr(message, "message_type", None) != A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST:
            return message.create_error(
                sender_agent="LocationAgent",
                error_message=f"Unsupported message_type '{getattr(message, 'message_type', None)}'. Expected '{A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST}'.",
            )

        hospital_coords = message.payload.get("hospital_coords")
        if not hospital_coords or not isinstance(hospital_coords, dict):
            return message.create_error(
                sender_agent="LocationAgent",
                error_message="Missing or invalid 'hospital_coords' in payload.",
            )

        try:
            hosp_lat = float(hospital_coords["latitude"])
            hosp_lon = float(hospital_coords["longitude"])
            self.validate_coordinates(hosp_lat, hosp_lon, label="Hospital")
        except (KeyError, ValueError, TypeError) as err:
            return message.create_error(
                sender_agent="LocationAgent",
                error_message=f"Invalid hospital coordinates: {err}",
            )

        candidates = message.payload.get("candidates", [])
        annotated_candidates = []

        for cand in candidates:
            item = dict(cand)
            dest_lat = cand.get("latitude")
            dest_lon = cand.get("longitude")

            if dest_lat is not None and dest_lon is not None:
                try:
                    d_lat = float(dest_lat)
                    d_lon = float(dest_lon)
                    self.validate_coordinates(d_lat, d_lon, label=f"Candidate {cand.get('source_id')}")
                    loc_info = self.calculate_distance(
                        origin_lat=hosp_lat,
                        origin_lon=hosp_lon,
                        dest_lat=d_lat,
                        dest_lon=d_lon,
                        include_eta=True,
                    )
                    item["distance_km"] = loc_info["distance_km"]
                    item["estimated_time"] = loc_info["estimated_time"]
                except Exception as ex:
                    item["distance_km"] = None
                    item["estimated_time"] = None
                    item["location_error"] = str(ex)
            else:
                item["distance_km"] = None
                item["estimated_time"] = None

            annotated_candidates.append(item)

        # Sort annotated candidates by distance
        annotated_candidates.sort(
            key=lambda x: (x["distance_km"] is None, x["distance_km"] or float("inf"))
        )

        return message.create_response(
            sender_agent="LocationAgent",
            message_type=A2AMessageType.LOCATION_DISTANCES_CALCULATED_EVENT,
            payload={
                "hospital_id": message.payload.get("hospital_id"),
                "hospital_coords": hospital_coords,
                "requirement": message.payload.get("requirement"),
                "candidates_count": len(annotated_candidates),
                "candidates": annotated_candidates,
            },
        )

    @staticmethod
    def validate_coordinates(lat: float, lon: float, label: str = "Coordinate") -> None:
        """Validate that latitude and longitude are valid numeric geographic values.
        
        Args:
            lat: Latitude value to check
            lon: Longitude value to check
            label: Descriptive label for error messages (e.g. 'Origin', 'Destination')
            
        Raises:
            ValueError: If coordinate values are non-numeric or outside geographic bounds.
        """
        if not isinstance(lat, (int, float)) or isinstance(lat, bool):
            raise ValueError(f"{label} latitude must be a valid number, got {lat!r}.")
        if not isinstance(lon, (int, float)) or isinstance(lon, bool):
            raise ValueError(f"{label} longitude must be a valid number, got {lon!r}.")

        if not (-90.0 <= lat <= 90.0):
            raise ValueError(
                f"{label} latitude must be between -90.0 and 90.0 degrees, got {lat}."
            )
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(
                f"{label} longitude must be between -180.0 and 180.0 degrees, got {lon}."
            )

    def calculate_distance(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        include_eta: bool = False,
    ) -> Dict[str, Any]:
        """Calculate straight-line geographic distance between two coordinate pairs.
        
        Args:
            origin_lat: Latitude of origin (e.g. hospital)
            origin_lon: Longitude of origin
            dest_lat: Latitude of destination (e.g. blood bank or donor)
            dest_lon: Longitude of destination
            include_eta: If True, includes approximate travel time in response
            
        Returns:
            Dictionary with distance_km (rounded to 2 decimal places), and optional ETA:
            {
                "distance_km": 5.42
            }
            or with include_eta=True:
            {
                "distance_km": 5.42,
                "estimated_time": "~11 mins (approx straight-line)"
            }
            
        Raises:
            ValueError: If coordinates are invalid or out of range.
        """
        # 1. Validate inputs
        self.validate_coordinates(origin_lat, origin_lon, label="Origin")
        self.validate_coordinates(dest_lat, dest_lon, label="Destination")

        # 2. Route via RoutingProvider
        route_info = self.routing_provider.route(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
        )
        if include_eta:
            return route_info
        return {"distance_km": route_info["distance_km"]}

    def get_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> Dict[str, Any]:
        """Compute full route with ETA and provider source metadata (Part 11)."""
        self.validate_coordinates(origin_lat, origin_lon, label="Origin")
        self.validate_coordinates(dest_lat, dest_lon, label="Destination")
        return self.routing_provider.route(origin_lat, origin_lon, dest_lat, dest_lon)

    def process(
        self,
        request_data: Dict[str, Any],
        include_eta: bool = False,
    ) -> Dict[str, Any]:
        """Process a structured dictionary containing origin and destination coordinates.
        
        Supports standard keys:
            - 'origin_latitude' or 'origin_lat'
            - 'origin_longitude' or 'origin_lon'
            - 'destination_latitude', 'dest_lat', or 'destination_lat'
            - 'destination_longitude', 'dest_lon', or 'destination_lon'
        """
        origin_lat = request_data.get("origin_latitude", request_data.get("origin_lat"))
        origin_lon = request_data.get("origin_longitude", request_data.get("origin_lon"))
        dest_lat = request_data.get("destination_latitude", request_data.get("dest_lat", request_data.get("destination_lat")))
        dest_lon = request_data.get("destination_longitude", request_data.get("dest_lon", request_data.get("destination_lon")))

        if None in (origin_lat, origin_lon, dest_lat, dest_lon):
            missing = [
                k for k, v in [
                    ("origin_latitude", origin_lat),
                    ("origin_longitude", origin_lon),
                    ("destination_latitude", dest_lat),
                    ("destination_longitude", dest_lon),
                ] if v is None
            ]
            raise ValueError(f"Missing required coordinate fields: {', '.join(missing)}")

        return self.calculate_distance(
            origin_lat=float(origin_lat),
            origin_lon=float(origin_lon),
            dest_lat=float(dest_lat),
            dest_lon=float(dest_lon),
            include_eta=include_eta,
        )

    def distance_between_entities(
        self,
        origin_entity: Any,
        destination_entity: Any,
        include_eta: bool = False,
    ) -> Dict[str, Any]:
        """Calculate distance between two entities (models or dicts) with latitude/longitude.
        
        Convenient helper for finding distances between Hospital, BloodBank, or Donor.
        """
        origin_lat = self._extract_attr(origin_entity, "latitude")
        origin_lon = self._extract_attr(origin_entity, "longitude")
        dest_lat = self._extract_attr(destination_entity, "latitude")
        dest_lon = self._extract_attr(destination_entity, "longitude")

        return self.calculate_distance(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            include_eta=include_eta,
        )

    @staticmethod
    def _extract_attr(entity: Any, attr_name: str) -> float:
        """Extract coordinate attribute from an object or dictionary."""
        if isinstance(entity, dict):
            val = entity.get(attr_name)
        else:
            val = getattr(entity, attr_name, None)

        if val is None:
            raise ValueError(f"Entity missing required attribute '{attr_name}'.")
        return float(val)
