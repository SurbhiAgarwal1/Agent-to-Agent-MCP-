"""Unit tests for the Location Agent and Haversine Distance Service."""

import pytest
from app.agents.location_agent import (
    LocationAgent,
    BaseRoutingService,
    HaversineRoutingService,
)
from app.models.hospital import Hospital
from app.models.blood_bank import BloodBank
from app.models.donor import Donor


# -----------------------------------------------------------------------------
# 1. Same Coordinates Tests
# -----------------------------------------------------------------------------

def test_same_coordinates():
    """Verify that distance between identical coordinates is 0.0 km."""
    agent = LocationAgent()
    lat, lon = 28.6139, 77.2090  # New Delhi reference point

    result = agent.calculate_distance(lat, lon, lat, lon)

    assert result == {"distance_km": 0.0}


# -----------------------------------------------------------------------------
# 2. Known Coordinate Pairs
# -----------------------------------------------------------------------------

def test_known_coordinate_pairs():
    """Verify calculation against known geographical benchmark distances."""
    agent = LocationAgent()

    # Benchmark 1: New York City (40.7128, -74.0060) to London (51.5074, -0.1278)
    # Expected great-circle distance is ~5570.22 km
    nyc_to_london = agent.calculate_distance(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5565.0 <= nyc_to_london["distance_km"] <= 5575.0
    assert nyc_to_london["distance_km"] == 5570.22

    # Benchmark 2: Paris (48.8566, 2.3522) to London (51.5074, -0.1278)
    # Expected great-circle distance is ~343.56 km
    paris_to_london = agent.calculate_distance(48.8566, 2.3522, 51.5074, -0.1278)
    assert 340.0 <= paris_to_london["distance_km"] <= 346.0
    assert paris_to_london["distance_km"] == 343.56

    # Benchmark 3: Connaught Place to India Gate (New Delhi landmarks)
    # CP: 28.6315, 77.2167 -> India Gate: 28.6129, 77.2295
    # Expected distance is ~2.42 km
    delhi_landmarks = agent.calculate_distance(28.6315, 77.2167, 28.6129, 77.2295)
    assert 2.3 <= delhi_landmarks["distance_km"] <= 2.6
    assert delhi_landmarks["distance_km"] == 2.42


# -----------------------------------------------------------------------------
# 3. Nearby Locations
# -----------------------------------------------------------------------------

def test_nearby_locations():
    """Verify small distances between nearby urban coordinates (e.g. ~1 km)."""
    agent = LocationAgent()

    # ~0.009 degrees of latitude corresponds to approx ~1.00 km
    lat1, lon1 = 28.6139, 77.2090
    lat2, lon2 = 28.6229, 77.2090

    result = agent.calculate_distance(lat1, lon1, lat2, lon2)
    assert 0.95 <= result["distance_km"] <= 1.05


# -----------------------------------------------------------------------------
# 4. Invalid Coordinates
# -----------------------------------------------------------------------------

def test_invalid_coordinates_latitude_out_of_bounds():
    """Latitude must be constrained within [-90.0, 90.0]."""
    agent = LocationAgent()

    # Latitude > 90
    with pytest.raises(ValueError, match="latitude must be between -90.0 and 90.0"):
        agent.calculate_distance(91.5, 77.0, 28.0, 77.0)

    # Latitude < -90
    with pytest.raises(ValueError, match="latitude must be between -90.0 and 90.0"):
        agent.calculate_distance(28.0, 77.0, -95.0, 77.0)


def test_invalid_coordinates_longitude_out_of_bounds():
    """Longitude must be constrained within [-180.0, 180.0]."""
    agent = LocationAgent()

    # Longitude > 180
    with pytest.raises(ValueError, match="longitude must be between -180.0 and 180.0"):
        agent.calculate_distance(28.0, 185.0, 28.0, 77.0)

    # Longitude < -180
    with pytest.raises(ValueError, match="longitude must be between -180.0 and 180.0"):
        agent.calculate_distance(28.0, 77.0, 28.0, -181.0)


def test_invalid_coordinates_non_numeric():
    """Coordinates must be valid float/int numbers."""
    agent = LocationAgent()

    with pytest.raises(ValueError, match="must be a valid number"):
        agent.calculate_distance("invalid", 77.0, 28.0, 77.0)  # type: ignore

    with pytest.raises(ValueError, match="must be a valid number"):
        agent.calculate_distance(28.0, 77.0, 28.0, True)  # type: ignore


# -----------------------------------------------------------------------------
# 5. Reasonable Distance Values & Mathematical Properties
# -----------------------------------------------------------------------------

def test_symmetry_property():
    """Distance from A to B must equal distance from B to A (symmetry)."""
    agent = LocationAgent()
    p1 = (28.6139, 77.2090)
    p2 = (19.0760, 72.8777)  # Mumbai

    d1 = agent.calculate_distance(p1[0], p1[1], p2[0], p2[1])
    d2 = agent.calculate_distance(p2[0], p2[1], p1[0], p1[1])

    assert d1["distance_km"] == d2["distance_km"]


def test_triangle_inequality():
    """Haversine distance satisfies the spherical triangle inequality: d(A, C) <= d(A, B) + d(B, C)."""
    agent = LocationAgent()
    delhi = (28.6139, 77.2090)
    mumbai = (19.0760, 72.8777)
    bengaluru = (12.9716, 77.5946)

    d_delhi_bengaluru = agent.calculate_distance(*delhi, *bengaluru)["distance_km"]
    d_delhi_mumbai = agent.calculate_distance(*delhi, *mumbai)["distance_km"]
    d_mumbai_bengaluru = agent.calculate_distance(*mumbai, *bengaluru)["distance_km"]

    assert d_delhi_bengaluru <= (d_delhi_mumbai + d_mumbai_bengaluru) + 0.01


def test_antipodes_maximum_distance():
    """Maximum possible distance on Earth (antipodal points) cannot exceed half the circumference ~20,015 km."""
    agent = LocationAgent()
    # North pole to South pole
    result = agent.calculate_distance(90.0, 0.0, -90.0, 0.0)
    assert 20010.0 <= result["distance_km"] <= 20020.0


# -----------------------------------------------------------------------------
# 6. Approximate ETA & Labeling Tests
# -----------------------------------------------------------------------------

def test_estimated_travel_time_labeling():
    """Verify that estimated travel time is explicitly marked as approximate straight-line."""
    agent = LocationAgent()

    # Distance of 10.0 km at 30 km/h should be ~20 mins
    result = agent.calculate_distance(28.6139, 77.2090, 28.7000, 77.2090, include_eta=True)

    assert "distance_km" in result
    assert "estimated_time" in result
    assert "approx straight-line" in result["estimated_time"]


# -----------------------------------------------------------------------------
# 7. Integration & Swappable Routing Provider Interface
# -----------------------------------------------------------------------------

class MockRealRoutingService(BaseRoutingService):
    """Mock simulating a real road-network routing API (e.g. OSRM or Google Maps)."""

    def calculate_distance(self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> float:
        # Simulates real road network distance which is typically ~1.3x straight-line distance
        straight_line = HaversineRoutingService().calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        return straight_line * 1.30

    def estimate_travel_time(self, distance_km: float) -> str:
        return f"{round(distance_km * 2.5)} mins (live road traffic)"


def test_swappable_routing_service():
    """Verify that LocationAgent can seamlessly accept an alternative routing service without API changes."""
    # 1. Default agent with Haversine
    haversine_agent = LocationAgent()
    res_haversine = haversine_agent.calculate_distance(28.6139, 77.2090, 28.6229, 77.2090)

    # 2. Agent injected with MockRealRoutingService
    road_agent = LocationAgent(routing_service=MockRealRoutingService())
    res_road = road_agent.calculate_distance(28.6139, 77.2090, 28.6229, 77.2090, include_eta=True)

    # The road distance is higher than straight-line distance
    assert res_road["distance_km"] > res_haversine["distance_km"]
    assert "live road traffic" in res_road["estimated_time"]


# -----------------------------------------------------------------------------
# 8. Entity-to-Entity Distance Calculation
# -----------------------------------------------------------------------------

def test_distance_between_entities():
    """Verify calculating distance between Hospital, BloodBank, or Donor objects."""
    agent = LocationAgent()

    hospital = Hospital(
        hospital_id=1,
        name="Metro Hospital",
        latitude=28.6139,
        longitude=77.2090,
        address="10 Medical Way",
    )
    blood_bank = BloodBank(
        bank_id=2,
        name="Central Blood Bank",
        latitude=28.6315,
        longitude=77.2167,
        address="Connaught Place Center",
    )

    result = agent.distance_between_entities(hospital, blood_bank)
    assert result["distance_km"] > 0
    assert isinstance(result["distance_km"], float)


def test_process_dictionary_input():
    """Verify process() with dictionary payload containing coordinate aliases."""
    agent = LocationAgent()

    payload = {
        "origin_latitude": 28.6139,
        "origin_longitude": 77.2090,
        "destination_latitude": 28.6315,
        "destination_longitude": 77.2167,
    }

    result = agent.process(payload)
    assert "distance_km" in result
    assert result["distance_km"] == 2.1  # Straight line between these coordinates
