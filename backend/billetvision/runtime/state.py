from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.enums import LogFileStatus, SourceType, TriggerMode
from billetvision.runtime.sources import FrameSource, SyntheticSource, make_source
from billetvision.schemas import CalibrationState, Roi, SourceInfo, Spec
from billetvision.vision.calibration import calibration_to_state
from billetvision.vision.rectify import Rectifier
from billetvision.vision.types import Calibration

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LatestFrame:
    """Newest captured video frame with sequence index and monotonic timestamp."""

    frame: NDArray[np.uint8]
    index: int
    t_monotonic: float


@dataclass(frozen=True, eq=False)
class PipelineSnapshot:
    """One consistent read of every field the processing loop needs."""

    latest_frame: LatestFrame | None
    rectifier: Rectifier | None
    calibration: Calibration | None
    calibration_is_synthetic: bool
    background: NDArray[np.uint8] | None
    roi: Roi
    spec: Spec
    paused: bool
    trigger_mode: str
    source_type: str
    generation: int
    empty_frame_fn: Callable[[], NDArray[np.uint8] | None]

    def empty_frame(self) -> NDArray[np.uint8] | None:
        return self.empty_frame_fn()


@dataclass(frozen=True)
class StatusSnapshot:
    """Lightweight read for stats publishing."""

    camera_ok: bool
    calibrated: bool
    paused: bool
    log_status: str


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
        self._drift_ok: bool = True

        self.latest_frame: LatestFrame | None = None
        self.latest_annotated_jpeg: bytes | None = None
        self.latest_rectified_jpeg: bytes | None = None
        self.latest_raw_jpeg: bytes | None = None

        # Calibration state
        self.rectifier: Rectifier | None = None
        self.calibration: Calibration | None = None
        self._calibration_is_synthetic: bool = False
        self._background_rect_gray: NDArray[np.uint8] | None = None

        # Active spec (loaded at startup, never None after init)
        self._active_spec: Spec | None = None

        # Generation counter — bumps on calibration, ROI, spec, trigger, source
        self._generation: int = 0

        # Metrics (kept for backward compat with CaptureThread)
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

        # Log file status
        self._log_status: str = LogFileStatus.ok

        # Stream view requests (set of view names with last-request timestamps)
        self._view_requests: dict[str, float] = {}
        self._view_grace_s: float = 5.0

    # ── Frame access ────────────────────────────────────────────────────

    def update_frame(
        self, frame: NDArray[np.uint8], index: int, t_monotonic: float
    ) -> None:
        """Atomically set the newest frame, discarding any older frame."""
        with self.lock:
            self.latest_frame = LatestFrame(
                frame=frame, index=index, t_monotonic=t_monotonic
            )

    def get_frame(self) -> LatestFrame | None:
        """Atomically read the newest frame."""
        with self.lock:
            return self.latest_frame

    # ── JPEG views ──────────────────────────────────────────────────────

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

    def publish_jpeg(self, view: str, data: bytes) -> None:
        """Called by the pipeline to update a stream view."""
        with self.lock:
            if view == "annotated":
                self.latest_annotated_jpeg = data
            elif view == "rectified":
                self.latest_rectified_jpeg = data
            elif view == "raw":
                self.latest_raw_jpeg = data

    def view_requested(self, view: str) -> bool:
        """True while a client is connected to this view (5 s grace)."""
        with self.lock:
            ts = self._view_requests.get(view)
            if ts is None:
                return False
            return (time.monotonic() - ts) < self._view_grace_s

    def request_view(self, view: str) -> None:
        """Called by the stream endpoint to signal interest."""
        with self.lock:
            self._view_requests[view] = time.monotonic()

    # ── Spec ────────────────────────────────────────────────────────────

    @property
    def active_spec(self) -> Spec | None:
        with self.lock:
            return self._active_spec

    @active_spec.setter
    def active_spec(self, spec: Spec) -> None:
        with self.lock:
            self._active_spec = spec
            self._generation += 1

    # ── Calibration ─────────────────────────────────────────────────────

    def apply_calibration(
        self,
        cal: Calibration,
        rectifier: Rectifier,
        background: NDArray[np.uint8] | None = None,
        synthetic: bool = False,
    ) -> None:
        """Atomic swap of calibration + rectifier + background. Bumps generation."""
        with self.lock:
            self.calibration = cal
            self.rectifier = rectifier
            self._background_rect_gray = background
            self._calibration_is_synthetic = synthetic
            self._generation += 1

    def set_drift(self, drift_val_mm: float, ok: bool) -> bool:
        """Update drift values. Returns True if drift_ok changed."""
        with self.lock:
            self.calib_drift_mm = drift_val_mm
            changed = self._drift_ok != ok
            self._drift_ok = ok
            self.calib_drift_alert = not ok
            return changed

    def calibration_state(self) -> CalibrationState:
        """Build the CalibrationState pydantic model for API/WS."""
        with self.lock:
            if self.calibration is None:
                return CalibrationState(
                    calibrated=False,
                    has_background=False,
                    has_intrinsics=False,
                    marker_mm=config.MARKER_MM,
                    image_px_per_mm=0.0,
                    rect_px_per_mm=config.RECT_PX_PER_MM,
                    roi=Roi(**config.ROI_DEFAULT),
                    reprojection_error_px=0.0,
                    verify=None,
                    drift_mm=None,
                    drift_ok=True,
                    created_at=0.0,
                )
            return calibration_to_state(
                self.calibration,
                has_background=self._background_rect_gray is not None,
                drift_val_mm=self.calib_drift_mm,
                drift_ok=self._drift_ok,
            )

    # ── Snapshots ───────────────────────────────────────────────────────

    def pipeline_snapshot(self) -> PipelineSnapshot:
        """One consistent read under the lock for the processing thread."""
        with self.lock:
            # Build the empty_frame callable outside the lock
            source = self.source

            def _empty() -> NDArray[np.uint8] | None:
                return source.empty_frame()

            return PipelineSnapshot(
                latest_frame=self.latest_frame,
                rectifier=self.rectifier,
                calibration=self.calibration,
                calibration_is_synthetic=self._calibration_is_synthetic,
                background=self._background_rect_gray,
                roi=Roi(**config.ROI_DEFAULT)
                if self.calibration is None
                else self.calibration.roi,
                spec=self._active_spec
                if self._active_spec is not None
                else _default_spec(),
                paused=self.paused,
                trigger_mode=str(self.trigger_mode),
                source_type=self.source_info.type
                if self.source_info is not None
                else "synthetic",
                generation=self._generation,
                empty_frame_fn=_empty,
            )

    def status_snapshot(self) -> StatusSnapshot:
        """Lightweight read for stats publishing."""
        with self.lock:
            # camera_ok: capture thread active AND last frame not stale
            camera_ok = True
            if self.latest_frame is not None:
                age = time.monotonic() - self.latest_frame.t_monotonic
                camera_ok = age <= config.STALE_FRAME_S
            elif self.source_info is not None:
                camera_ok = False  # no frame yet

            return StatusSnapshot(
                camera_ok=camera_ok,
                calibrated=self.rectifier is not None,
                paused=self.paused,
                log_status=str(self._log_status),
            )

    def set_log_status(self, status: str) -> None:
        with self.lock:
            self._log_status = status

    # ── Source ───────────────────────────────────────────────────────────

    @property
    def generation(self) -> int:
        with self.lock:
            return self._generation

    def set_trigger_mode(self, mode: TriggerMode) -> None:
        with self.lock:
            self.trigger_mode = mode
            self._generation += 1


def _default_spec() -> Spec:
    """Fallback spec when none has been loaded from the DB yet."""
    from billetvision.db import DEFAULT_SPEC_DICT

    return Spec(**DEFAULT_SPEC_DICT)


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

    def switch_source(
        self, source_type: str | SourceType, value: str = ""
    ) -> bool:
        """Switch video source safely."""
        logger.info(
            "Switching capture source to %s (%s)...", source_type, value
        )
        new_source = make_source(source_type, value)
        if not new_source.open():
            logger.warning(
                "Failed to open candidate source %s", source_type
            )
            return False

        # Test read
        test_frame = new_source.read()
        if test_frame is None:
            logger.warning(
                "Candidate source %s opened but returned no frame",
                source_type,
            )
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
            # Discard synthetic calibration when switching to a real source
            if (
                self.state._calibration_is_synthetic
                and new_source.info().type != "synthetic"
            ):
                self.state.rectifier = None
                self.state.calibration = None
                self.state._calibration_is_synthetic = False
                self.state._background_rect_gray = None
                self.state._generation += 1

        old_source.close()
        logger.info(
            "Successfully switched to %s (%s)", source_type, value
        )
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
                if latest is not None and (
                    now - latest.t_monotonic > config.STALE_FRAME_S
                ):
                    logger.debug(
                        "Source frame stale; attempting reconnect..."
                    )
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
