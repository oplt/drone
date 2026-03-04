from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math

@dataclass
class TerrainProfile:
    # elevation above mean sea level (AMSL) in meters
    elevation_m: float

class TerrainService:
    """
    Provide terrain elevations for (lat, lon).
    Implement with:
      - Google Elevation API (easy)
      - Copernicus/SRTM DEM tiles (more work, no API key)
      - Your own DSM from photogrammetry (best for fields)
    """
    def __init__(self, maps_client):
        self.maps = maps_client

    def elevation_m(self, lat: float, lon: float) -> float:
        # EXPECTATION: implement in GoogleMapsClient:
        #   maps.get_elevation(lat, lon) -> float
        return float(self.maps.get_elevation(lat, lon))

    def elevation_many_m(self, coords: Iterable[tuple[float, float]]) -> list[float]:
        # EXPECTATION: implement in GoogleMapsClient:
        #   maps.get_elevations([(lat,lon), ...]) -> list[float]
        return [float(x) for x in self.maps.get_elevations(list(coords))]