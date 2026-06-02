from __future__ import annotations

import hashlib
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseSensorRig


class WarehouseSensorRigMixin:
    @staticmethod
    def _resolve_calibration_urls(
        intrinsics_url: str | None,
        extrinsics_url: str | None,
    ) -> tuple[str | None, str | None, bool]:
        resolved_intrinsics = (intrinsics_url or "").strip() or None
        resolved_extrinsics = (extrinsics_url or "").strip() or None
        calibration_complete = bool(resolved_intrinsics and resolved_extrinsics)
        return resolved_intrinsics, resolved_extrinsics, calibration_complete

    @staticmethod
    def _apply_sensor_rig_fields(
        rig: WarehouseSensorRig,
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
        active: bool = True,
    ) -> WarehouseSensorRig:
        resolved_intrinsics, resolved_extrinsics, calibration_complete = (
            WarehouseSensorRigMixin._resolve_calibration_urls(
                intrinsics_url, extrinsics_url
            )
        )
        rig.owner_id = owner_id
        rig.org_id = org_id
        rig.name = name.strip()
        rig.camera_model = camera_model.strip()
        rig.stereo_baseline_m = stereo_baseline_m
        rig.intrinsics_url = resolved_intrinsics
        rig.extrinsics_url = resolved_extrinsics
        rig.imu_transform_json = dict(imu_transform_json)
        rig.firmware_version = (firmware_version or "").strip() or None
        rig.isaac_ros_version = (isaac_ros_version or "").strip() or None
        rig.calibration_status = "valid" if calibration_complete else "missing"
        rig.calibration_hash = (
            hashlib.sha256(
                f"{resolved_intrinsics}|{resolved_extrinsics}".encode()
            ).hexdigest()[:32]
            if calibration_complete
            else None
        )
        rig.calibration_meta = (
            {"source": "create", "auto_validated": True} if calibration_complete else {}
        )
        rig.active = active
        return rig

    async def _find_inactive_sensor_rig_by_name(
        self,
        db: AsyncSession,
        *,
        org_id: int | None,
        owner_id: int,
        name: str,
    ) -> WarehouseSensorRig | None:
        stripped_name = name.strip()
        if org_id is not None:
            scope = WarehouseSensorRig.org_id == org_id
        else:
            scope = WarehouseSensorRig.owner_id == owner_id
        return (
            await db.execute(
                select(WarehouseSensorRig)
                .where(
                    scope,
                    WarehouseSensorRig.name == stripped_name,
                    WarehouseSensorRig.active.is_(False),
                )
                .order_by(WarehouseSensorRig.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

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
        stripped_name = name.strip()
        existing = await self._find_inactive_sensor_rig_by_name(
            db,
            org_id=org_id,
            owner_id=owner_id,
            name=stripped_name,
        )
        if existing is not None:
            self._apply_sensor_rig_fields(
                existing,
                owner_id=owner_id,
                org_id=org_id,
                name=stripped_name,
                camera_model=camera_model,
                stereo_baseline_m=stereo_baseline_m,
                intrinsics_url=intrinsics_url,
                extrinsics_url=extrinsics_url,
                imu_transform_json=imu_transform_json,
                firmware_version=firmware_version,
                isaac_ros_version=isaac_ros_version,
                active=True,
            )
            await db.flush()
            await db.refresh(existing)
            return existing

        rig = WarehouseSensorRig()
        self._apply_sensor_rig_fields(
            rig,
            owner_id=owner_id,
            org_id=org_id,
            name=stripped_name,
            camera_model=camera_model,
            stereo_baseline_m=stereo_baseline_m,
            intrinsics_url=intrinsics_url,
            extrinsics_url=extrinsics_url,
            imu_transform_json=imu_transform_json,
            firmware_version=firmware_version,
            isaac_ros_version=isaac_ros_version,
            active=True,
        )
        db.add(rig)
        await db.flush()
        await db.refresh(rig)
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
        await db.refresh(rig)
        return rig

    async def delete_sensor_rig(
        self,
        db: AsyncSession,
        *,
        rig: WarehouseSensorRig,
    ) -> None:
        await db.delete(rig)
        await db.flush()
