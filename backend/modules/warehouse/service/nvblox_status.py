from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from backend.modules.warehouse.service.map_source_config import NVBLOX_OUTPUT_TOPICS

NvbloxStatus = Literal["off", "warming", "live", "degraded", "error"]

_LIVE_TOPICS = (
    "/nvblox_node/static_esdf_pointcloud",
    "/nvblox_node/mesh",
    "/nvblox_node/color_layer",
)
_STALE_AFTER_S = 3.0
_TF_DEGRADED_THRESHOLD = 3
_MAX_TRACKED_MESSAGES = 256


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
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False, compare=False)

    def _prune_messages_locked(self) -> None:
        if len(self.last_message_at) <= _MAX_TRACKED_MESSAGES:
            return
        keep = sorted(self.last_message_at.items(), key=lambda item: item[1], reverse=True)[:_MAX_TRACKED_MESSAGES]
        self.last_message_at = dict(keep)

    def note_topic_list(self, topics: set[str] | list[str]) -> None:
        normalized = {str(topic) for topic in topics}
        with self._lock:
            self.topics_present = {topic for topic in normalized if topic.startswith("/nvblox_node/")}

    def note_message(self, topic: str) -> None:
        with self._lock:
            self.last_message_at[str(topic)] = time.monotonic()
            self.last_error = None if self.process_running else self.last_error
            self._prune_messages_locked()

    def note_process_running(self, running: bool) -> None:
        with self._lock:
            self.process_running = bool(running)
            if running:
                self.last_error = None
            elif not self.last_error:
                self.last_error = "nvblox process not running"

    def note_error(self, message: str) -> None:
        with self._lock:
            self.last_error = str(message)[:500]

    def note_tf_depth_failure(self, failed: bool) -> None:
        with self._lock:
            self.tf_depth_failure = bool(failed)
            if failed:
                self.last_tf_issue_at = time.monotonic()

    def note_tf_old_data(self) -> None:
        with self._lock:
            self.tf_old_data_count += 1
            self.tf_depth_failure = True
            self.last_tf_issue_at = time.monotonic()

    def note_tf_jump_back(self) -> None:
        with self._lock:
            self.tf_jump_back_count += 1
            self.tf_depth_failure = True
            self.last_tf_issue_at = time.monotonic()

    def note_tf_lookup_failed(self) -> None:
        with self._lock:
            self.tf_lookup_failed_count += 1
            self.tf_depth_failure = True
            self.last_tf_issue_at = time.monotonic()

    def note_tf_authority_issue(self) -> None:
        with self._lock:
            self.tf_authority_issues += 1
            self.tf_depth_failure = True
            self.last_tf_issue_at = time.monotonic()

    def reset_tf_counters(self) -> None:
        with self._lock:
            self.tf_old_data_count = 0
            self.tf_jump_back_count = 0
            self.tf_lookup_failed_count = 0
            self.tf_authority_issues = 0
            self.tf_depth_failure = False
            self.last_tf_issue_at = None

    def _tf_degraded_locked(self) -> bool:
        return (
            self.tf_depth_failure
            or self.tf_jump_back_count >= _TF_DEGRADED_THRESHOLD
            or self.tf_old_data_count >= _TF_DEGRADED_THRESHOLD * 5
        )

    def tf_degraded(self) -> bool:
        with self._lock:
            return self._tf_degraded_locked()

    def status(self) -> NvbloxStatus:
        with self._lock:
            tf_degraded = self._tf_degraded_locked()
            process_running = self.process_running
            last_error = self.last_error
            topics_present = set(self.topics_present)
            last_message_at = dict(self.last_message_at)
            tf_depth_failure = self.tf_depth_failure

        if tf_degraded and process_running:
            return "degraded"
        if last_error and not process_running:
            return "error"
        if tf_depth_failure and not process_running:
            return "error"

        nvblox_topics = topics_present or {topic for topic in last_message_at if topic.startswith("/nvblox_node/")}
        if not nvblox_topics and not process_running:
            return "off"

        now = time.monotonic()
        live_hits = [topic for topic in _LIVE_TOPICS if topic in last_message_at and (now - last_message_at[topic]) <= _STALE_AFTER_S]
        if live_hits and not tf_degraded:
            return "live"
        if any((now - ts) <= _STALE_AFTER_S for ts in last_message_at.values()):
            return "degraded"
        if nvblox_topics or process_running:
            return "warming"
        if last_error:
            return "error"
        return "off"

    def as_dict(self) -> dict[str, object]:
        with self._lock:
            last_message_at = dict(self.last_message_at)
            last_tf_issue_at = self.last_tf_issue_at
            payload = {
                "status": self.status(),
                "process_running": self.process_running,
                "topics_present": sorted(self.topics_present),
                "last_message_at": {
                    topic: datetime.fromtimestamp(ts, UTC).isoformat()
                    for topic, ts in last_message_at.items()
                },
                "last_error": self.last_error,
                "tf_depth_failure": self.tf_depth_failure,
                "tf_degraded": self._tf_degraded_locked(),
                "tf_old_data_count": self.tf_old_data_count,
                "tf_jump_back_count": self.tf_jump_back_count,
                "tf_lookup_failed_count": self.tf_lookup_failed_count,
                "tf_authority_issues": self.tf_authority_issues,
                "last_tf_issue_at": (
                    datetime.fromtimestamp(last_tf_issue_at, UTC).isoformat()
                    if last_tf_issue_at is not None
                    else None
                ),
                "monitored_topics": list(NVBLOX_OUTPUT_TOPICS),
            }
        return payload


nvblox_status_tracker = NvbloxStatusTracker()
