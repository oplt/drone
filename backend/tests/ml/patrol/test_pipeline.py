from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.ml.patrol.pipeline import DroneAnomalyPipeline


class DroneAnomalyPipelineTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = DroneAnomalyPipeline.__new__(DroneAnomalyPipeline)

    def test_get_latest_telemetry_reads_live_cache(self) -> None:
        telemetry_manager = SimpleNamespace(
            _running=True,
            last_telemetry={
                "timestamp": time.time(),
                "position": {
                    "lat": 51.2194,
                    "lon": 4.4025,
                    "alt": 120.0,
                    "relative_alt": 37.5,
                },
                "status": {"heading": 182.0, "groundspeed": 6.5},
                "camera": {"gimbal_pitch_deg": -42.0},
            },
        )

        with patch("backend.messaging.websocket.telemetry_manager", telemetry_manager):
            telemetry = self.pipeline._get_latest_telemetry()

        self.assertEqual(telemetry["lat"], 51.2194)
        self.assertEqual(telemetry["lon"], 4.4025)
        self.assertEqual(telemetry["altitude_m"], 37.5)
        self.assertEqual(telemetry["heading"], 182.0)
        self.assertEqual(telemetry["groundspeed"], 6.5)
        self.assertEqual(telemetry["gimbal_pitch_deg"], -42.0)
        self.assertTrue(telemetry["has_position"])

    def test_get_latest_telemetry_rejects_stale_cache(self) -> None:
        telemetry_manager = SimpleNamespace(
            _running=True,
            last_telemetry={
                "timestamp": time.time() - 30.0,
                "position": {"lat": 50.0, "lon": 4.0, "relative_alt": 35.0},
                "status": {"heading": 90.0, "groundspeed": 5.0},
            },
        )

        with patch("backend.messaging.websocket.telemetry_manager", telemetry_manager):
            telemetry = self.pipeline._get_latest_telemetry()

        self.assertIsNone(telemetry["lat"])
        self.assertIsNone(telemetry["lon"])
        self.assertIsNone(telemetry["altitude_m"])
        self.assertIsNone(telemetry["heading"])
        self.assertIsNone(telemetry["groundspeed"])
        self.assertFalse(telemetry["has_position"])


if __name__ == "__main__":
    unittest.main()
