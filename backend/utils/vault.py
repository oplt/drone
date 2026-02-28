from __future__ import annotations

import base64
import os
from typing import Optional
from backend.config import settings as config

from cryptography.fernet import Fernet, InvalidToken


class Vault:
    """
    Minimal vault:
    - Master key from env: SETTINGS_VAULT_KEY (Fernet key)
    - Encrypt/decrypt secrets stored in DB
    """

    def __init__(self, key: Optional[str] = None) -> None:
        key = config.settings_vault_key
        if not key:
            raise RuntimeError("Missing SETTINGS_VAULT_KEY environment variable (Fernet key).")

        # Accept raw 32-byte base64 fernet key
        self._fernet = Fernet(key.encode("utf-8"))

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("utf-8")

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            raise RuntimeError("Vault decrypt failed (invalid token / wrong key).") from e