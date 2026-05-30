from __future__ import annotations

from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseSensorRig


class WarehouseSensorRigMixin:
    def _sensor_scope(
        self,
        *,
        owner_id: int,
        org_id: int | None,
        allow_org_access: bool,
    ) -> Any:
        return (
            or_(WarehouseSensorRig.owner_id == owner_id, WarehouseSensorRig.org_id == org_id)
            if allow_org_access and org_id is not None
            else WarehouseSensorRig.owner_id == owner_id
        )

    async def list_sensor_rigs(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
        limit: int = 100,
    ) -> list[WarehouseSensorRig]:
        scope = self._sensor_scope(
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        rows = (
            (
                await db.execute(
                    select(WarehouseSensorRig)
                    .where(scope, WarehouseSensorRig.active.is_(True))
                    .order_by(WarehouseSensorRig.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return cast(list[WarehouseSensorRig], rows)

    async def get_owned_sensor_rig(
        self,
        db: AsyncSession,
        *,
        sensor_rig_id: int,
        owner_id: int,
        org_id: int | None = None,
        allow_org_access: bool = False,
    ) -> WarehouseSensorRig | None:
        scope = self._sensor_scope(
            owner_id=owner_id,
            org_id=org_id,
            allow_org_access=allow_org_access,
        )
        return (
            await db.execute(
                select(WarehouseSensorRig).where(
                    WarehouseSensorRig.id == sensor_rig_id,
                    WarehouseSensorRig.active.is_(True),
                    scope,
                )
            )
        ).scalar_one_or_none()

    async def create_sensor_rig(
        self,
        db: AsyncSession,
        *,
        owner_id: int,
        org_id: int | None,
        name: str,
        camera_model: str,
        stereo_baseline_m: float | None,
        intrinsics_url: str | None,
        extrinsics_url: str | None,
        imu_transform_json: dict[str, Any],
        firmware_version: str | None,
        isaac_ros_version: str | None,
    ) -> WarehouseSensorRig:
        rig = WarehouseSensorRig(
            owner_id=owner_id,
            org_id=org_id,
            name=name.strip(),
            camera_model=camera_model.strip(),
            stereo_baseline_m=stereo_baseline_m,
            intrinsics_url=(intrinsics_url or "").strip() or None,
            extrinsics_url=(extrinsics_url or "").strip() or None,
            imu_transform_json=dict(imu_transform_json),
            firmware_version=(firmware_version or "").strip() or None,
            isaac_ros_version=(isaac_ros_version or "").strip() or None,
            calibration_status="missing",
            calibration_meta={},
            active=True,
        )
        db.add(rig)
        await db.flush()
        return rig

    async def update_sensor_rig_calibration(
        self,
        db: AsyncSession,
        *,
        rig: WarehouseSensorRig,
        calibration_status: str,
        calibration_hash: str | None,
        intrinsics_url: str | None,
        extrinsics_url: str | None,
        imu_transform_json: dict[str, Any] | None,
        calibration_meta: dict[str, Any],
    ) -> WarehouseSensorRig:
        rig.calibration_status = calibration_status
        rig.calibration_hash = (calibration_hash or "").strip() or None
        if intrinsics_url is not None:
            rig.intrinsics_url = intrinsics_url.strip() or None
        if extrinsics_url is not None:
            rig.extrinsics_url = extrinsics_url.strip() or None
        if imu_transform_json is not None:
            rig.imu_transform_json = dict(imu_transform_json)
        rig.calibration_meta = dict(calibration_meta)
        await db.flush()
        return rig

    async def deactivate_sensor_rig(
        self,
        db: AsyncSession,
        *,
        rig: WarehouseSensorRig,
    ) -> None:
        rig.active = False
        await db.flush()
