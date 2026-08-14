from __future__ import annotations

import asyncio


def _is_benign_shutdown_exit_code(code: int | None) -> bool:
    if code is None:
        return False
    return code in (0, -2, -15, 130, 143)


def _is_benign_shutdown_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return True
    message = str(exc).lower()
    if "externalshutdownexception" in message:
        return True
    for code in (-15, 143, 130, -2):
        if f"code {code}" in message:
            return True
    return False
