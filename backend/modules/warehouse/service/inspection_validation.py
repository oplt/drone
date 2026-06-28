from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise

from backend.modules.warehouse.models import WarehouseScanTarget
from backend.modules.warehouse.planning.indoor.models import LocalPose, OccupancyGrid


@dataclass(frozen=True)
class InspectionValidationPolicy:
    clearance_m: float = 0.35
    min_altitude_m: float = 0.25
    max_altitude_m: float = 8.0
    approach_tolerance_deg: float = 25.0
    max_map_age_s: float = 10.0
    battery_reserve_pct: float = 20.0
    battery_cost_pct_per_m: float = 0.08
    max_path_length_m: float = 600.0


@dataclass
class InspectionValidationReport:
    passed: bool = True
    failures: list[dict[str, object]] = field(default_factory=list)
    warnings: list[dict[str, object]] = field(default_factory=list)
    paths: list[dict[str, object]] = field(default_factory=list)
    energy: dict[str, object] = field(default_factory=dict)

    def warn(self, check: str, message: str, **details: object) -> None:
        self.warnings.append({"check": check, "message": message, **details})

    def fail(self, check: str, message: str, **details: object) -> None:
        self.passed = False
        self.failures.append({"check": check, "message": message, **details})

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failures": self.failures,
            "warnings": self.warnings,
            "paths": self.paths,
            "energy": self.energy,
        }


def _pose(value: dict[str, object]) -> LocalPose:
    return LocalPose(
        x_m=float(value["x_m"]),
        y_m=float(value["y_m"]),
        z_m=float(value["z_m"]),
        yaw_deg=float(value.get("yaw_deg") or 0.0),
        frame_id=str(value.get("frame_id") or ""),
    )


def _inside_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def validate_inspection_path(
    *,
    targets: list[WarehouseScanTarget],
    grid: OccupancyGrid,
    grid_poses: list[LocalPose],
    warehouse_poses: list[LocalPose],
    warehouse_polygon: list[list[float]],
    map_age_s: float,
    start_grid_pose: LocalPose | None,
    return_to_dock: bool,
    battery_pct: float = 100.0,
    policy: InspectionValidationPolicy = InspectionValidationPolicy(),
) -> InspectionValidationReport:
    report = InspectionValidationReport()
    if map_age_s < 0 or map_age_s > policy.max_map_age_s:
        report.fail("map_freshness", "Occupancy snapshot is stale", age_s=map_age_s)
    if len(warehouse_polygon) < 3:
        report.fail("geofence", "Warehouse boundary is missing or invalid")
    if len(grid_poses) != len(targets) or len(warehouse_poses) != len(targets):
        report.fail("input", "Target and pose counts do not match")
        return report

    for target, grid_pose, warehouse_pose in zip(targets, grid_poses, warehouse_poses, strict=True):
        target_id = int(target.id)
        if not policy.min_altitude_m <= warehouse_pose.z_m <= policy.max_altitude_m:
            report.fail("altitude", "Scan pose is outside altitude envelope", target_id=target_id)
        if warehouse_polygon and not _inside_polygon(
            warehouse_pose.x_m, warehouse_pose.y_m, warehouse_polygon
        ):
            report.fail("geofence", "Scan pose is outside warehouse boundary", target_id=target_id)
        cell = grid.world_to_cell(grid_pose)
        if not grid.is_traversable(*cell, clearance_m=policy.clearance_m):
            report.fail(
                "point_clearance", "Scan pose lacks required clearance", target_id=target_id
            )

        normal = target.shelf_normal_local_json
        point = target.target_point_local_json
        if isinstance(normal, dict) and isinstance(point, dict):
            vx = float(point["x_m"]) - warehouse_pose.x_m
            vy = float(point["y_m"]) - warehouse_pose.y_m
            vz = float(point["z_m"]) - warehouse_pose.z_m
            nx, ny, nz = (float(normal[key]) for key in ("x", "y", "z"))
            denom = math.sqrt(vx * vx + vy * vy + vz * vz) * math.sqrt(nx * nx + ny * ny + nz * nz)
            angle = (
                180.0
                if denom <= 1e-9
                else math.degrees(
                    math.acos(max(-1.0, min(1.0, (vx * nx + vy * ny + vz * nz) / denom)))
                )
            )
            if angle > policy.approach_tolerance_deg:
                report.fail(
                    "approach_cone",
                    "Scan pose approaches shelf from an unsafe direction",
                    target_id=target_id,
                    angle_deg=angle,
                )

    if start_grid_pose is None:
        report.fail("return_path", "A dock exit pose is required for inspection validation")
        return report
    legs = [start_grid_pose, *grid_poses]
    if return_to_dock:
        legs.append(start_grid_pose)
    total_path_m = 0.0
    for index, (start, end) in enumerate(pairwise(legs)):
        path = grid.astar_path(start, end, clearance_m=policy.clearance_m)
        if not path:
            report.fail("swept_path", "No collision-free inflated path exists", leg=index)
        else:
            path_length_m = grid.path_length_m(path)
            total_path_m += path_length_m
            report.paths.append(
                {"leg": index, "samples": len(path), "path_length_m": path_length_m}
            )
    estimated_cost_pct = total_path_m * policy.battery_cost_pct_per_m
    report.energy = {
        "path_length_m": total_path_m,
        "estimated_cost_pct": estimated_cost_pct,
        "battery_pct": battery_pct,
        "reserve_pct": policy.battery_reserve_pct,
    }
    if total_path_m > policy.max_path_length_m:
        report.fail(
            "energy_budget",
            "Inspection path exceeds maximum safe path length",
            path_length_m=total_path_m,
            maximum_m=policy.max_path_length_m,
        )
    if battery_pct - estimated_cost_pct < policy.battery_reserve_pct:
        report.fail(
            "return_energy",
            "Estimated mission energy violates return reserve",
            battery_pct=battery_pct,
            estimated_cost_pct=estimated_cost_pct,
            reserve_pct=policy.battery_reserve_pct,
        )
    return report
