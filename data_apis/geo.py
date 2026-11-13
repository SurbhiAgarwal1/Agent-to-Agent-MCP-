"""Fictional Indian geography used by deterministic dataset generation."""
from math import cos, radians

CITIES = [
    ("Bengaluru", "Bengaluru Urban", "Karnataka", 12.9716, 77.5946),
    ("Mysuru", "Mysuru", "Karnataka", 12.2958, 76.6394),
    ("Mangaluru", "Dakshina Kannada", "Karnataka", 12.9141, 74.8560),
    ("Hyderabad", "Hyderabad", "Telangana", 17.3850, 78.4867),
    ("Chennai", "Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("Mumbai", "Mumbai City", "Maharashtra", 19.0760, 72.8777),
    ("Pune", "Pune", "Maharashtra", 18.5204, 73.8567),
    ("Delhi", "New Delhi", "Delhi", 28.6139, 77.2090),
    ("Kolkata", "Kolkata", "West Bengal", 22.5726, 88.3639),
    ("Ahmedabad", "Ahmedabad", "Gujarat", 23.0225, 72.5714),
    ("Hubballi", "Dharwad", "Karnataka", 15.3647, 75.1240),
    ("Coimbatore", "Coimbatore", "Tamil Nadu", 11.0168, 76.9558),
    ("Nagpur", "Nagpur", "Maharashtra", 21.1458, 79.0882),
    ("Jaipur", "Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("Kochi", "Ernakulam", "Kerala", 9.9312, 76.2673),
]
STREETS = ["Civic Centre Road", "Lifeline Avenue", "Central Clinic Street", "Health Park Road", "Service Lane"]

def location(rng, index):
    city, district, state, lat, lon = CITIES[index % len(CITIES)]
    # Bounded jitter stays within the metro area represented by each city.
    return {
        "city": city, "district": district, "state": state,
        "pin_code": f"{100000 + ((index * 7919) % 899999):06d}",
        "address": f"{10 + index % 980}, {STREETS[index % len(STREETS)]}, {city}",
        "latitude": round(lat + rng.uniform(-0.045, 0.045), 6),
        "longitude": round(lon + rng.uniform(-0.045, 0.045), 6),
    }

def distance_km(lat1, lon1, lat2, lon2):
    from math import asin, sqrt, sin, cos, radians
    dlat, dlon = radians(lat2-lat1), radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 6371.0 * 2 * asin(sqrt(a))

def within_box(lat, lon, center_lat, center_lon, radius_km):
    dlat = radius_km / 110.574
    dlon = radius_km / max(1.0, 111.320*cos(radians(center_lat)))
    return center_lat-dlat <= lat <= center_lat+dlat and center_lon-dlon <= lon <= center_lon+dlon
