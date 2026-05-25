from __future__ import annotations

import ast
from pathlib import Path

PHASE2_ROUTES = (
    ("missions/api", "routes.py"),
    ("mapping", "api.py"),
    ("warehouse", "api.py"),
    ("fields", "api.py"),
    ("irrigation", "api.py"),
)
DB_METHODS = {
    "execute",
    "scalar",
    "get",
    "add",
    "flush",
    "commit",
    "refresh",
    "rollback",
    "delete",
}


def test_phase2_routes_do_not_own_persistence() -> None:
    routes_root = Path(__file__).parents[1] / "modules"
    errors: list[str] = []

    for folder, filename in PHASE2_ROUTES:
        path = routes_root / folder / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "sqlalchemy" or node.module.startswith("backend.db"):
                    errors.append(f"{filename}:{node.lineno} imports {node.module}")
                if ".repository" in node.module:
                    errors.append(f"{filename}:{node.lineno} imports repository {node.module}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "db"
                and node.func.attr in DB_METHODS
            ):
                errors.append(f"{filename}:{node.lineno} calls db.{node.func.attr}()")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Session"
            ):
                errors.append(f"{filename}:{node.lineno} constructs Session()")

    assert not errors, "\n".join(errors)
