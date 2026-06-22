from __future__ import annotations

from fastapi.testclient import TestClient

from backend.entrypoints.api.app import app


def test_ml_events_endpoint_accepts_anomaly_payload() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/events",
        json={
            "event_type": "person_loitering",
            "confidence": 0.91,
            "location": {"lat": 50.93, "lon": 5.34},
            "payload": {"track_id": 1, "label": "person"},
        },
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": True}
