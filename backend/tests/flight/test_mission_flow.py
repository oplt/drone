from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase, mock

from backend.db.models import FlightStatus
from backend.drone.models import Coordinate
from backend.flight.missions.photogrammetry_mission import PhotogrammetryMission
from backend.flight.missions.private_patrol import (
    _start_patrol_ml_runtime,
    _stop_patrol_ml_runtime,
)
from backend.ml.patrol.stream_reader import StreamReader


class _FakeRepo:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.finish_calls: list[dict] = []

    async def add_event(self, flight_id: int, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))

    async def finish_flight(self, flight_id: int, status: FlightStatus, note: str) -> None:
        self.finish_calls.append(
            {"flight_id": flight_id, "status": status, "note": note}
        )


class _FakeDrone:
    def __init__(self) -> None:
        self.home_location = SimpleNamespace(lat=50.0, lon=4.0, alt=0.0)
        self.follow_calls: list[list[Coordinate]] = []
        self.landed = False
        self.waited = False

    def set_groundspeed(self, speed_mps: float) -> bool:
        return True

    def arm_and_takeoff(self, alt: float) -> None:
        return None

    def start_image_capture(self, **kwargs) -> bool:
        return True

    def stop_image_capture(self) -> bool:
        return True

    def follow_waypoints(self, path: list[Coordinate]) -> None:
        self.follow_calls.append(list(path))

    def land(self) -> None:
        self.landed = True

    def wait_until_disarmed(self, timeout_s: float = 900) -> None:
        self.waited = True

    def download_captured_images(self, *, destination_dir: str) -> list[str]:
        return []


class _FakeCaptureService:
    def __init__(self) -> None:
        self._session_dir = Path(tempfile.mkdtemp(prefix="photo-session-"))

    def start_session(self, *, flight_id: str):
        return SimpleNamespace(
            flight_id=flight_id,
            relative_source_dir="drone_sync/test-flight",
            session_dir=self._session_dir,
        )

    def import_external_images(self, session, image_paths: list[str]) -> int:
        return len(image_paths)

    def trigger_external_sync(self, session) -> dict:
        return {"ok": True}

    def finalize_session(
        self,
        session,
        *,
        min_images: int,
        timeout_s: float,
        poll_interval_s: float,
        extra_meta: dict,
    ) -> dict:
        return {
            "status": "ready",
            "image_count": 0,
            "source_dir": session.relative_source_dir,
        }


class PhotogrammetryMissionFlowTests(IsolatedAsyncioTestCase):
    async def test_photogrammetry_returns_home_before_landing(self) -> None:
        mission = PhotogrammetryMission(
            polygon_lonlat=[(4.0, 50.0), (4.001, 50.0), (4.001, 50.001)],
            altitude_agl=30.0,
            fov_h=78.0,
            fov_v=62.0,
            front_overlap=0.8,
            side_overlap=0.7,
        )
        survey_path = [
            Coordinate(lat=50.0005, lon=4.0005, alt=30.0),
            Coordinate(lat=50.0010, lon=4.0010, alt=30.0),
        ]
        orch = SimpleNamespace(
            drone=_FakeDrone(),
            repo=_FakeRepo(),
            _flight_id=42,
        )

        with mock.patch.object(
            PhotogrammetryMission,
            "get_waypoints",
            return_value=survey_path,
        ), mock.patch(
            "backend.flight.missions.photogrammetry_mission.FlightCaptureSessionService",
            _FakeCaptureService,
        ):
            await mission.fly_photogrammetry(orch, cruise_alt=30.0)

        self.assertEqual(orch.drone.follow_calls[0], survey_path)
        self.assertEqual(len(orch.drone.follow_calls), 2)
        self.assertEqual(orch.drone.follow_calls[1][0].lat, 50.0)
        self.assertEqual(orch.drone.follow_calls[1][0].lon, 4.0)
        self.assertTrue(orch.drone.landed)
        self.assertTrue(orch.drone.waited)
        self.assertEqual(orch.repo.finish_calls[-1]["status"], FlightStatus.COMPLETED)


class PatrolMLRuntimeTests(IsolatedAsyncioTestCase):
    async def test_patrol_ml_runtime_uses_active_video_source(self) -> None:
        orch = SimpleNamespace(video=SimpleNamespace(source=0))
        zones = [
            {
                "name": "property",
                "polygon": [
                    {"lat": 50.0, "lon": 4.0},
                    {"lat": 50.0, "lon": 4.1},
                    {"lat": 50.1, "lon": 4.1},
                ],
                "restricted": True,
            }
        ]
        fake_settings = SimpleNamespace(enabled=True, stream_source="")
        fake_runtime = SimpleNamespace(
            status=mock.Mock(return_value={"running": False}),
            start=mock.AsyncMock(),
            stop=mock.AsyncMock(),
            set_zones=mock.Mock(),
        )

        with mock.patch(
            "backend.flight.missions.private_patrol.ml_settings",
            fake_settings,
        ), mock.patch(
            "backend.flight.missions.private_patrol.ml_runtime",
            fake_runtime,
        ):
            binding = await _start_patrol_ml_runtime(orch, zones=zones)
            stopped = await _stop_patrol_ml_runtime(binding)

        self.assertTrue(binding.running)
        self.assertTrue(binding.started_here)
        self.assertEqual(binding.stream_source, 0)
        fake_runtime.start.assert_awaited_once_with(stream_source=0)
        fake_runtime.set_zones.assert_called_once_with(zones)
        self.assertTrue(stopped)
        fake_runtime.stop.assert_awaited_once()


class StreamReaderTests(TestCase):
    def test_numeric_string_source_is_coerced_to_camera_index(self) -> None:
        fake_capture = mock.Mock()
        fake_capture.isOpened.return_value = True

        with mock.patch(
            "backend.ml.patrol.stream_reader.cv2.VideoCapture",
            return_value=fake_capture,
        ) as capture_ctor:
            reader = StreamReader(source="0")
            reader.open()

        capture_ctor.assert_called_once_with(0)
