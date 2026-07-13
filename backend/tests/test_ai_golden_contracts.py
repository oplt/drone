from backend.modules.agents.golden_evals import run_golden_agent_contracts


def test_golden_agent_contracts() -> None:
    checks = run_golden_agent_contracts()
    failed = [check.name for check in checks if not check.passed]
    assert not failed, failed
