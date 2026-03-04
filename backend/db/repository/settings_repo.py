from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from ..models import SettingsRow, VaultSecret
import logging
from ..session import Session
from backend.utils.vault import Vault


logger = logging.getLogger(__name__)



MASK = "********"


# Vault keys (names stored in VaultSecret.name)
V_TELEM_MQTT_PASS = "telemetry.mqtt_pass"
V_AI_LLM_KEY = "ai.llm_api_key"
V_PI_PASS = "raspberry.raspberry_password"
V_PHOTO_WEBODM_API_TOKEN = "photogrammetry.WEBODM_API_TOKEN"
V_PHOTO_ASSET_SIGNING_SECRET = "photogrammetry.PHOTOGRAMMETRY_ASSET_SIGNING_SECRET"

SECRET_PATHS = {
    V_TELEM_MQTT_PASS: ("telemetry", "mqtt_pass"),
    V_AI_LLM_KEY: ("ai", "llm_api_key"),
    V_PI_PASS: ("raspberry", "raspberry_password"),
    V_PHOTO_WEBODM_API_TOKEN: ("photogrammetry", "WEBODM_API_TOKEN"),
    V_PHOTO_ASSET_SIGNING_SECRET: (
        "photogrammetry",
        "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET",
    ),
}


def _ensure_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base (dict-dict recursively)."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_path(d: Dict[str, Any], path: tuple[str, str], value: Any) -> None:
    a, b = path
    d.setdefault(a, {})
    if isinstance(d[a], dict):
        d[a][b] = value


def _pop_path(d: Dict[str, Any], path: tuple[str, str]) -> Optional[Any]:
    a, b = path
    if not isinstance(d.get(a), dict):
        return None
    return d[a].pop(b, None)


class SettingsRepository:
    def __init__(self) -> None:
        self._session_factory = Session
        self._vault = Vault()

    async def _read_row(self) -> tuple[Dict[str, Any], Optional[str]]:
        async with self._session_factory() as db:
            res = await db.execute(select(SettingsRow).where(SettingsRow.id == 1))
            row = res.scalar_one_or_none()
            data = (row.data if row else {}) or {}
            updated_at = row.updated_at.isoformat() if row and getattr(row, "updated_at", None) else None
            return dict(data), updated_at

    async def _read_secret_names(self) -> set[str]:
        async with self._session_factory() as db:
            sec = await db.execute(select(VaultSecret.name))
            return {r[0] for r in sec.all()}

    async def get_settings_doc(self) -> Dict[str, Any]:
        """
        Public (UI) shape:
        - returns SettingsDoc-compatible dict
        - secrets are masked if present in vault
        """
        data, updated_at = await self._read_row()

        # Ensure top-level sections exist so UI doesn't crash on undefined access
        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
                "photogrammetry": {},
            },
            data,
        )

        sec_names = await self._read_secret_names()
        for secret_name, path in SECRET_PATHS.items():
            if secret_name in sec_names:
                _set_path(data, path, MASK)

        if updated_at:
            data["updated_at"] = updated_at

        return data

    async def put_settings_doc(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        """
        - Upsert non-secret settings JSON into SettingsRow(id=1)
        - If incoming contains a non-masked secret, encrypt+store it in VaultSecret
        - Never stores plaintext secrets in SettingsRow.data
        - Returns saved doc with masked secrets
        """
        # Normalize and ensure sections exist
        data = _ensure_dict(incoming)

        # updated_at should be DB-derived, not stored
        data.pop("updated_at", None)

        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
                "photogrammetry": {},
            },
            data,
        )

        # --- extract + store secrets (then remove from JSON) ---
        mqtt_pass = _pop_path(data, SECRET_PATHS[V_TELEM_MQTT_PASS])
        llm_key = _pop_path(data, SECRET_PATHS[V_AI_LLM_KEY])
        pi_pass = _pop_path(data, SECRET_PATHS[V_PI_PASS])
        webodm_api_token = _pop_path(data, SECRET_PATHS[V_PHOTO_WEBODM_API_TOKEN])
        asset_signing_secret = _pop_path(data, SECRET_PATHS[V_PHOTO_ASSET_SIGNING_SECRET])

        async with self._session_factory() as db:

            async def upsert_secret(name: str, value: Optional[str]) -> None:
                if value is None:
                    return
                raw = str(value)
                if raw == MASK:
                    return
                if not raw.strip():
                    await db.execute(delete(VaultSecret).where(VaultSecret.name == name))
                    return
                ct = self._vault.encrypt(raw)
                stmt = (
                    pg_insert(VaultSecret)
                    .values(name=name, ciphertext=ct)
                    .on_conflict_do_update(
                        index_elements=[VaultSecret.name],
                        set_={"ciphertext": ct},
                    )
                )
                await db.execute(stmt)

            await upsert_secret(V_TELEM_MQTT_PASS, mqtt_pass)
            await upsert_secret(V_AI_LLM_KEY, llm_key)
            await upsert_secret(V_PI_PASS, pi_pass)
            await upsert_secret(V_PHOTO_WEBODM_API_TOKEN, webodm_api_token)
            await upsert_secret(V_PHOTO_ASSET_SIGNING_SECRET, asset_signing_secret)

            # --- upsert non-secret JSON ---
            stmt = (
                pg_insert(SettingsRow)
                .values(id=1, data=data)
                .on_conflict_do_update(
                    index_elements=[SettingsRow.id],
                    set_={"data": data},
                )
            )
            await db.execute(stmt)
            await db.commit()

        return await self.get_settings_doc()

    async def get_effective_settings_doc(self) -> Dict[str, Any]:
        """
        Internal runtime shape:
        - returns SettingsDoc-compatible dict
        - secrets are decrypted and injected into the SAME nested paths the UI uses
        """
        data, updated_at = await self._read_row()

        data = _deep_merge(
            {
                "telemetry": {},
                "ai": {},
                "credentials": {},
                "hardware": {},
                "preflight": {},
                "raspberry": {},
                "camera": {},
                "photogrammetry": {},
            },
            data,
        )

        async with self._session_factory() as db:
            sec_res = await db.execute(select(VaultSecret))
            secrets = {s.name: s.ciphertext for s in sec_res.scalars().all()}

        def dec(name: str) -> str:
            ct = secrets.get(name)
            if not ct:
                return ""
            raw = self._vault.decrypt(ct)
            # Vault.decrypt may already return bytes or str depending on your impl
            return raw.decode("utf-8") if hasattr(raw, "decode") else str(raw)

        for secret_name, path in SECRET_PATHS.items():
            _set_path(data, path, dec(secret_name))

        if updated_at:
            data["updated_at"] = updated_at

        return data
