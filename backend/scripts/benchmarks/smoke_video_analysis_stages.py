from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--stage-timings", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("version") != 1:
        raise SystemExit("Unsupported manifest version")
    timings = (
        json.loads(args.stage_timings.read_text()) if args.stage_timings else {}
    )
    expected = manifest["expected_stage_keys"]
    report = {
        "manifest": manifest["name"],
        "stages": {
            stage: float(timings.get(stage, 0.0))
            for stage in expected
        },
        "missing": [stage for stage in expected if stage not in timings],
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
