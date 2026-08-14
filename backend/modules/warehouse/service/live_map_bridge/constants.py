"""Warehouse live-map bridge — regex and field constants."""

from __future__ import annotations

import re

_POSITION_RE = re.compile(
    r"position:\s*\n\s*x:\s*([-+0-9.eE]+)\s*\n\s*y:\s*([-+0-9.eE]+)\s*\n\s*z:\s*([-+0-9.eE]+)",
    re.MULTILINE,
)
_YAW_RE = re.compile(
    r"orientation:\s*\n\s*x:\s*([-+0-9.eE]+)\s*\n\s*y:\s*([-+0-9.eE]+)\s*\n\s*z:\s*([-+0-9.eE]+)\s*\n\s*w:\s*([-+0-9.eE]+)",
    re.MULTILINE,
)

_POINTFIELD_DATATYPE_SIZE: dict[int, int] = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 4,
    6: 4,
    7: 4,
    8: 8,
}

__all__ = ["_POINTFIELD_DATATYPE_SIZE", "_POSITION_RE", "_YAW_RE"]
