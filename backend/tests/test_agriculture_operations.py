import pytest

from backend.core.config.runtime import settings


def test_agriculture_analysis_uses_isolated_inference_queue():
    assert settings.celery_agriculture_inference_queue == "agriculture-rgb-inference"
    assert settings.celery_agriculture_inference_soft_time_limit_seconds < settings.celery_agriculture_inference_time_limit_seconds


def test_agriculture_operational_metrics_are_registered():
    from backend.observability import prometheus_metrics

    prometheus_metrics.agriculture_runs_started_total.labels(queue="test").inc()
    prometheus_metrics.agriculture_georeference_rate.labels(stage="test").set(.75)


def test_agriculture_media_quota_rejects_oversized_manifest():
    from backend.modules.agriculture.storage import AgricultureStorage

    with pytest.raises(ValueError, match="exceeds configured quota"):
        AgricultureStorage.validate_content(AgricultureStorage(), content_type="video/mp4", byte_size=101, quota_bytes=100)


def test_agriculture_storage_retention_is_timezone_safe():
    from datetime import UTC, datetime, timedelta
    from backend.modules.agriculture.storage import AgricultureStorage

    assert AgricultureStorage.is_expired(datetime.now(UTC) - timedelta(days=31), retention_days=30)
    assert not AgricultureStorage.is_expired(datetime.now(UTC) - timedelta(days=1), retention_days=30)


def test_agriculture_storage_requires_tenant_prefix():
    from backend.modules.agriculture.storage import AgricultureStorage

    storage = AgricultureStorage()
    storage.validate_tenant_key("org/7/flights/flight-1/image.jpg", org_id=7, resource="flights/flight-1")
    with pytest.raises(ValueError, match="organization/resource prefix"):
        storage.validate_tenant_key("uploads/image.jpg", org_id=7, resource="flights/flight-1")


def test_agriculture_storage_resumable_chunks_are_ordered_and_atomic(tmp_path):
    import hashlib
    from backend.modules.agriculture.storage import AgricultureStorage

    storage = AgricultureStorage(tmp_path)
    key = "org/7/uploads/session.part"
    assert storage.write_chunk(key, b"abc", offset=0) == 3
    with pytest.raises(ValueError, match="offset mismatch"):
        storage.write_chunk(key, b"x", offset=1)
    assert storage.write_chunk(key, b"def", offset=3) == 6
    assert storage.read_range(key, offset=0, length=6) == b"abcdef"
    assert storage.checksum(key) == hashlib.sha256(b"abcdef").hexdigest()


def test_agriculture_rate_limit_fails_closed_with_local_fallback(monkeypatch):
    import asyncio
    import uuid
    import backend.core.rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: (_ for _ in ()).throw(ConnectionError("redis unavailable")))
    async def run():
        key = f"test-agriculture-rate-limit-{uuid.uuid4()}"
        await rate_limit.enforce_rate_limit(key=key, limit=1, window_seconds=60)
        with pytest.raises(Exception) as error:
            await rate_limit.enforce_rate_limit(key=key, limit=1, window_seconds=60)
        assert getattr(error.value, "status_code", None) == 429

    asyncio.run(run())
