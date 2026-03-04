import googlemaps
from backend.drone.models import Coordinate


class GoogleMapsClient:
    def __init__(self, api_key: str):
        self.client = googlemaps.Client(api_key)

    def geocode(self, address: str) -> Coordinate:
        res = self.client.geocode(address)
        loc = res[0]["geometry"]["location"]
        return Coordinate(lat=loc["lat"], lon=loc["lng"])

    def waypoints_between(self, start: Coordinate, end: Coordinate, steps: int = 5):
        if steps <= 0:
            raise ValueError("steps must be > 0")
        dlat = (end.lat - start.lat) / steps
        dlon = (end.lon - start.lon) / steps
        for i in range(1, steps + 1):
            yield Coordinate(
                lat=start.lat + dlat * i,
                lon=start.lon + dlon * i,
                alt=end.alt,
            )

    # ✅ NEW: Google Elevation API (single)
    def elevation_m(self, lat: float, lon: float) -> float:
        res = self.client.elevation((lat, lon))
        if not res:
            raise RuntimeError("No elevation result from Google Elevation API")
        return float(res[0]["elevation"])  # meters AMSL

    # ✅ NEW: Google Elevation API (batch)
    def elevations_m(self, coords: list[tuple[float, float]]) -> list[float]:
        # coords: [(lat, lon), ...]
        if not coords:
            return []
        res = self.client.elevation(coords)
        if not res or len(res) != len(coords):
            # Google may still respond, but be defensive.
            raise RuntimeError("Elevation batch returned unexpected result length")
        return [float(r["elevation"]) for r in res]

    # Compatibility aliases used in older mission and preflight flows.
    def get_elevation(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)

    def get_elevations(self, coords: list[tuple[float, float]]) -> list[float]:
        return self.elevations_m(coords)

    def elevation(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)

    def elevation_at(self, lat: float, lon: float) -> float:
        return self.elevation_m(lat, lon)
