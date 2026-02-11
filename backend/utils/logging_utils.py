import time


class RateLimitLogger:
    def __init__(self, interval_sec: float):
        self.interval = interval_sec
        self._last = 0.0

    def should_log(self) -> bool:
        now = time.time()
        if now - self._last >= self.interval:
            self._last = now
            return True
        return False
