from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path
from urllib.parse import quote

from backend.config import settings


class AssetGatewayService:
    """
    Signed URL helper for mapping assets.

    Token payload binds:
    - asset id
    - user id
    - expiry (unix seconds)
    - optional asset sub-path (for directory assets like 3D Tiles)
    """

    def __init__(self) -> None:
        secret = os.getenv("PHOTOGRAMMETRY_ASSET_SIGNING_SECRET", "").strip()
        if not secret:
            secret = settings.jwt_secret
        self._secret = secret.encode("utf-8")
        self.storage_dir = Path(
            os.getenv("PHOTOGRAMMETRY_STORAGE_DIR", "backend/storage/mapping")
        ).resolve()
        self.public_base = os.getenv("PHOTOGRAMMETRY_STORAGE_BASE_URL", "/mapping-assets").rstrip(
            "/"
        )

    def _payload(self, *, asset_id: int, user_id: int, exp: int, path: str) -> bytes:
        return f"{asset_id}:{user_id}:{exp}:{path}".encode("utf-8")

    def sign(self, *, asset_id: int, user_id: int, exp: int, path: str = "") -> str:
        payload = self._payload(asset_id=asset_id, user_id=user_id, exp=exp, path=path)
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify(
        self,
        *,
        asset_id: int,
        user_id: int,
        exp: int,
        sig: str,
        path: str = "",
    ) -> bool:
        if exp < int(time.time()):
            return False
        expected = self.sign(asset_id=asset_id, user_id=user_id, exp=exp, path=path)
        return hmac.compare_digest(expected, sig)

    def build_signed_url(
        self,
        *,
        asset_id: int,
        user_id: int,
        ttl_seconds: int,
        path: str = "",
    ) -> tuple[str, int]:
        ttl = max(60, min(24 * 60 * 60, int(ttl_seconds)))
        exp = int(time.time()) + ttl
        sig = self.sign(asset_id=asset_id, user_id=user_id, exp=exp, path=path)
        qp = f"exp={exp}&sig={quote(sig)}"
        if path:
            qp += f"&path={quote(path)}"
        return f"/mapping/assets/{asset_id}/download?{qp}", exp

    def resolve_local_target(self, *, asset_url: str, asset_type: str, path: str = "") -> Path | None:
        """
        Resolve asset URL to a local file path when asset is served from local mapping storage.
        """
        if not asset_url.startswith(f"{self.public_base}/"):
            return None

        rel = asset_url[len(self.public_base) + 1 :]
        root = (self.storage_dir / rel).resolve()
        if not root.exists():
            return None

        if root.is_file():
            if path:
                return None
            return root

        if root.is_dir():
            effective_path = path.strip().lstrip("/")
            if not effective_path:
                if asset_type == "TILESET_3D":
                    effective_path = "tileset.json"
                else:
                    return None
            target = (root / effective_path).resolve()
            if not str(target).startswith(str(root)):
                return None
            if not target.exists() or not target.is_file():
                return None
            return target

        return None
