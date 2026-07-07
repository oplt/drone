from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
_warned_missing_startup_timing = False


def _warn_once(exc: ModuleNotFoundError) -> None:
    global _warned_missing_startup_timing
    if not _warned_missing_startup_timing:
        logger.warning("Optional mapping startup timing unavailable: %s", exc)
        _warned_missing_startup_timing = True


def begin_mapping_startup_safe(*, mission_start_monotonic: float) -> None:
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            begin_mapping_startup_timing,
        )

        begin_mapping_startup_timing(mission_start_monotonic=mission_start_monotonic)
    except ModuleNotFoundError as exc:
        _warn_once(exc)
    except Exception:
        logger.debug("Could not begin mapping startup timing", exc_info=True)


def note_mapping_startup_safe(mark: str) -> None:
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import note_mapping_startup

        note_mapping_startup(mark)
    except ModuleNotFoundError as exc:
        _warn_once(exc)
    except Exception:
        logger.debug("Could not record mapping startup mark=%s", mark, exc_info=True)


def active_mapping_startup_timing_safe():
    try:
        from backend.modules.warehouse.service.mapping_startup_timing import (
            active_mapping_startup_timing,
        )

        return active_mapping_startup_timing()
    except ModuleNotFoundError as exc:
        _warn_once(exc)
    except Exception:
        logger.debug("Could not read active mapping startup timing", exc_info=True)
    return None
