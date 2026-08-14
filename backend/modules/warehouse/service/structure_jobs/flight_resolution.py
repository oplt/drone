"""Resolve the latest extractable model flight for a warehouse map."""

from __future__ import annotations

from sqlalchemy import select

from backend.modules.warehouse.models import WarehouseMappingJob, WarehouseModel


async def resolve_latest_model_flight(
    db,
    *,
    warehouse_map_id: int,
) -> tuple[int, str] | None:
    """Return (model_id, client_flight_id) for the newest ready model of a map.

    Reads the client_flight_id from the mapping job params persisted by
    ``persist_capture``. Returns ``None`` when nothing is extractable yet.
    """
    rows = (
        await db.execute(
            select(WarehouseMappingJob, WarehouseModel)
            .join(WarehouseModel, WarehouseMappingJob.model_id == WarehouseModel.id)
            .where(
                WarehouseMappingJob.warehouse_map_id == int(warehouse_map_id),
                WarehouseModel.status == "ready",
            )
            .order_by(WarehouseMappingJob.id.desc())
            .limit(10)
        )
    ).all()
    for job, model in rows:
        params = job.params if isinstance(job.params, dict) else {}
        capture = params.get("capture_result")
        capture = capture if isinstance(capture, dict) else {}
        flight = capture.get("client_flight_id") or params.get("client_flight_id")
        token = str(flight or "").strip()
        if token:
            return int(model.id), token
    return None
