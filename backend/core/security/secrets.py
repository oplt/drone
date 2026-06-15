from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class Vault:
    """
    Minimal vault:
    - Master key from env: SETTINGS_VAULT_KEY (Fernet key)
    - Encrypt/decrypt secrets stored in DB

    The key is now loaded lazily when a Vault instance is created, avoiding
    unnecessary import-time dependency on bootstrap settings for modules that
    merely import this file.
    """

    def __init__(self, key: str | bytes | None = None) -> None:
        if key is None:
            from backend.core.config.runtime import bootstrap as config

            key = config.settings_vault_key
        if not key:
            raise RuntimeError("Missing SETTINGS_VAULT_KEY environment variable (Fernet key).")

        raw_key = key if isinstance(key, bytes) else str(key).encode("utf-8")
        try:
            self._fernet = Fernet(raw_key)
        except Exception as exc:
            raise RuntimeError("Invalid SETTINGS_VAULT_KEY; expected a Fernet key.") from exc

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("utf-8")

    def encrypt(self, plaintext: str | bytes) -> bytes:
        raw = plaintext if isinstance(plaintext, bytes) else str(plaintext).encode("utf-8")
        return self._fernet.encrypt(raw)

    def encrypt_to_str(self, plaintext: str | bytes) -> str:
        return self.encrypt(plaintext).decode("utf-8")

    def decrypt(self, ciphertext: bytes | str) -> str:
        raw = ciphertext.encode("utf-8") if isinstance(ciphertext, str) else ciphertext
        try:
            return self._fernet.decrypt(raw).decode("utf-8")
        except InvalidToken as e:
            raise RuntimeError("Vault decrypt failed (invalid token / wrong key).") from e

    def decrypt_bytes(self, ciphertext: bytes | str) -> bytes:
        raw = ciphertext.encode("utf-8") if isinstance(ciphertext, str) else ciphertext
        try:
            return self._fernet.decrypt(raw)
        except InvalidToken as e:
            raise RuntimeError("Vault decrypt failed (invalid token / wrong key).") from e
