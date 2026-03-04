from abc import ABC, abstractmethod
from typing import Iterable
from .models import Coordinate, Telemetry


class DroneClient(ABC):
    def __init__(self):
        self.home_location = None

    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def arm_and_takeoff(self, alt: float) -> None: ...
    @abstractmethod
    def goto(self, coord: Coordinate) -> None: ...
    @abstractmethod
    def set_mode(self, mode: str) -> None: ...
    @abstractmethod
    def get_telemetry(self) -> Telemetry: ...
    @abstractmethod
    def follow_waypoints(self, path: Iterable[Coordinate]) -> None: ...
    @abstractmethod
    def land(self) -> None: ...
    @abstractmethod
    def close(self) -> None: ...

    # Optional camera/survey controls used by photogrammetry missions.
    # Implementations may return False when unsupported.
    def set_groundspeed(self, speed_mps: float) -> bool:
        return False

    def start_image_capture(
        self,
        *,
        mode: str = "distance",
        distance_m: float | None = None,
        interval_s: float | None = None,
    ) -> bool:
        return False

    def stop_image_capture(self) -> bool:
        return False

    # Optional direct image retrieval hook for adapters that can pull images
    # from the vehicle/camera storage after flight.
    def download_captured_images(self, *, destination_dir: str) -> list[str]:
        return []
