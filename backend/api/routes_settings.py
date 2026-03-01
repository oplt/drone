from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from backend.schemas.settings import SettingsDoc
from backend.utils.config_runtime import get_runtime_settings
from backend.db.repository import SettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])

svc = SettingsRepository()

UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "runtime_uploads"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_UPLOADS: dict[tuple[str, str], set[str]] = {
    ("telemetry", "mqtt_ca_certs"): {".pem", ".crt", ".ca"},
    ("telemetry", "opcua_cert_path"): {".pem", ".crt", ".cert"},
    ("telemetry", "opcua_key_path"): {".pem", ".key"},
    ("raspberry", "ssh_key_path"): {".pem", ".key", ".pub"},
}


@router.get("", response_model=SettingsDoc)
async def get_settings():
    return await svc.get_settings_doc()


@router.put("", response_model=SettingsDoc)
async def put_settings(payload: SettingsDoc, request: Request):
    saved = await svc.put_settings_doc(payload.model_dump())

    # Refresh runtime settings for this process
    request.app.state.settings_doc = await svc.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(svc)

    return saved


@router.post("/upload")
async def upload_settings_file(
    section: str = Form(...),
    field: str = Form(...),
    file: UploadFile = File(...),
):
    key = (section, field)
    allowed = ALLOWED_UPLOADS.get(key)
    if not allowed:
        raise HTTPException(status_code=400, detail="Unsupported settings upload field.")

    suffix = Path(file.filename or "").suffix.lower()
    if not suffix or suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension for {section}.{field}.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large.")

    target_dir = UPLOAD_ROOT / section / field
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{int(time.time())}-{secrets.token_hex(8)}{suffix}"
    target_path.write_bytes(payload)
    os.chmod(target_path, 0o600)

    return {"path": str(target_path.resolve())}
