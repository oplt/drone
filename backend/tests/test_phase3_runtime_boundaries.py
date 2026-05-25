import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "modules" / "vehicle_runtime"
FORBIDDEN_RUNTIME_ADAPTER_IMPORTS = (
    "backend.infrastructure.maps",
    "backend.infrastructure.messaging",
    "backend.infrastructure.camera",
    "backend.infrastructure.storage",
    "pymavlink",
)


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_runtime_services_depend_on_ports_not_concrete_adapters() -> None:
    service_files = [
        path for path in RUNTIME_ROOT.glob("*.py") if path.name not in {"__init__.py", "ports.py"}
    ]
    violations: list[str] = []
    for path in service_files:
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_RUNTIME_ADAPTER_IMPORTS):
                violations.append(f"{path.name}: {module}")
    assert not violations, "\n".join(violations)


def test_orchestrator_compatibility_module_is_only_a_facade() -> None:
    assert not (ROOT / "drone" / "orchestrator.py").exists()


def test_photogrammetry_workflow_receives_external_adapters() -> None:
    service_imports = imported_modules(ROOT / "modules" / "mapping" / "service" / "workflow.py")
    assert "backend.infrastructure.photogrammetry.webodm_client" not in service_imports
    assert "backend.infrastructure.photogrammetry.storage" not in service_imports
    assert "backend.infrastructure.photogrammetry.ingest" not in service_imports


def test_object_storage_legacy_path_is_only_a_facade() -> None:
    assert not (ROOT / "services" / "storage" / "s3_client.py").exists()
