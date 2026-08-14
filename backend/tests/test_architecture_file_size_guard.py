from __future__ import annotations

import json
from pathlib import Path

from backend.scripts.check_file_sizes import (
    BASELINE_PATH,
    collect_violations,
    evaluate_against_baseline,
    limit_for,
    prune_baseline,
    should_skip,
)


def test_should_skip_alembic_and_tests() -> None:
    assert should_skip("backend/infrastructure/persistence/alembic/versions/abc_revision.py")
    assert should_skip("backend/tests/test_example.py")
    assert not should_skip("backend/modules/patrol/planning/perimeter.py")


def test_evaluate_against_baseline_flags_regression_and_stale() -> None:
    current = {
        "backend/modules/example/service.py": {"effective_lines": 500, "limit": 400},
        "backend/modules/other/service.py": {"effective_lines": 450, "limit": 400},
    }
    baseline = {
        "backend/modules/example/service.py": {"effective_lines": 480, "limit": 400},
        "backend/modules/removed/service.py": {"effective_lines": 900, "limit": 400},
    }
    regressions, stale, grandfathered = evaluate_against_baseline(current, baseline)
    assert grandfathered == 0
    assert stale == ["backend/modules/removed/service.py"]
    assert len(regressions) == 2


def test_prune_baseline_drops_resolved_entries() -> None:
    baseline = {
        "backend/modules/a/service.py": {"effective_lines": 500, "limit": 400},
        "backend/modules/b/service.py": {"effective_lines": 450, "limit": 400},
    }
    current = {"backend/modules/a/service.py": {"effective_lines": 500, "limit": 400}}
    pruned = prune_baseline(baseline, current)
    assert list(pruned) == ["backend/modules/a/service.py"]


def test_live_baseline_has_no_stale_entries() -> None:
    """Phase 0: baseline entries must be removed once a file is under its limit."""
    current = collect_violations()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    _regressions, stale, _grandfathered = evaluate_against_baseline(current, baseline)
    assert stale == [], (
        "Stale baseline entries detected; run "
        "python backend/scripts/check_file_sizes.py --prune-baseline"
    )


def test_mission_specific_not_grandfathered_when_compliant() -> None:
    path = "backend/modules/preflight/checks/mission_specific.py"
    assert path not in collect_violations()


def test_limit_for_api_and_infrastructure() -> None:
    assert limit_for("backend/modules/mapping/api/routes.py") == 220
    assert limit_for("backend/modules/telemetry/api/routes.py") == 220
    assert limit_for("backend/modules/analytics/api/routes.py") == 220
    assert limit_for("backend/infrastructure/vehicle/mavlink_client.py") == 260
