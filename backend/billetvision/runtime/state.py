from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.enums import SourceType, TriggerMode
from billetvision.runtime.sources import FrameSource, SyntheticSource, make_source
from billetvision.schemas import SourceInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatestFrame:
    """Newest captured video frame with sequence index and monotonic timestamp."""

    frame: NDArray[np.uint8]
    index: int
    t_monotonic: float


class RuntimeState:
    """Thread-safe central state container for BilletVision runtime."""

    def __init__(self, initial_source: FrameSource | None = None) -> None:
        self.lock = threading.Lock()
        self.source: FrameSource = initial_source or SyntheticSource(mode="station")
        self.source_info: SourceInfo = self.source.info()

        self.paused: bool = False
        self.trigger_mode: TriggerMode = TriggerMode.auto
        self.calib_drift_alert: bool = False
        self.calib_drift_mm: float = 0.0

        self.latest_frame: LatestFrame | None = None
        self.latest_annotated_jpeg: bytes | None = None
        self.latest_rectified_jpeg: bytes | None = None
        self.latest_raw_jpeg: bytes | None = None

        # Metrics
        self.fps_capture: float = 0.0
        self.fps_process: float = 0.0
        self.process_ms_p95: float = 0.0
        self.stage_timings: dict[str, float] = {
            "undistort": 0.0,
            "segment": 0.0,
            "track": 0.0,
            "measure": 0.0,
            "id": 0.0,
            "decide": 0.0,
            "write": 0.0,
        }
        self.active_tracks_count: int = 0
        self.dropped_jobs: int = 0
        self.inspections_total: int = 0
        self.by_status: dict[str, int] = {
            "Pass": 0,
            "Rework": 0,
            "Fail": 0,
            "Review": 0,
        }
        self.start_time: float = time.time()

    def update_frame(self, frame: NDArray[np.uint8], index: int, t_monotonic: float) -> None:
        """Atomically set the newest frame, discarding any older frame."""
        with self.lock:
            self.latest_frame = LatestFrame(frame=frame, index=index, t_monotonic=t_monotonic)

    def get_frame(self) -> LatestFrame | None:
        """Atomically read the newest frame."""
        with self.lock:
            return self.latest_frame

    def set_annotated_jpeg(self, jpeg_bytes: bytes) -> None:
        with self.lock:
            self.latest_annotated_jpeg = jpeg_bytes

    def set_rectified_jpeg(self, jpeg_bytes: bytes) -> None:
        with self.lock:
            self.latest_rectified_jpeg = jpeg_bytes

    def set_raw_jpeg(self, jpeg_bytes: bytes) -> None:
        with self.lock:
            self.latest_raw_jpeg = jpeg_bytes

    def get_jpeg(self, view: str = "annotated") -> bytes | None:
        with self.lock:
            if view == "rectified":
                return self.latest_rectified_jpeg
            if view == "raw":
                return self.latest_raw_jpeg
            return self.latest_annotated_jpeg


class CaptureThread:
    """Dedicated background thread capturing frames into RuntimeState."""

    def __init__(self, state: RuntimeState) -> None:
        self.state = state
        self._stop_event = threading.Event()
        self._frame_count = 0
        self._fps_timer = time.monotonic()
        self._fps_count = 0

        self._thread = threading.Thread(
            target=self._capture_loop, name="capture_thread", daemon=True
        )

    def start(self) -> None:
        # Open source
        with self.state.lock:
            self.state.source.open()
            self.state.source_info = self.state.source.info()
        self._thread.start()
        logger.info("CaptureThread started")

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        with self.state.lock:
            self.state.source.close()
        logger.info("CaptureThread stopped")

    def switch_source(self, source_type: str | SourceType, value: str = "") -> bool:
        """Switch video source safely.

        Opens and tests new source first; keeps previous source if new one fails.
        """
        logger.info("Switching capture source to %s (%s)...", source_type, value)
        new_source = make_source(source_type, value)
        if not new_source.open():
            logger.warning("Failed to open candidate source %s", source_type)
            return False

        # Test read
        test_frame = new_source.read()
        if test_frame is None:
            logger.warning("Candidate source %s opened but returned no frame", source_type)
            new_source.close()
            return False

        with self.state.lock:
            old_source = self.state.source
            self.state.source = new_source
            self.state.source_info = new_source.info()
            # Push test frame immediately
            self._frame_count += 1
            self.state.latest_frame = LatestFrame(
                frame=test_frame[0],
                index=self._frame_count,
                t_monotonic=test_frame[1],
            )

        old_source.close()
        logger.info("Successfully switched to %s (%s)", source_type, value)
        return True

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            with self.state.lock:
                paused = self.state.paused
                current_source = self.state.source

            if paused:
                time.sleep(0.05)
                continue

            res = current_source.read()
            if res is None:
                # Connection dropped or empty frame
                time.sleep(0.01)
                now = time.monotonic()
                latest = self.state.get_frame()
                if latest is not None and (now - latest.t_monotonic > config.STALE_FRAME_S):
                    logger.debug("Source frame stale; attempting reconnect...")
                    time.sleep(config.RECONNECT_S)
                    current_source.open()
                continue

            frame, t_mono = res
            self._frame_count += 1
            self._fps_count += 1

            # Update latest frame (drops any older frame)
            self.state.update_frame(frame, self._frame_count, t_mono)

            # Compute capture FPS every second
            now = time.monotonic()
            dt = now - self._fps_timer
            if dt >= 1.0:
                with self.state.lock:
                    self.state.fps_capture = round(self._fps_count / dt, 1)
                self._fps_count = 0
                self._fps_timer = now
