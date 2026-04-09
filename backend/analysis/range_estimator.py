from dataclasses import dataclass


@dataclass
class RangeEstimateResult:
    distance_km: float
    est_range_km: float | None
    available_Wh: float | None
    required_Wh: float | None
    feasible: bool
    reason: str


class BatteryRangeModel:
    """Strategy base class."""

    def estimate_range_km(
        self,
        capacity_Wh: float,
        battery_level_frac: float | None,
        cruise_power_W: float,
        cruise_speed_mps: float,
        reserve_frac: float = 0.2,
    ) -> float | None:
        raise NotImplementedError


class SimpleWhPerKmModel(BatteryRangeModel):
    """
    Uses: Wh/km = P / V_kmh, where V_kmh = cruise_speed_mps * 3.6.
    Range = usable_Wh / Wh_per_km.
    """

    def estimate_range_km(
        self,
        capacity_Wh: float,
        battery_level_frac: float | None,
        cruise_power_W: float,
        cruise_speed_mps: float,
        reserve_frac: float = 0.2,
    ) -> float | None:
        if battery_level_frac is None:
            return None  # No SOC ⇒ can’t estimate (fail safe)
        v_kmh = max(0.1, cruise_speed_mps * 3.6)
        wh_per_km = cruise_power_W / v_kmh
        usable_Wh = max(0.0, capacity_Wh * max(0.0, (battery_level_frac - reserve_frac)))
        if usable_Wh <= 0:
            return 0.0
        return usable_Wh / wh_per_km
