from backend.modules.agriculture import storage_operations
from backend.modules.agriculture.storage import AgricultureStorage


def test_local_restore_drill_verifies_and_cleans_up(monkeypatch, tmp_path):
    storage = AgricultureStorage(tmp_path)
    monkeypatch.setattr(storage_operations, "agriculture_storage", storage)
    result = storage_operations.local_restore_drill()
    assert result == {"status": "pass", "checksum_verified": True}
    assert list(tmp_path.rglob("*")) == []


def test_storage_readiness_reports_local_backend(monkeypatch, tmp_path):
    storage = AgricultureStorage(tmp_path)
    monkeypatch.setattr(storage_operations, "agriculture_storage", storage)
    result = storage_operations.storage_readiness()
    assert result["status"] == "ready"
    assert {check["code"] for check in result["checks"]} >= {
        "backend_configured",
        "object_store_reachable",
        "backup_prefix_valid",
    }
