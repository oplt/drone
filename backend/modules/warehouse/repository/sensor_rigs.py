from __future__ import annotations

from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.warehouse.models import WarehouseSensorRig
from backend.modules.warehouse.service.sensor_calibration import (
    normalize_sensor_extrinsics,
    sensor_calibration_checksum,
)


class WarehouseRepositoryError(RuntimeError):
    pass


_MAX_LIST_LIMIT = 500


def _clamp_limit(limit: int, *, default: int = 100, max_limit: int = _MAX_LIST_LIMIT) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(max_limit, value))


def _required_str(value: object, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise WarehouseRepositoryError(f"{field_name} cannot be empty.")
    return cleaned


def _optional_str(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


class WarehouseSensorRigMixin:
    @staticmethod
    def _resolve_calibration_urls(
        intrinsics_url: str | None,
        extrinsics_url: str | None,
    ) -> tuple[str | None, str | None, bool]:
        resolved_intrinsics = _optional_str(intrinsics_url)
        resolved_extrinsics = _optional_str(extrinsics_url)
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
        extrinsics_json: dict[str, Any],
        imu_transform_json: dict[str, Any],
        firmware_version: str | None,
        isaac_ros_version: str | None,
        active: bool = True,
    ) -> WarehouseSensorRig:
        resolved_intrinsics, resolved_extrinsics, _ = (
            WarehouseSensorRigMixin._resolve_calibration_urls(intrinsics_url, extrinsics_url)
        )
        if stereo_baseline_m is not None and float(stereo_baseline_m) <= 0:
            raise WarehouseRepositoryError("stereo_baseline_m must be positive when provided.")
        if not isinstance(imu_transform_json, dict):
            raise WarehouseRepositoryError("imu_transform_json must be a JSON object.")
        try:
            normalized_extrinsics = normalize_sensor_extrinsics(extrinsics_json)
        except ValueError as exc:
            normalized_extrinsics = {}
            if extrinsics_json:
                raise WarehouseRepositoryError(str(exc)) from exc
        calibration_complete = bool(resolved_intrinsics and normalized_extrinsics)

        rig.owner_id = int(owner_id)
        rig.org_id = org_id
        rig.name = _required_str(name, field_name="name")
        rig.camera_model = _required_str(camera_model, field_name="camera_model")
        rig.stereo_baseline_m = None if stereo_baseline_m is None else float(stereo_baseline_m)
        rig.intrinsics_url = resolved_intrinsics
        rig.extrinsics_url = resolved_extrinsics
        rig.extrinsics_json = normalized_extrinsics
        rig.imu_transform_json = dict(imu_transform_json)
        rig.firmware_version = _optional_str(firmware_version)
        rig.isaac_ros_version = _optional_str(isaac_ros_version)
        rig.calibration_status = "valid" if calibration_complete else "missing"
        rig.calibration_hash = (
            sensor_calibration_checksum(normalized_extrinsics) if calibration_complete else None
        )
        rig.calibration_meta = (
            {"source": "create", "auto_validated": True} if calibration_complete else {}
        )
        rig.active = bool(active)
        return rig

    async def _find_inactive_sensor_rig_by_name(
        self,
        db: AsyncSession,
        *,
        org_id: int | None,
        owner_id: int,
        name: str,
    ) -> WarehouseSensorRig | None:
        stripped_name = _required_str(name, field_name="name")
        if org_id is not None:
            scope = WarehouseSensorRig.org_id == int(org_id)
        else:
            scope = WarehouseSensorRig.owner_id == int(owner_id)
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
            or_(
                WarehouseSensorRig.owner_id == int(owner_id),
                WarehouseSensorRig.org_id == int(org_id),
            )
            if allow_org_access and org_id is not None
            else WarehouseSensorRig.owner_id == int(owner_id)
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
                    .limit(_clamp_limit(limit))
                )
            )
            .scalars()
            .all()
        )
        return cast(list[WarehouseSensorRig], list(rows))

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
                    WarehouseSensorRig.id == int(sensor_rig_id),
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
        extrinsics_json: dict[str, Any],
        imu_transform_json: dict[str, Any],
        firmware_version: str | None,
        isaac_ros_version: str | None,
    ) -> WarehouseSensorRig:
        stripped_name = _required_str(name, field_name="name")
        existing = await self._find_inactive_sensor_rig_by_name(
            db,
            org_id=org_id,
            owner_id=int(owner_id),
            name=stripped_name,
        )
        if existing is not None:
            self._apply_sensor_rig_fields(
                existing,
                owner_id=int(owner_id),
                org_id=org_id,
                name=stripped_name,
                camera_model=camera_model,
                stereo_baseline_m=stereo_baseline_m,
                intrinsics_url=intrinsics_url,
                extrinsics_url=extrinsics_url,
                extrinsics_json=extrinsics_json,
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
            owner_id=int(owner_id),
            org_id=org_id,
            name=stripped_name,
            camera_model=camera_model,
            stereo_baseline_m=stereo_baseline_m,
            intrinsics_url=intrinsics_url,
            extrinsics_url=extrinsics_url,
            extrinsics_json=extrinsics_json,
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
        extrinsics_json: dict[str, Any] | None,
        imu_transform_json: dict[str, Any] | None,
        calibration_meta: dict[str, Any],
    ) -> WarehouseSensorRig:
        status = _required_str(calibration_status, field_name="calibration_status")
        rig.calibration_status = status
        if intrinsics_url is not None:
            rig.intrinsics_url = _optional_str(intrinsics_url)
        if extrinsics_url is not None:
            rig.extrinsics_url = _optional_str(extrinsics_url)
        if extrinsics_json is not None:
            try:
                rig.extrinsics_json = normalize_sensor_extrinsics(extrinsics_json)
            except ValueError as exc:
                raise WarehouseRepositoryError(str(exc)) from exc
        if imu_transform_json is not None:
            if not isinstance(imu_transform_json, dict):
                raise WarehouseRepositoryError("imu_transform_json must be a JSON object.")
            rig.imu_transform_json = dict(imu_transform_json)
        if not isinstance(calibration_meta, dict):
            raise WarehouseRepositoryError("calibration_meta must be a JSON object.")
        rig.calibration_meta = dict(calibration_meta)

        computed_hash = (
            sensor_calibration_checksum(rig.extrinsics_json) if rig.extrinsics_json else None
        )
        cleaned_hash = _optional_str(calibration_hash)
        if cleaned_hash is not None and cleaned_hash != computed_hash:
            raise WarehouseRepositoryError("calibration_hash does not match extrinsics_json")
        cleaned_hash = computed_hash
        rig.calibration_status = (
            status if status != "valid" or (rig.intrinsics_url and cleaned_hash) else "failed"
        )
        rig.calibration_hash = cleaned_hash
        await db.flush()
        await db.refresh(rig)
        return rig

    async def delete_sensor_rig(
        self,
        db: AsyncSession,
        *,
        rig: WarehouseSensorRig,
    ) -> None:
        # The rest of this repository treats inactive rigs as recoverable records
        # (create_sensor_rig can reactivate them). Keep delete soft and reversible.
        rig.active = False
        await db.flush()
