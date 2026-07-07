from __future__ import annotations

import re

_UNSAFE_TOKEN_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_token(raw: object, *, fallback: str = "unknown") -> str:
    token = _UNSAFE_TOKEN_CHARS.sub("_", str(raw or "")).strip("._-")
    return token or fallback
