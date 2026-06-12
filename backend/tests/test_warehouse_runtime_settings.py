from backend.core.config.runtime import settings


def test_warehouse_live_map_clock_settings_exist() -> None:
    assert hasattr(settings, "warehouse_live_map_clock_stability_s")
    assert settings.warehouse_live_map_clock_stability_s > 0
    assert hasattr(settings, "warehouse_mapping_stack_preflight_clock_s")
    assert settings.warehouse_mapping_stack_preflight_clock_s > 0


def test_mission_runtime_allows_idempotent_failed_state() -> None:
    from backend.modules.missions.domain.state_machine import validate_transition

    assert validate_transition("failed", "failed") is False
