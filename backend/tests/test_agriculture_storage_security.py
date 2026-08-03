from __future__ import annotations

import hashlib

import pytest

from backend.modules.agriculture.storage import AgricultureStorage, EICAR_SIGNATURE


def test_agriculture_storage_rejects_tenant_escape_and_supports_verified_backup(tmp_path):
    storage = AgricultureStorage(tmp_path)
    checksum = hashlib.sha256(b"safe media").hexdigest()
    key = "org/7/flights/f-1/media.bin"
    backup = "org/7/backups/agriculture/media.bin"
    storage.write_object(key, b"safe media", expected_checksum=checksum)
    assert storage.exists(key)
    assert storage.backup(key, backup_key=backup) == backup
    storage.delete(key)
    storage.restore(backup, target_key=key, expected_checksum=checksum)
    assert storage.checksum(key) == checksum
    with pytest.raises(ValueError):
        storage.validate_tenant_key("org/8/flights/f-1/media.bin", org_id=7, resource="flights/f-1")


def test_agriculture_storage_quarantines_eicar_signature(tmp_path):
    storage = AgricultureStorage(tmp_path)
    key = "org/7/flights/f-1/suspicious.bin"
    data = b"prefix" + EICAR_SIGNATURE + b"suffix"
    storage.write_object(key, data, expected_checksum=hashlib.sha256(data).hexdigest())
    result = storage.scan_file(key)
    assert result["status"] == "quarantined"
    assert result["reason"] == "malware_signature"
