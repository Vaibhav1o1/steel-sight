"""Processing thread (SPEC §15). Per-frame vision loop.

Never touches the DB, disk or network. Talks to the rest of the system
only through RuntimeState (frames in, JPEGs out), the bounded job queue,
the system-alert queue, RuntimeMetrics and the EventBus.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.runtime.events import EventBus
from billetvision.runtime.metrics import RuntimeMetrics
from billetvision.runtime.state import PipelineSnapshot, RuntimeState
from billetvision.vision.calibration import (
    calibrate_from_marker,
    detect_marker,
    drift_mm,
)
from billetvision.vision.measure import measure
from billetvision.vision.rectify import build_rectifier, glare_mask
from billetvision.vision.segment import segment
from billetvision.vision.track import Tracker
from billetvision.vision.types import Detection, FinalizeJob, Track

logger = logging.getLogger(__name__)

BGRImage = NDArray[np.uint8]


# ── Overlay (minimal HUD until T21 wires vision.overlay) ───────────


def _minimal_overlay(
    frame_bgr: BGRImage,
    *,
    calibrated: bool,
    paused: bool,
    fps: float,
    spec_id: str,
) -> BGRImage:
    """Draw a top banner on a copy, never in place."""
    out = frame_bgr.copy()
    if not calibrated:
        banner = "CALIBRATE FIRST"
        colour = (0, 0, 255)
    elif paused:
        banner = "PAUSED"
        colour = (0, 200, 255)
    else:
        banner = f"{spec_id}  {fps:.0f} fps"
        colour = (80, 220, 80)
    cv2.rectangle(
        out, (0, 0), (out.shape[1], 48), (0, 0, 0), thickness=-1
    )
    cv2.putText(
        out, banner, (16, 34),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, colour, 2, cv2.LINE_AA,
    )
    return out


def _encode_jpeg(image_bgr: BGRImage) -> bytes:
    ok, buf = cv2.imencode(
        ".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
    )
    return buf.tobytes() if ok else b""


# ── Alert gate (rate limiter) ──────────────────────────────────────


class _AlertGate:
    """Allows one alert per key per cooldown window."""

    def __init__(self, cooldown_s: float) -> None:
        self._cooldown_s = cooldown_s
        self._last: dict[str, float] = {}

    def allow(self, key: str, now: float) -> bool:
        last = self._last.get(key)
        if last is not None and now - last < self._cooldown_s:
            return False
        self._last[key] = now
        return True


# ── Processing thread ──────────────────────────────────────────────


class ProcessingThread(threading.Thread):
    def __init__(
        self,
        state: RuntimeState,
        job_queue: queue.Queue[FinalizeJob],
        system_alerts: queue.Queue[str],
        metrics: RuntimeMetrics,
        bus: EventBus,
    ) -> None:
        super().__init__(name="processing", daemon=True)
        self._state = state
        self._jobs = job_queue
        self._system_alerts = system_alerts
        self._metrics = metrics
        self._bus = bus
        self.stop_event = threading.Event()

        self._tracker: Tracker | None = None
        self._tracker_generation: int = -1
        self._alerts = _AlertGate(cooldown_s=30.0)
        self._last_index: int = -1
        self._last_stats_t: float = 0.0
        self._last_drift_t: float = time.monotonic()
        self._last_jpeg_t: float = 0.0
        self._drift_was_ok: bool = True
        self._autocal_attempted_gen: int = -1

    # ── lifecycle ───────────────────────────────────────────────────

    def stop(self, timeout_s: float = 3.0) -> None:
        self.stop_event.set()
        self.join(timeout=timeout_s)

    @property
    def track_count(self) -> int:
        return 0 if self._tracker is None else len(self._tracker.tracks)

    def run(self) -> None:
        logger.info("processing thread started")
        while not self.stop_event.is_set():
            now = time.monotonic()
            processed = False
            try:
                self._maybe_autocalibrate()
                processed = self._process_next_frame(now)
                self._maybe_check_drift(now)
                self._maybe_publish_stats(now)
            except Exception:
                logger.exception("processing loop error")
                self._metrics.inc_errors()
                self._raise_alert(
                    "processing-error",
                    "Processing error — see backend log",
                    now,
                )
            if not processed:
                time.sleep(0.002)
        logger.info("processing thread stopped")

    # ── per frame ───────────────────────────────────────────────────

    def _process_next_frame(self, now: float) -> bool:
        snap = self._state.pipeline_snapshot()
        latest = snap.latest_frame
        if latest is None or latest.index <= self._last_index:
            return False
        self._last_index = latest.index
        t0 = time.monotonic()
        frame = latest.frame
        fps = self._metrics.process_fps.fps()

        # Not calibrated: still stream, never measure (PRD E-03)
        if snap.rectifier is None:
            self._drop_tracker()
            from billetvision.vision.overlay import draw_hud
            annotated = draw_hud(
                frame,
                calibrated=False,
                paused=snap.paused,
                fps=fps,
                spec_id=snap.spec.id,
            )
            self._publish_views(now, annotated, None, frame)
            self._record(t0)
            return True

        # 1. Undistort
        t_undistort_start = time.monotonic()
        rect_bgr = snap.rectifier.apply(frame)
        rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
        t_undistort = time.monotonic() - t_undistort_start

        # Paused: keep feed alive, inspect nothing
        if snap.paused:
            self._drop_tracker()
            from billetvision.vision.overlay import draw_hud
            annotated = draw_hud(
                frame,
                calibrated=True,
                paused=True,
                fps=fps,
                spec_id=snap.spec.id,
            )
            self._publish_views(now, annotated, rect_bgr, frame)
            self._record(t0)
            return True

        # 2. Segment
        t_segment_start = time.monotonic()
        glare = glare_mask(rect_gray)
        detections = segment(
            rect_gray,
            background=snap.background,
            spec=snap.spec,
            roi=snap.rectifier.roi,
            rect_px_per_mm=snap.rectifier.cal.rect_px_per_mm,
        )
        t_segment = time.monotonic() - t_segment_start

        # PRD E-07: merged billets
        if any(d.merged for d in detections):
            self._raise_alert(
                "merged",
                "Two billets are touching — separate them",
                now,
            )

        # 3. Measure + Track
        measure_ms = [0.0]

        def measure_fn(
            det: Detection,
        ) -> tuple:
            t_m = time.monotonic()
            res = measure(det, rect_gray, rect_bgr, glare)
            measure_ms[0] += (time.monotonic() - t_m) * 1000.0
            return res

        t_track_start = time.monotonic()
        tracker = self._tracker_for(snap)
        finalized = tracker.update(
            detections, latest.t_monotonic, measure_fn=measure_fn
        )
        t_track = (time.monotonic() - t_track_start) * 1000.0 - measure_ms[0]

        # Update timings in state (converting to ms)
        with self._state.lock:
            self._state.stage_timings["undistort"] = t_undistort * 1000.0
            self._state.stage_timings["segment"] = t_segment * 1000.0
            self._state.stage_timings["track"] = t_track
            self._state.stage_timings["measure"] = measure_ms[0]

        from billetvision.vision.overlay import draw_detections, draw_tracks, draw_hud
        
        annotated = draw_hud(
            frame,
            calibrated=True,
            paused=False,
            fps=fps,
            spec_id=snap.spec.id,
        )
        annotated = draw_tracks(
            annotated,
            tracker.tracks,
            roi=snap.rectifier.roi,
            px_per_mm=snap.rectifier.cal.rect_px_per_mm,
        )

        if finalized:
            snapshot_jpeg = _encode_jpeg(annotated)
            for trk in finalized:
                if trk.samples:
                    self._enqueue(
                        self._make_job(
                            trk, snapshot_jpeg, snap, latest.t_monotonic
                        ),
                        now,
                    )

        self._publish_views(now, annotated, rect_bgr, frame)
        self._record(t0)
        return True

    # ── helpers ─────────────────────────────────────────────────────

    def _tracker_for(self, snap: PipelineSnapshot) -> Tracker:
        if (
            self._tracker is None
            or snap.generation != self._tracker_generation
        ):
            roi = snap.rectifier.roi if snap.rectifier else snap.roi
            self._tracker = Tracker(
                roi=roi, trigger_mode=snap.trigger_mode
            )
            self._tracker_generation = snap.generation
        return self._tracker

    def _drop_tracker(self) -> None:
        self._tracker = None
        self._tracker_generation = -1

    def _make_job(
        self,
        trk: Track,
        snapshot_jpeg: bytes,
        snap: PipelineSnapshot,
        t_frame: float,
    ) -> FinalizeJob:
        sharpest = sorted(
            trk.crops, key=lambda c: c[0], reverse=True
        )[: config.OCR_CROPS]
        return FinalizeJob(
            track_id=trk.id,
            samples=tuple(trk.samples),
            crops=tuple(crop for _, crop in sharpest),
            snapshot_jpeg=snapshot_jpeg,
            first_sample_t=(
                trk.first_sample_t
                if trk.first_sample_t is not None
                else t_frame
            ),
            source=snap.source_type,
            spec=snap.spec,
        )

    def _enqueue(self, job: FinalizeJob, now: float) -> None:
        try:
            self._jobs.put_nowait(job)
            return
        except queue.Full:
            pass
        try:
            self._jobs.get_nowait()
            self._metrics.inc_dropped_jobs()
        except queue.Empty:
            pass
        try:
            self._jobs.put_nowait(job)
        except queue.Full:
            self._metrics.inc_dropped_jobs()
        self._raise_alert(
            "overload",
            "Processing overloaded — some inspections were dropped",
            now,
        )

    def _raise_alert(
        self, key: str, message: str, now: float
    ) -> None:
        if not self._alerts.allow(key, now):
            return
        try:
            self._system_alerts.put_nowait(message)
        except queue.Full:
            logger.warning(
                "system alert queue full, dropped: %s", message
            )

    def _publish_views(
        self,
        now: float,
        annotated: BGRImage,
        rect_bgr: BGRImage | None,
        raw: BGRImage,
    ) -> None:
        if now - self._last_jpeg_t < 1.0 / config.STREAM_FPS:
            return
        self._last_jpeg_t = now
        self._state.publish_jpeg("annotated", _encode_jpeg(annotated))
        if rect_bgr is not None and self._state.view_requested(
            "rectified"
        ):
            self._state.publish_jpeg(
                "rectified", _encode_jpeg(rect_bgr)
            )
        if self._state.view_requested("raw"):
            self._state.publish_jpeg("raw", _encode_jpeg(raw))

    def _record(self, t0: float) -> None:
        self._metrics.process_fps.tick()
        self._metrics.record_process_ms(
            (time.monotonic() - t0) * 1000.0
        )

    # ── timers ──────────────────────────────────────────────────────

    def _maybe_publish_stats(self, now: float) -> None:
        if now - self._last_stats_t < config.STATS_INTERVAL_S:
            return
        self._last_stats_t = now
        status = self._state.status_snapshot()
        self._bus.publish(
            {
                "type": "stats",
                "fps_capture": round(
                    self._metrics.capture_fps.fps(), 1
                ),
                "fps_process": round(
                    self._metrics.process_fps.fps(), 1
                ),
                "process_ms_p95": round(
                    self._metrics.get_process_ms_p95(), 1
                ),
                "tracks": self.track_count,
                "camera_ok": status.camera_ok,
                "calibrated": status.calibrated,
                "paused": status.paused,
                "log_status": status.log_status,
                "server_time": time.time(),
            }
        )

    def _maybe_check_drift(self, now: float) -> None:
        """SPEC §4.7 / PRD E-05."""
        if now - self._last_drift_t < config.DRIFT_CHECK_S:
            return
        self._last_drift_t = now
        snap = self._state.pipeline_snapshot()
        if (
            snap.calibration is None
            or snap.latest_frame is None
            or snap.calibration_is_synthetic
        ):
            return
        frame = snap.latest_frame.frame
        cal = snap.calibration
        if (
            cal.camera_matrix is not None
            and cal.dist_coeffs is not None
        ):
            frame = cv2.undistort(
                frame, cal.camera_matrix, cal.dist_coeffs
            )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        result = detect_marker(gray)
        if result is None:
            return  # marker covered — not an error
        corners, _shift = result
        d = drift_mm(corners, cal.marker_corners_px, cal.image_px_per_mm)
        ok = d <= config.DRIFT_MAX_MM
        if self._state.set_drift(d, ok):
            self._bus.publish(
                {
                    "type": "calibration",
                    "calibration": self._state.calibration_state().model_dump(),
                }
            )
        if self._drift_was_ok and not ok:
            self._raise_alert(
                "drift",
                f"Camera or marker moved by {d:.1f} mm — recalibrate",
                now,
            )
        self._drift_was_ok = ok

    def _maybe_autocalibrate(self) -> None:
        """SPEC §6: synthetic source + no calibration → auto-calibrate."""
        snap = self._state.pipeline_snapshot()
        if snap.source_type != "synthetic" or snap.rectifier is not None:
            return
        if self._autocal_attempted_gen == snap.generation:
            return
        self._autocal_attempted_gen = snap.generation
        empty = snap.empty_frame()
        if empty is None:
            return
        gray = cv2.cvtColor(empty, cv2.COLOR_BGR2GRAY)
        result = detect_marker(gray)
        if result is None:
            logger.error(
                "synthetic auto-calibration: marker not found"
            )
            return
        corners, _shift = result
        h, w = empty.shape[:2]
        cal = calibrate_from_marker(
            corners,
            image_size=(w, h),
            marker_mm=config.MARKER_MM,
            roi=snap.roi,
            rect_px_per_mm=config.RECT_PX_PER_MM,
        )
        rectifier = build_rectifier(cal)
        background = cv2.cvtColor(
            rectifier.apply(empty), cv2.COLOR_BGR2GRAY
        )
        self._state.apply_calibration(
            cal, rectifier, background, synthetic=True
        )
        self._bus.publish(
            {
                "type": "calibration",
                "calibration": self._state.calibration_state().model_dump(),
            }
        )
        logger.info(
            "synthetic auto-calibration applied (%.2f px/mm)",
            cal.image_px_per_mm,
        )
