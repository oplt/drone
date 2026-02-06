import math
from dataclasses import dataclass
from drone.models import Coordinate


EARTH_RADIUS_KM = 6371.0088

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat/2)**2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c

def _coord_from_home(home) -> Coordinate:
    # Accepts dronekit LocationGlobal/Relative or our Coordinate
    lat = float(getattr(home, "lat", home.lat if isinstance(home, Coordinate) else 0.0))
    lon = float(getattr(home, "lon", home.lon if isinstance(home, Coordinate) else 0.0))
    alt = float(getattr(home, "alt", 0.0))
    return Coordinate(lat=lat, lon=lon, alt=alt)

def _total_mission_distance_km(home: Coordinate, start: Coordinate, end: Coordinate) -> float:
    d1 = haversine_km(home.lat,  home.lon,  start.lat, start.lon)
    d2 = haversine_km(start.lat, start.lon, end.lat,   end.lon)
    d3 = haversine_km(end.lat,   end.lon,   home.lat,  home.lon)
    return d1 + d2 + d3
