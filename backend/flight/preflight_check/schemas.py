from enum import Enum
from typing import List, Optional, Dict, Any
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
    message: Optional[str] = None


class PreflightReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    mission_type: str
    overall_status: CheckStatus
    base_checks: List[CheckResult]
    mission_checks: List[CheckResult]
    summary: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    vehicle_id: Optional[str] = None
    quick_check: Optional[bool] = False
    critical_failures: Optional[List[CheckResult]] = None
    mission_checks_skipped: Optional[bool] = False