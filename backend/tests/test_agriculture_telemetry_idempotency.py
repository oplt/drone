from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.modules.agriculture.models import AgricultureTelemetryReceipt
from backend.modules.agriculture.routers import live as agriculture_live
from backend.modules.agriculture.schemas import TelemetryBatchIn


def _sample_batch() -> TelemetryBatchIn:
    return TelemetryBatchIn(
        samples=[
            {
                "timestamp": datetime.now(UTC),
                "lat": 50.85,
                "lon": 4.35,
            }
        ]
    )


@pytest.mark.asyncio
async def test_telemetry_receipt_lookup_before_lock(monkeypatch) -> None:
    batch = _sample_batch()
    payload_checksum = agriculture_live._telemetry_payload_checksum(batch)
    flight = SimpleNamespace(
        id="flight-1",
        field_id=10,
        mission_id="mission-1",
        input_manifest={},
        coverage_summary={},
    )
    monkeypatch.setattr(
        agriculture_live._common,
        "_owned_flight",
        AsyncMock(return_value=flight),
    )

    receipt = SimpleNamespace(
        payload_checksum=payload_checksum,
        result_json={"inserted": 1, "duplicates": 0, "rejected": 0, "gap_count": 0},
    )

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=receipt)

    result = await agriculture_live.ingest_telemetry(
        "flight-1",
        batch,
        "batch-1",
        db,
        SimpleNamespace(user=SimpleNamespace(id=1, org_id=7)),
    )

    assert result.inserted == 1
    db.scalar.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_telemetry_idempotency_rejects_payload_mismatch(monkeypatch) -> None:
    flight = SimpleNamespace(
        id="flight-1",
        field_id=10,
        mission_id="mission-1",
        input_manifest={},
        coverage_summary={},
    )
    monkeypatch.setattr(
        agriculture_live._common,
        "_owned_flight",
        AsyncMock(return_value=flight),
    )

    receipt = AgricultureTelemetryReceipt(
        flight_id="flight-1",
        idempotency_key="batch-1",
        payload_checksum="deadbeef",
        result_json={"inserted": 1, "duplicates": 0, "rejected": 0, "gap_count": 0},
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=receipt)

    with pytest.raises(HTTPException) as exc:
        await agriculture_live.ingest_telemetry(
            "flight-1",
            _sample_batch(),
            "batch-1",
            db,
            SimpleNamespace(user=SimpleNamespace(id=1, org_id=7)),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_telemetry_persists_receipt_row_instead_of_manifest_map(monkeypatch) -> None:
    flight = SimpleNamespace(
        id="flight-1",
        field_id=10,
        mission_id="mission-1",
        input_manifest={},
        coverage_summary={},
    )
    monkeypatch.setattr(
        agriculture_live._common,
        "_owned_flight",
        AsyncMock(return_value=flight),
    )
    monkeypatch.setattr(agriculture_live._common, "enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(
        agriculture_live.agriculture_service,
        "ingest_telemetry",
        AsyncMock(return_value=(2, 0, 0, 0)),
    )
    monkeypatch.setattr(agriculture_live, "append_event", AsyncMock())

    added: list[object] = []
    db = AsyncMock()
    scalar_results = [None, flight, None]
    db.scalar = AsyncMock(side_effect=scalar_results)
    db.add = lambda row: added.append(row)
    db.commit = AsyncMock()

    result = await agriculture_live.ingest_telemetry(
        "flight-1",
        _sample_batch(),
        "batch-1",
        db,
        SimpleNamespace(user=SimpleNamespace(id=1, org_id=7)),
    )

    assert result.inserted == 2
    assert len(added) == 1
    assert isinstance(added[0], AgricultureTelemetryReceipt)
    assert "telemetry_batch_receipts" not in flight.input_manifest
    assert flight.input_manifest["telemetry_samples"] == 2
