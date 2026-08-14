from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PI_PORT = 5000

_GAZEBO_ENABLE_COOLDOWN_S = 10.0
_UNAVAILABLE_BACKOFF_BASE_S = 5.0
_UNAVAILABLE_BACKOFF_MAX_S = 60.0
_DRONE_DISCONNECTED_RETRY_MS = 5000
_last_gazebo_enable_attempt = 0.0
_gazebo_no_topic_warning_logged = False
