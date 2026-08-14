#!/usr/bin/env python3
"""Ensure P4 research NO-GO decisions stay enforced in production labels."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES_PATH = ROOT / "backend/modules/agriculture/capabilities.py"
READINESS_PATH = ROOT / "backend/modules/agriculture/readiness.json"


def main() -> int:
    capabilities_src = CAPABILITIES_PATH.read_text(encoding="utf-8")
    banned = (
        "multispectral",
        "multispectral_stress",
        "ndvi",
        "prescription",
        "prescription_zones",
        "thermal_water_stress",
    )
    for name in banned:
        if re.search(rf'AgricultureCapability\(\s*"{name}"', capabilities_src):
            raise SystemExit(f"Forbidden production capability present: {name}")

    readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    for priority in ("P1", "P2", "P3"):
        availability = readiness["priorities"][priority].get("availability")
        if availability != "research_blocked":
            raise SystemExit(f"{priority} must be research_blocked, found {availability!r}")

    sys.path.insert(0, str(ROOT))
    from backend.modules.agriculture.inference_profiles import (  # noqa: PLC0415
        CAPABILITY_PROFILE_IDS,
        PROFILE_SCHEMA_VERSION,
        default_inference_profile,
    )

    for capability_id in CAPABILITY_PROFILE_IDS:
        profile = default_inference_profile(capability_id)
        if profile["profile_version"] != PROFILE_SCHEMA_VERSION:
            raise SystemExit(f"{capability_id} must use the current profile schema")
        if profile["sahi_enabled"] or profile["tracking_enabled"]:
            raise SystemExit(
                f"{capability_id} must retain the standard EXP-002 baseline"
            )

    print("P4 research gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
