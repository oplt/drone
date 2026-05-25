from __future__ import annotations

import ast
from pathlib import Path

from backend.modules.alerts.models import AlertDelivery
from backend.modules.automation.models import OutboxEvent
from backend.modules.deliverables.rendering import render_deliverable
from backend.modules.integrations.webhooks.models import WebhookDelivery

ROOT = Path(__file__).resolve().parents[1]
THIN_TASKS = (
    "deliverable_tasks.py",
    "export_tasks.py",
    "photogrammetry_tasks.py",
    "webhook_tasks.py",
    "outbox_tasks.py",
    "scheduling_tasks.py",
)


def imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_async_task_adapters_do_not_own_persistence_workflows() -> None:
    violations: list[str] = []
    for filename in THIN_TASKS:
        modules = imports_for(ROOT / "entrypoints" / "workers" / filename)
        for module in modules:
            if module == "sqlalchemy" or module.startswith("backend.db"):
                violations.append(f"{filename}: {module}")
    assert not violations, "\n".join(violations)


def test_notification_tables_expose_idempotency_keys() -> None:
    assert OutboxEvent.__table__.c.idempotency_key.unique is True
    assert WebhookDelivery.__table__.c.idempotency_key.unique is True
    assert AlertDelivery.__table__.c.idempotency_key.unique is True


def test_html_deliverable_escapes_field_names() -> None:
    field = type("Field", (), {"id": 1, "name": "<script>x</script>", "area_ha": 1.5})()
    rendered = render_deliverable("HTML_SUMMARY", field, None)
    assert b"<script>" not in rendered.content
    assert b"&lt;script&gt;" in rendered.content
