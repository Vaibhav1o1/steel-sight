from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np


class FpsTracker:
    def __init__(self, maxlen: int = 30) -> None:
        self._q: deque[float] = deque(maxlen=maxlen)

    def tick(self) -> None:
        self._q.append(time.monotonic())

    def fps(self) -> float:
        if len(self._q) < 2:
            return 0.0
        return (len(self._q) - 1) / max((self._q[-1] - self._q[0]), 1e-6)


class RuntimeMetrics:
    def __init__(self) -> None:
        self.capture_fps = FpsTracker(maxlen=60)
        self.process_fps = FpsTracker(maxlen=60)
        self.process_ms: deque[float] = deque(maxlen=100)
        self.latency_ms: deque[float] = deque(maxlen=100)
        self._lock = threading.Lock()
        self._dropped_jobs: int = 0
        self._errors: int = 0

    def record_process_ms(self, ms: float) -> None:
        self.process_ms.append(ms)

    def record_latency_ms(self, ms: float) -> None:
        self.latency_ms.append(ms)

    def get_process_ms_p95(self) -> float:
        if not self.process_ms:
            return 0.0
        return float(np.percentile(self.process_ms, 95))

    def inc_dropped_jobs(self) -> None:
        """Thread-safe increment of dropped jobs counter."""
        with self._lock:
            self._dropped_jobs += 1

    def inc_errors(self) -> None:
        """Thread-safe increment of processing error counter."""
        with self._lock:
            self._errors += 1

    @property
    def dropped_jobs(self) -> int:
        with self._lock:
            return self._dropped_jobs

    @property
    def errors(self) -> int:
        with self._lock:
            return self._errors
