from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from backend.modules.warehouse.service.map_source_config import NVBLOX_OUTPUT_TOPICS

NvbloxStatus = Literal["off", "warming", "live", "degraded", "error"]

_LIVE_TOPICS = (
    "/nvblox_node/static_esdf_pointcloud",
    "/nvblox_node/mesh",
)

_STALE_AFTER_S = 3.0
_TF_DEGRADED_THRESHOLD = 3


@dataclass
class NvbloxStatusTracker:
    process_running: bool = False
    topics_present: set[str] = field(default_factory=set)
    last_message_at: dict[str, float] = field(default_factory=dict)
    last_error: str | None = None
    tf_depth_failure: bool = False
    tf_old_data_count: int = 0
    tf_jump_back_count: int = 0
    tf_lookup_failed_count: int = 0
    tf_authority_issues: int = 0
    last_tf_issue_at: float | None = None

    def note_topic_list(self, topics: set[str] | list[str]) -> None:
        normalized = {str(topic) for topic in topics}
        self.topics_present = {
            topic for topic in normalized if topic.startswith("/nvblox_node/")
        }

    def note_message(self, topic: str) -> None:
        self.last_message_at[str(topic)] = time.monotonic()

    def note_process_running(self, running: bool) -> None:
        self.process_running = running
        if not running:
            self.last_error = self.last_error or "nvblox process not running"

    def note_error(self, message: str) -> None:
        self.last_error = message

    def note_tf_depth_failure(self, failed: bool) -> None:
        self.tf_depth_failure = failed
        if failed:
            self.last_tf_issue_at = time.monotonic()

    def note_tf_old_data(self) -> None:
        self.tf_old_data_count += 1
        self.tf_depth_failure = True
        self.last_tf_issue_at = time.monotonic()

    def note_tf_jump_back(self) -> None:
        self.tf_jump_back_count += 1
        self.tf_depth_failure = True
        self.last_tf_issue_at = time.monotonic()

    def note_tf_lookup_failed(self) -> None:
        self.tf_lookup_failed_count += 1
        self.tf_depth_failure = True
        self.last_tf_issue_at = time.monotonic()

    def note_tf_authority_issue(self) -> None:
        self.tf_authority_issues += 1
        self.tf_depth_failure = True
        self.last_tf_issue_at = time.monotonic()

    def reset_tf_counters(self) -> None:
        self.tf_old_data_count = 0
        self.tf_jump_back_count = 0
        self.tf_lookup_failed_count = 0
        self.tf_authority_issues = 0
        self.tf_depth_failure = False
        self.last_tf_issue_at = None

    def tf_degraded(self) -> bool:
        return (
            self.tf_depth_failure
            or self.tf_jump_back_count >= _TF_DEGRADED_THRESHOLD
            or self.tf_old_data_count >= _TF_DEGRADED_THRESHOLD * 5
        )

    def status(self) -> NvbloxStatus:
        if self.tf_degraded() and self.process_running:
            return "degraded"
        if self.last_error and not self.process_running:
            return "error"
        if self.tf_depth_failure and not self.process_running:
            return "error"

        nvblox_topics = self.topics_present or {
            topic for topic in self.last_message_at if topic.startswith("/nvblox_node/")
        }
        if not nvblox_topics and not self.process_running:
            return "off"

        now = time.monotonic()
        live_hits = [
            topic
            for topic in _LIVE_TOPICS
            if topic in self.last_message_at
            and (now - self.last_message_at[topic]) <= _STALE_AFTER_S
        ]
        if live_hits and not self.tf_degraded():
            return "live"

        any_recent = any(
            (now - ts) <= _STALE_AFTER_S for ts in self.last_message_at.values()
        )
        if any_recent:
            return "degraded"

        if nvblox_topics or self.process_running:
            return "warming"

        if self.last_error:
            return "error"

        return "off"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status(),
            "process_running": self.process_running,
            "topics_present": sorted(self.topics_present),
            "last_message_at": {
                topic: datetime.fromtimestamp(ts, UTC).isoformat()
                for topic, ts in self.last_message_at.items()
            },
            "last_error": self.last_error,
            "tf_depth_failure": self.tf_depth_failure,
            "tf_degraded": self.tf_degraded(),
            "tf_old_data_count": self.tf_old_data_count,
            "tf_jump_back_count": self.tf_jump_back_count,
            "tf_lookup_failed_count": self.tf_lookup_failed_count,
            "tf_authority_issues": self.tf_authority_issues,
            "last_tf_issue_at": (
                datetime.fromtimestamp(self.last_tf_issue_at, UTC).isoformat()
                if self.last_tf_issue_at is not None
                else None
            ),
            "monitored_topics": list(NVBLOX_OUTPUT_TOPICS),
        }


nvblox_status_tracker = NvbloxStatusTracker()
