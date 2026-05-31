from __future__ import annotations

from backend.core.errors.handlers import _safe_http_message


def test_safe_http_message_preserves_503_readiness_detail() -> None:
    message, details = _safe_http_message(
        503,
        {
            "message": "Warehouse mapping stack is not ready for preflight.",
            "missing_required_topics": ["rgb_image"],
            "suggested_actions": ["Run scripts/check_warehouse_ros_health.sh"],
        },
    )
    assert message == "Warehouse mapping stack is not ready for preflight."
    assert details["missing_required_topics"] == ["rgb_image"]
    assert "check_warehouse_ros_health" in details["suggested_actions"][0]


def test_safe_http_message_hides_500_internals() -> None:
    message, details = _safe_http_message(500, {"message": "db exploded", "trace": "secret"})
    assert message == "Internal server error"
    assert details == {}
