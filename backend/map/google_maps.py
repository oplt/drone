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
        # simple linear interpolation as placeholder; you can replace with Directions API polyline decoding
        dlat = (end.lat - start.lat) / steps
        dlon = (end.lon - start.lon) / steps
        for i in range(1, steps + 1):
            yield Coordinate(lat=start.lat + dlat*i, lon=start.lon + dlon*i, alt=end.alt)
