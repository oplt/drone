from __future__ import annotations

from dataclasses import dataclass

from .models import ReturnMarginEstimate


@dataclass(frozen=True)
class ReturnMarginEvaluator:
    max_path_length_m: float
    max_mission_time_s: float
    battery_return_reserve_pct: float
    battery_emergency_land_reserve_pct: float
    nominal_speed_mps: float = 1.0

    def estimate_cost_pct(self, distance_m: float) -> float:
        if self.max_path_length_m <= 0:
            return 100.0
        return max(0.0, (float(distance_m) / float(self.max_path_length_m)) * 100.0)

    def evaluate(
        self,
        *,
        battery_remaining_pct: float,
        outbound_path_length_m: float,
        explore_buffer_m: float,
        return_path_length_m: float,
        elapsed_s: float,
    ) -> ReturnMarginEstimate:
        outbound_cost_pct = self.estimate_cost_pct(outbound_path_length_m)
        explore_cost_pct = self.estimate_cost_pct(explore_buffer_m)
        return_cost_pct = self.estimate_cost_pct(return_path_length_m)
        total_cost_pct = outbound_cost_pct + explore_cost_pct + return_cost_pct
        projected_remaining_pct = float(battery_remaining_pct) - total_cost_pct
        required_reserve_pct = max(
            float(self.battery_return_reserve_pct),
            float(self.battery_emergency_land_reserve_pct),
        )
        time_for_plan_s = float(
            outbound_path_length_m + explore_buffer_m + return_path_length_m
        ) / max(0.1, float(self.nominal_speed_mps))
        time_remaining_s = max(0.0, float(self.max_mission_time_s) - float(elapsed_s))

        can_return = (float(battery_remaining_pct) - return_cost_pct) >= float(
            self.battery_emergency_land_reserve_pct
        )
        can_continue = (
            projected_remaining_pct >= required_reserve_pct and time_for_plan_s <= time_remaining_s
        )
        should_return_now = not can_continue and can_return

        if not can_return:
            reason = "cannot_preserve_emergency_reserve"
        elif time_for_plan_s > time_remaining_s:
            reason = "mission_time_margin_exhausted"
        elif not can_continue:
            reason = "return_margin_low"
        else:
            reason = "margin_ok"

        return ReturnMarginEstimate(
            can_continue=bool(can_continue),
            can_return=bool(can_return),
            should_return_now=bool(should_return_now),
            projected_remaining_pct=float(projected_remaining_pct),
            required_reserve_pct=float(required_reserve_pct),
            outbound_cost_pct=float(outbound_cost_pct),
            explore_cost_pct=float(explore_cost_pct),
            return_cost_pct=float(return_cost_pct),
            total_cost_pct=float(total_cost_pct),
            return_path_length_m=float(return_path_length_m),
            reason=reason,
        )
