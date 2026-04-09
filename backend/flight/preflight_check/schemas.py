from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class CheckResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    name: str
    status: CheckStatus
    message: str | None = None


class PreflightReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    mission_type: str
    overall_status: CheckStatus
    base_checks: list[CheckResult]
    mission_checks: list[CheckResult]
    summary: dict[str, Any] | None = None
    timestamp: float | None = None
    vehicle_id: str | None = None
    quick_check: bool | None = False
    critical_failures: list[CheckResult] | None = None
    mission_checks_skipped: bool | None = False
