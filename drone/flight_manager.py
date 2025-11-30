# drone/flight_manager.py

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .drone_base import DroneClient
from .models import Coordinate
from map.google_maps import GoogleMapsClient
from db.repository import TelemetryRepository
from messaging.mqtt import MqttClient
from messaging.opcua import DroneOpcUaServer
from analysis.range_estimator import SimpleWhPerKmModel, RangeEstimateResult
from utils.geo import haversine_km, _coord_from_home, _total_mission_distance_km
from config import settings


class FlightManager:
    """
    Owns mission planning, pre-flight range check, in-flight range guarding,
    and emergency monitoring. Does NOT know about video or LLM.
    """

    def __init__(
            self,
            drone: DroneClient,
            maps: GoogleMapsClient,
            repo: TelemetryRepository,
            opcua: DroneOpcUaServer,
            mqtt: MqttClient,
            range_model: Optional[SimpleWhPerKmModel] = None,
    ) -> None:
        self.drone = drone
        self.maps = maps
        self.repo = repo
        self.opcua = opcua
        self.mqtt = mqtt
        self.range_model = range_model or SimpleWhPerKmModel()

        self._running: bool = True
        self._flight_id: Optional[int] = None
        self._dest_coord: Optional[Coordinate] = None

    # ---- lifecycle / coordination -------------------------------------------------

    def set_flight_context(self, flight_id: int, dest: Coordinate) -> None:
        """Called by Orchestrator once the Flight row is created."""
        self._flight_id = flight_id
        self._dest_coord = dest

    @property
    def flight_id(self) -> Optional[int]:
        return self._flight_id

    def stop(self) -> None:
        """Signal background tasks to stop."""
        self._running = False

    # ---- range estimation helpers --------------------------------------------------

    def _estimate_range(self, distance_km: float, battery_level_frac: float | None) -> RangeEstimateResult:
        est_range_km = self.range_model.estimate_range_km(
            capacity_Wh=settings.battery_capacity_wh,
            battery_level_frac=battery_level_frac,
            cruise_power_W=settings.cruise_power_w,
            cruise_speed_mps=settings.cruise_speed_mps,
            reserve_frac=settings.energy_reserve_frac,
        )
        note = ""
        feasible = False
        req_Wh = None
        avail_Wh = None
        if est_range_km is None:
            note = "No battery level reading; cannot estimate range (fail safe)."
        else:
            feasible = est_range_km >= distance_km
            v_kmh = settings.cruise_speed_mps * 3.6
            wh_per_km = settings.cruise_power_w / v_kmh
            req_Wh = wh_per_km * distance_km
            avail_Wh = settings.battery_capacity_wh * max(
                0.0,
                (battery_level_frac or 0.0) - settings.energy_reserve_frac,
                )
            if not feasible:
                note = f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km."
            else:
                note = f"OK: dist {distance_km:.2f} km ≤ est range {est_range_km:.2f} km."

        return RangeEstimateResult(distance_km, est_range_km, avail_Wh, req_Wh, feasible, note)

    async def _preflight_range_check(
            self,
            home: Coordinate,
            start: Coordinate,
            dest: Coordinate,
    ) -> RangeEstimateResult:
        """
        Uses total route distance: home→start→dest→home.
        Assumes self.drone.connect() was already called so home_location is set.
        """
        distance_km = _total_mission_distance_km(home, start, dest)

        t = self.drone.get_telemetry()
        level_frac = (
            None
            if t.battery_remaining is None
            else max(0.0, min(1.0, float(t.battery_remaining) / 100.0))
        )

        capacity_Wh = settings.battery_capacity_wh
        cruise_power_W = settings.cruise_power_w
        cruise_speed_mps = settings.cruise_speed_mps
        reserve_frac = settings.energy_reserve_frac

        model = SimpleWhPerKmModel()
        est_range_km = model.estimate_range_km(
            capacity_Wh=capacity_Wh,
            battery_level_frac=level_frac,
            cruise_power_W=cruise_power_W,
            cruise_speed_mps=cruise_speed_mps,
            reserve_frac=reserve_frac,
        )

        v_kmh = max(0.1, cruise_speed_mps * 3.6)
        wh_per_km = cruise_power_W / v_kmh
        required_Wh = distance_km * wh_per_km
        available_Wh = (
            None
            if level_frac is None
            else max(0.0, capacity_Wh * max(0.0, level_frac - reserve_frac))
        )

        feasible = (est_range_km is not None) and (est_range_km >= distance_km)
        reason = "OK"
        if est_range_km is None:
            reason = "No battery level reading; cannot estimate range"
        elif not feasible:
            reason = f"Insufficient range. Need ~{distance_km:.2f} km, est range {est_range_km:.2f} km."

        return RangeEstimateResult(
            distance_km=distance_km,
            est_range_km=est_range_km,
            available_Wh=available_Wh,
            required_Wh=required_Wh,
            feasible=feasible,
            reason=reason,
        )

    # ---- background guard tasks ----------------------------------------------------

    async def range_guard_task(self) -> None:
        """Re-evaluate remaining distance periodically and warn if we're going to run short."""
        while self._running:
            try:
                if self._dest_coord:
                    t = self.drone.get_telemetry()
                    remain_km = haversine_km(
                        t.lat,
                        t.lon,
                        self._dest_coord.lat,
                        self._dest_coord.lon,
                    )
                    level = None
                    if t.battery_current is not None:
                        level = max(0.0, min(1.0, float(t.battery_current) / 100.0))
                    res = self._estimate_range(remain_km, level)
                    await self.opcua.update_range(
                        res.est_range_km or 0.0,
                        res.feasible,
                        res.reason,
                        )
                    if not res.feasible:
                        self.mqtt.publish(
                            "drone/warnings",
                            {
                                "type": "inflight_range_warning",
                                "remaining_distance_km": remain_km,
                                "est_range_km": res.est_range_km,
                                "note": res.reason,
                            },
                        )
                        # Optional: trigger RTL or hold
                        # self.drone.set_mode("RTL")
            except Exception:
                logging.info("CANNOT APPLY range_guard_task")

            await asyncio.sleep(2.0)

    async def emergency_monitor_task(self) -> None:
        """Monitor for emergency conditions and handle them."""
        while self._running:
            try:
                if hasattr(self.drone, "dead_mans_switch_active"):
                    if not self.drone.dead_mans_switch_active and self.drone.vehicle:
                        self.mqtt.publish(
                            "drone/emergency",
                            {
                                "type": "dead_mans_switch_triggered",
                                "message": "Connection lost - drone executing emergency protocol",
                                "timestamp": asyncio.get_event_loop().time(),
                            },
                            qos=2,
                        )
                        self._running = False
                        break
                await asyncio.sleep(1.0)
            except Exception as e:
                logging.info(f"Error in emergency monitor: {e}")
                await asyncio.sleep(1.0)

    # ---- core mission -------------------------------------------------------------

    async def fly_route(
            self,
            start: Coordinate,
            dest: Coordinate,
            cruise_alt: float = 30.0,
    ) -> None:
        """
        Full mission:
        - mission_created event
        - preflight range check
        - arm & takeoff
        - follow waypoints
        - RTL and wait until disarmed
        """
        self._running = True

        if self._flight_id is None:
            # In practice, Orchestrator should create flight and call set_flight_context(),
            # but we keep this fallback for robustness.
            self._flight_id = await self.repo.create_flight(
                start_lat=start.lat,
                start_lon=start.lon,
                start_alt=start.alt,
                dest_lat=dest.lat,
                dest_lon=dest.lon,
                dest_alt=dest.alt,
            )
            logging.info(f"[FlightManager] Created flight with ID: {self._flight_id}")

        await self.repo.add_event(
            self._flight_id,
            "mission_created",
            {"alt": cruise_alt},
        )

        self._dest_coord = dest

        await asyncio.sleep(1.0)
        await self.repo.add_event(self._flight_id, "connected", {})

        # Preflight range check
        home = _coord_from_home(self.drone.home_location)
        preflight = await self._preflight_range_check(home, start, dest)
        if not preflight.feasible and settings.ENFORCE_PREFLIGHT_RANGE:
            raise RuntimeError(preflight.reason)

        await asyncio.to_thread(self.drone.arm_and_takeoff, cruise_alt)
        await self.repo.add_event(self._flight_id, "takeoff", {})

        path = list(self.maps.waypoints_between(start, dest, steps=6))
        await asyncio.to_thread(self.drone.follow_waypoints, path)
        await self.repo.add_event(self._flight_id, "reached_destination", {})

        # RTL and wait for landing
        self.drone.set_mode("RTL")
        await self.repo.add_event(self._flight_id, "rtl_initiated", {})
        await asyncio.to_thread(self.drone.wait_until_disarmed, 900)
        await self.repo.add_event(self._flight_id, "landed_home", {})
        await self.repo.finish_flight(
            self._flight_id,
            status="completed",
            note="RTL to home completed",
        )
