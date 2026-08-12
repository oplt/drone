from __future__ import annotations

import hashlib
import hmac
import time
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from backend.core.config.runtime import settings


class AgricultureObjectStoragePort(Protocol):
    def sign(self, key: str, *, expires_in: int = 900) -> str: ...
    def validate_key(self, key: str) -> None: ...


ALLOWED_CONTENT_TYPES = {
    "video/mp4", "video/quicktime", "image/jpeg", "image/png", "image/tiff",
    "application/octet-stream", "application/json",
}

MAGIC_CONTENT_TYPES = {
    b"\xff\xd8\xff": {"image/jpeg"},
    b"\x89PNG\r\n\x1a\n": {"image/png"},
    b"II*\x00": {"image/tiff"},
    b"MM\x00*": {"image/tiff"},
}
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _scan_bytes(data: bytes) -> dict[str, str]:
    if EICAR_SIGNATURE in data:
        return {"status": "quarantined", "reason": "malware_signature", "scanner": "builtin-eicar"}
    if not getattr(settings, "agriculture_malware_scan_required", False):
        return {"status": "passed", "reason": "signature_scan_clear", "scanner": "builtin-eicar"}
    try:
        import clamd
        result = clamd.ClamdUnixSocket().instream(data)
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError("Agriculture malware scanner is required but unavailable") from exc
    state = next(iter(result.values()), ("ERROR", "scanner_error"))
    if state[0] == "FOUND":
        return {"status": "quarantined", "reason": "malware_detected", "scanner": "clamav", "signature": str(state[1])}
    if state[0] != "OK":
        raise RuntimeError("Agriculture malware scanner returned an error")
    return {"status": "passed", "reason": "clamav_clear", "scanner": "clamav"}


class AgricultureStorage:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or "backend/storage/agriculture").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def safe_path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Storage key escapes agriculture storage root")
        return candidate

    def validate_key(self, key: str) -> None:
        if not key or len(key) > 1024 or "\x00" in key:
            raise ValueError("Invalid agriculture storage key")
        self.safe_path(key)

    def validate_tenant_key(self, key: str, *, org_id: int | None, resource: str) -> None:
        self.validate_key(key)
        tenant = str(org_id) if org_id is not None else "public"
        expected = f"org/{tenant}/{resource.strip('/')}/"
        if not key.startswith(expected):
            raise ValueError("Agriculture storage key must use the organization/resource prefix")

    def validate_content(self, *, content_type: str | None, byte_size: int | None, quota_bytes: int | None = None) -> None:
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError("Unsupported agriculture media content type")
        if byte_size is not None and byte_size < 0:
            raise ValueError("Media byte size cannot be negative")
        if quota_bytes is not None and byte_size is not None and byte_size > quota_bytes:
            raise ValueError("Agriculture media exceeds configured quota")

    def validate_file_content(self, key: str, *, declared_content_type: str | None) -> str:
        """Sniff bytes independently from filename and reject MIME mismatches."""
        path = self.safe_path(key)
        with path.open("rb") as source:
            header = source.read(32)
        detected: str | None = None
        for magic, content_types in MAGIC_CONTENT_TYPES.items():
            if header.startswith(magic):
                detected = next(iter(content_types))
                break
        if len(header) >= 12 and header[4:8] == b"ftyp":
            detected = "video/quicktime" if header[8:12] == b"qt  " else "video/mp4"
        if declared_content_type in {"application/json"}:
            try:
                import json
                json.loads(path.read_text(encoding="utf-8"))
                detected = "application/json"
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("Invalid JSON agriculture artifact") from exc
        if declared_content_type and declared_content_type != "application/octet-stream" and detected != declared_content_type:
            compatible = {declared_content_type, detected} <= {"video/mp4", "video/quicktime"}
            if not compatible:
                raise ValueError("Agriculture media MIME does not match file content")
        return detected or "application/octet-stream"

    def usage_bytes(self, prefix: str) -> int:
        self.validate_key(prefix)
        path = self.safe_path(prefix)
        if not path.exists():
            return 0
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    def checksum(self, key: str) -> str:
        digest = hashlib.sha256()
        with self.safe_path(key).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def size(self, key: str) -> int:
        return self.safe_path(key).stat().st_size

    def write_chunk(self, key: str, data: bytes, *, offset: int) -> int:
        """Write one ordered chunk and return the new durable byte offset."""
        if offset < 0:
            raise ValueError("Upload offset cannot be negative")
        path = self.safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.stat().st_size if path.exists() else 0
        if offset != current:
            raise ValueError(f"Upload offset mismatch: expected {current}, got {offset}")
        with path.open("ab") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        return current + len(data)

    def write_object(self, key: str, data: bytes, *, expected_checksum: str) -> int:
        self.validate_key(key)
        if hashlib.sha256(data).hexdigest() != expected_checksum:
            raise ValueError("Agriculture object checksum mismatch")
        path = self.safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        with temporary.open("wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(path)
        return len(data)

    def read_range(self, key: str, *, offset: int, length: int) -> bytes:
        with self.safe_path(key).open("rb") as source:
            source.seek(offset)
            return source.read(length)

    def move(self, source_key: str, target_key: str) -> None:
        source = self.safe_path(source_key)
        target = self.safe_path(target_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)

    def backup(self, key: str, *, backup_key: str) -> str:
        source = self.safe_path(key)
        target = self.safe_path(backup_key)
        if not source.is_file():
            raise FileNotFoundError(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if self.checksum(key) != self.checksum(backup_key):
            target.unlink(missing_ok=True)
            raise IOError("Agriculture backup checksum verification failed")
        return backup_key

    def restore(self, backup_key: str, *, target_key: str, expected_checksum: str) -> str:
        if self.checksum(backup_key) != expected_checksum:
            raise ValueError("Agriculture backup checksum mismatch")
        source = self.safe_path(backup_key)
        target = self.safe_path(target_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".restore")
        shutil.copy2(source, temporary)
        temporary.replace(target)
        if self.checksum(target_key) != expected_checksum:
            raise IOError("Agriculture restore verification failed")
        return target_key

    def delete(self, key: str) -> bool:
        path = self.safe_path(key)
        if not path.is_file():
            return False
        path.unlink()
        parent = path.parent
        while parent != self.root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return True

    def exists(self, key: str) -> bool:
        return self.safe_path(key).is_file()

    def health(self) -> tuple[bool, int | None]:
        return self.root.is_dir(), shutil.disk_usage(self.root).free if self.root.is_dir() else 0

    def scan_file(self, key: str) -> dict[str, str]:
        """Deterministic safety gate; deployments may add ClamAV externally."""
        with self.safe_path(key).open("rb") as source:
            data = source.read()
        return _scan_bytes(data)

    @staticmethod
    def is_expired(created_at: datetime, *, retention_days: int, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
        return created + timedelta(days=max(1, retention_days)) <= current

    def sign(self, key: str, *, expires_in: int = 900) -> str:
        self.validate_key(key)
        expires = int(time.time()) + max(30, min(expires_in, 86_400))
        payload = f"{key}:{expires}".encode()
        secret = str(settings.jwt_secret).encode()
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return f"/agriculture/assets?{urlencode({'key': key, 'expires': expires, 'signature': signature})}"

    def verify(self, key: str, expires: int, signature: str) -> Path:
        if expires < int(time.time()):
            raise ValueError("Signed agriculture asset URL expired")
        expected = hmac.new(str(settings.jwt_secret).encode(), f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid agriculture asset signature")
        path = self.safe_path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path


class S3AgricultureStorage:
    """Small adapter over an injected boto-compatible client.

    The application keeps the same storage port for local development and S3/MinIO;
    credentials/client construction stays in deployment configuration.
    """

    def __init__(self, client, *, bucket: str, staging_root: str | Path, prefix: str = "agriculture", sse_algorithm: str = "AES256", require_tls: bool = True) -> None:
        self.client = client
        self.bucket = bucket
        self.root = Path(staging_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix.strip("/")
        self.sse_algorithm = sse_algorithm
        self.require_tls = require_tls

    def validate_key(self, key: str) -> None:
        if not key or ".." in Path(key).parts or key.startswith("/"):
            raise ValueError("Invalid agriculture storage key")

    def safe_path(self, key: str) -> Path:
        self.validate_key(key)
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Storage key escapes agriculture staging root")
        return candidate

    def validate_tenant_key(self, key: str, *, org_id: int | None, resource: str) -> None:
        self.validate_key(key)
        tenant = str(org_id) if org_id is not None else "public"
        if not key.startswith(f"org/{tenant}/{resource.strip('/')}/"):
            raise ValueError("Agriculture storage key must use the organization/resource prefix")

    def sign(self, key: str, *, expires_in: int = 900) -> str:
        self.validate_key(key)
        expires = int(time.time()) + max(30, min(expires_in, 86_400))
        signature = hmac.new(str(settings.jwt_secret).encode(), f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()
        return f"/agriculture/assets?{urlencode({'key': key, 'expires': expires, 'signature': signature})}"

    def _object_key(self, key: str) -> str:
        self.validate_key(key)
        return f"{self.prefix}/{key}"

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._object_key(key))
            return True
        except Exception as exc:
            if exc.__class__.__name__ in {"ClientError", "NoSuchKey"}:
                return False
            raise

    def health(self) -> tuple[bool, int | None]:
        self.client.head_bucket(Bucket=self.bucket)
        return True, None

    def usage_bytes(self, prefix: str) -> int:
        self.validate_key(prefix)
        total = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._object_key(prefix)):
            total += sum(int(item.get("Size", 0)) for item in page.get("Contents", []))
        return total

    def write_chunk(self, key: str, data: bytes, *, offset: int) -> int:
        path = self.safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.stat().st_size if path.exists() else 0
        if offset != current:
            raise ValueError(f"Upload offset mismatch: expected {current}, got {offset}")
        with path.open("ab") as target:
            target.write(data); target.flush(); os.fsync(target.fileno())
        return current + len(data)

    def read_range(self, key: str, *, offset: int, length: int) -> bytes:
        with self.safe_path(key).open("rb") as source:
            source.seek(offset)
            return source.read(length)

    def checksum(self, key: str) -> str:
        digest = hashlib.sha256()
        with self.safe_path(key).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def size(self, key: str) -> int:
        return self.safe_path(key).stat().st_size

    def validate_file_content(self, key: str, *, declared_content_type: str | None) -> str:
        return AgricultureStorage.validate_file_content(self, key, declared_content_type=declared_content_type)

    def validate_content(self, *, content_type: str | None, byte_size: int | None, quota_bytes: int | None = None) -> None:
        return AgricultureStorage.validate_content(self, content_type=content_type, byte_size=byte_size, quota_bytes=quota_bytes)

    def scan_file(self, key: str) -> dict[str, str]:
        with self.safe_path(key).open("rb") as source:
            data = source.read()
        return _scan_bytes(data)

    def move(self, source_key: str, target_key: str) -> None:
        source = self.safe_path(source_key)
        if not source.is_file():
            raise FileNotFoundError(source_key)
        self.put_file(target_key, source, content_type="application/octet-stream", checksum=self.checksum(source_key))
        source.unlink(missing_ok=True)

    def put_file(self, key: str, source: Path, *, content_type: str, checksum: str) -> None:
        self.validate_key(key)
        if hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
            raise ValueError("Agriculture object checksum mismatch")
        with source.open("rb") as body:
            self.client.put_object(Bucket=self.bucket, Key=self._object_key(key), Body=body, ContentType=content_type, ServerSideEncryption=self.sse_algorithm, Metadata={"sha256": checksum})

    def write_object(self, key: str, data: bytes, *, expected_checksum: str) -> int:
        self.validate_key(key)
        if hashlib.sha256(data).hexdigest() != expected_checksum:
            raise ValueError("Agriculture object checksum mismatch")
        self.client.put_object(Bucket=self.bucket, Key=self._object_key(key), Body=data, ContentType="application/octet-stream", ServerSideEncryption=self.sse_algorithm, Metadata={"sha256": expected_checksum})
        return len(data)

    def backup(self, key: str, *, backup_key: str) -> str:
        self.validate_key(key); self.validate_key(backup_key)
        self.client.copy_object(Bucket=self.bucket, CopySource={"Bucket": self.bucket, "Key": self._object_key(key)}, Key=self._object_key(backup_key), ServerSideEncryption=self.sse_algorithm)
        source = self.client.head_object(Bucket=self.bucket, Key=self._object_key(key))
        target = self.client.head_object(Bucket=self.bucket, Key=self._object_key(backup_key))
        expected = str((source.get("Metadata") or {}).get("sha256", ""))
        actual = str((target.get("Metadata") or {}).get("sha256", ""))
        if expected and actual and expected != actual:
            self.client.delete_object(Bucket=self.bucket, Key=self._object_key(backup_key))
            raise IOError("Agriculture backup checksum verification failed")
        return backup_key

    def restore(self, backup_key: str, *, target_key: str, expected_checksum: str) -> str:
        self.validate_key(backup_key); self.validate_key(target_key)
        response = self.client.get_object(Bucket=self.bucket, Key=self._object_key(backup_key))
        data = response["Body"].read()
        if hashlib.sha256(data).hexdigest() != expected_checksum:
            raise ValueError("Agriculture backup checksum mismatch")
        self.write_object(target_key, data, expected_checksum=expected_checksum)
        return target_key

    def put(self, key: str, data: bytes, *, content_type: str, checksum: str) -> None:
        self.validate_key(key)
        actual = hashlib.sha256(data).hexdigest()
        if actual != checksum:
            raise ValueError("Agriculture object checksum mismatch")
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"{self.prefix}/{key}",
            Body=data,
            ContentType=content_type,
            ServerSideEncryption=self.sse_algorithm,
            Metadata={"sha256": checksum},
        )

    def verify(self, key: str, expires: int, signature: str) -> str:
        if expires < int(time.time()):
            raise ValueError("Signed agriculture asset URL expired")
        expected = hmac.new(str(settings.jwt_secret).encode(), f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid agriculture asset signature")
        if not self.exists(key):
            raise FileNotFoundError(key)
        url = self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self._object_key(key)}, ExpiresIn=max(30, min(expires - int(time.time()), 86_400)))
        if self.require_tls and not str(url).startswith("https://"):
            raise ValueError("Agriculture object storage signed URLs require TLS")
        return url

    def configure_lifecycle(self, *, retention_days: int, backup_prefix: str) -> None:
        self.client.put_bucket_lifecycle_configuration(
            Bucket=self.bucket,
            LifecycleConfiguration={"Rules": [{
                "ID": "agriculture-retention",
                "Status": "Enabled",
                "Filter": {"Prefix": f"{self.prefix}/org/"},
                "Expiration": {"Days": max(1, retention_days)},
                "NoncurrentVersionExpiration": {"NoncurrentDays": max(1, retention_days)},
            }]},
        )
        self.client.put_bucket_versioning(Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"})

    def delete(self, key: str) -> bool:
        self.validate_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=f"{self.prefix}/{key}")
        self.safe_path(key).unlink(missing_ok=True)
        return True


def _build_storage() -> AgricultureStorage | S3AgricultureStorage:
    if str(getattr(settings, "storage_backend", "local")).lower() == "s3":
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("S3 agriculture storage requires boto3 in the production image") from exc
        client = boto3.client("s3", endpoint_url=settings.s3_endpoint_url or None, aws_access_key_id=settings.s3_access_key, aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region)
        return S3AgricultureStorage(client, bucket=settings.s3_bucket_name, staging_root="backend/storage/agriculture-staging", prefix="agriculture", sse_algorithm=settings.agriculture_storage_sse_algorithm, require_tls=str(settings.app_env).lower() in {"prod", "production", "staging"})
    return AgricultureStorage()


agriculture_storage = _build_storage()
