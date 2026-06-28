from backend.modules.warehouse.service.inspection_execution_policy import (
    InspectionExecutionPolicy,
    execution_action,
)


def test_transient_blockage_replans_then_returns() -> None:
    policy = InspectionExecutionPolicy(max_replans_per_leg=2)

    assert execution_action(reason="path_blocked", replan_attempts=0, policy=policy) == "replan"
    assert (
        execution_action(reason="path_blocked", replan_attempts=2, policy=policy)
        == "return_to_dock"
    )


def test_tf_or_version_loss_aborts() -> None:
    policy = InspectionExecutionPolicy()

    assert execution_action(reason="tf_lost", replan_attempts=0, policy=policy) == "abort_land"
    assert (
        execution_action(reason="version_changed", replan_attempts=0, policy=policy) == "abort_land"
    )
