"""Export the versioned agriculture OpenAPI surface for contract review.

Usage from the repository root:
    python backend/scripts/export_agriculture_contract.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/agriculture-openapi.json"
sys.path.insert(0, str(ROOT))

from backend.entrypoints.api.app import app


def agriculture_contract() -> dict[str, object]:
    openapi = app.openapi()
    paths = {
        path: methods
        for path, methods in openapi["paths"].items()
        if path.startswith("/agriculture/")
    }
    return {
        "schema_version": "agriculture.v1",
        "openapi": openapi["openapi"],
        "info": {
            "title": openapi["info"]["title"],
            "version": openapi["info"]["version"],
        },
        "paths": paths,
        "components": openapi.get("components", {}),
    }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(agriculture_contract(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT}")
