from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.modules.missions.planning.grid import (
    GridPlanner,
    _validate_plan_limits,
    combine_grid_plans,
)

router = APIRouter()


class GridPreviewIn(BaseModel):
    field_polygon_lonlat: list[list[float]] = Field(..., min_length=3)
    row_spacing_m: float = Field(default=7.5, gt=0, le=200)
    grid_angle_deg: float | None = Field(default=None, ge=0, lt=180)
    safety_inset_m: float = Field(default=1.5, ge=0)
    pattern_mode: Literal["boustrophedon", "crosshatch"] = "boustrophedon"
    crosshatch_angle_offset_deg: float = Field(default=90.0, gt=0, lt=180)
    start_corner: Literal["auto", "nw", "ne", "sw", "se"] = "auto"
    lane_strategy: Literal["serpentine", "one_way"] = "serpentine"
    row_stride: int = Field(default=1, ge=1, le=20)
    row_phase_m: float = Field(default=0.0, ge=0.0, le=500.0)


class GridPreviewOut(BaseModel):
    waypoints: list[dict]
    work_leg_mask: list[bool]
    angle_deg: float
    spacing_m: float
    stats: dict


@router.post("/missions/grid-preview", response_model=GridPreviewOut)
async def preview_grid(payload: GridPreviewIn) -> GridPreviewOut:
    try:
        polygon = [tuple(point) for point in payload.field_polygon_lonlat]
        angle = payload.grid_angle_deg if payload.grid_angle_deg is not None else 0.0
        primary = GridPlanner.generate(
            polygon,
            spacing_m=payload.row_spacing_m,
            angle_deg=angle,
            inset_m=payload.safety_inset_m,
            start_corner=payload.start_corner,
            lane_strategy=payload.lane_strategy,
            row_stride=payload.row_stride,
            row_phase_m=payload.row_phase_m,
        )
        plans = [primary]
        if payload.pattern_mode == "crosshatch":
            secondary_angle = (angle + payload.crosshatch_angle_offset_deg) % 180.0
            if abs(secondary_angle - angle) > 1e-6:
                plans.append(
                    GridPlanner.generate(
                        polygon,
                        spacing_m=payload.row_spacing_m,
                        angle_deg=secondary_angle,
                        inset_m=payload.safety_inset_m,
                        start_corner=payload.start_corner,
                        lane_strategy=payload.lane_strategy,
                        row_stride=payload.row_stride,
                        row_phase_m=payload.row_phase_m,
                    )
                )
        plan = combine_grid_plans(
            plans,
            poly_lonlat=polygon,
            pattern_mode=payload.pattern_mode,
        )
        _validate_plan_limits(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GridPreviewOut(
        waypoints=[{"lat": waypoint.lat, "lon": waypoint.lon} for waypoint in plan.waypoints],
        work_leg_mask=plan.work_leg_mask,
        angle_deg=plan.angle_deg,
        spacing_m=plan.spacing_m,
        stats=plan.stats,
    )
