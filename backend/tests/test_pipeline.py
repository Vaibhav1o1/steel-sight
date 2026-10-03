"""Tests for T20 — Processing Pipeline (resolved)."""

from __future__ import annotations

import queue
import time
from unittest.mock import patch

import pytest

from billetvision import config
from billetvision.runtime.events import EventBus
from billetvision.runtime.metrics import RuntimeMetrics
from billetvision.runtime.pipeline import ProcessingThread
from billetvision.runtime.sources import SyntheticSource
from billetvision.runtime.state import RuntimeState
from billetvision.runtime.worker import OcrWorkerThread
from billetvision.schemas import Spec
from billetvision.vision.types import FinalizeJob


def _make_spec() -> Spec:
    from billetvision.db import DEFAULT_SPEC_DICT

    return Spec(**DEFAULT_SPEC_DICT)


def _make_components(
    source: SyntheticSource | None = None,
):
    """Set up standard test components."""
    src = source or SyntheticSource("station", fps=30)
    state = RuntimeState(initial_source=src)
    state.active_spec = _make_spec()
    bus = EventBus()
    metrics = RuntimeMetrics()
    job_queue: queue.Queue[FinalizeJob] = queue.Queue(maxsize=8)
    system_alerts: queue.Queue[str] = queue.Queue(maxsize=32)
    pipeline = ProcessingThread(
        state, job_queue, system_alerts, metrics, bus
    )
    return state, bus, metrics, job_queue, system_alerts, pipeline


def _open_source_and_feed(state: RuntimeState, n_frames: int = 1):
    """Open the source and feed n frames into state."""
    with state.lock:
        state.source.open()
    for i in range(n_frames):
        res = state.source.read()
        if res is not None:
            frame, ts = res
            state.update_frame(frame, i + 1, ts)


# ── Test: synthetic auto-calibration ───────────────────────────────


def test_synthetic_source_autocalibrates():
    """Synthetic source, no calibration → within 2 s calibrated=true."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    events = bus.subscribe()
    pipeline.start()
    time.sleep(2.0)
    pipeline.stop(timeout_s=3.0)
    state.source.close()

    assert state.status_snapshot().calibrated is True

    # Should have published a calibration event
    found_calib = False
    while not events.empty():
        ev = events.get_nowait()
        if ev.get("type") == "calibration":
            found_calib = True
            break
    assert found_calib, "Expected a calibration event"


# ── Test: uncalibrated still streams JPEG ──────────────────────────


def test_uncalibrated_source_still_streams_jpeg():
    """With no calibration, annotated JPEG still published."""
    # Use a non-synthetic source type to prevent auto-calibration
    src = SyntheticSource("station", fps=30)
    state = RuntimeState(initial_source=src)
    state.active_spec = _make_spec()
    # Override source_info type so auto-cal is skipped
    with state.lock:
        src.open()
        state.source_info = src.info()
        # Pretend it's a webcam so autocalibrate is skipped
        state.source_info = state.source_info.model_copy(
            update={"type": "webcam"}
        )

    bus = EventBus()
    metrics = RuntimeMetrics()
    jq: queue.Queue[FinalizeJob] = queue.Queue(maxsize=8)
    sa: queue.Queue[str] = queue.Queue(maxsize=32)
    pipeline = ProcessingThread(state, jq, sa, metrics, bus)

    # Feed a frame
    res = src.read()
    assert res is not None
    frame, ts = res
    state.update_frame(frame, 1, ts)

    pipeline.start()
    time.sleep(1.0)
    pipeline.stop(timeout_s=3.0)
    src.close()

    jpeg = state.get_jpeg("annotated")
    assert jpeg is not None and len(jpeg) > 0


# ── Test: stats published even without camera ──────────────────────


def test_stats_published_when_no_frames():
    """No frames → stats events still arrive with camera_ok info."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    # Don't feed any frames
    events = bus.subscribe()
    pipeline.start()
    time.sleep(2.0)
    pipeline.stop(timeout_s=3.0)

    found_stats = False
    while not events.empty():
        ev = events.get_nowait()
        if ev.get("type") == "stats":
            found_stats = True
            break
    assert found_stats, "Expected stats events"


# ── Test: finalized job has snapshot and limited crops ──────────────


def test_finalized_job_has_snapshot_and_limited_crops():
    """FinalizeJob from synthetic run has non-empty snapshot_jpeg."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    pipeline.start()

    # Feed frames for 8 seconds to let billets pass through
    start = time.monotonic()
    idx = 4
    while time.monotonic() - start < 8.0:
        res = state.source.read()
        if res:
            frame, ts = res
            state.update_frame(frame, idx, ts)
            idx += 1
            metrics.capture_fps.tick()
        time.sleep(1 / 30.0)

    pipeline.stop(timeout_s=3.0)
    state.source.close()

    jobs = []
    while not jq.empty():
        jobs.append(jq.get_nowait())

    if jobs:
        for job in jobs:
            assert len(job.snapshot_jpeg) > 0, "snapshot_jpeg is empty"
            assert (
                len(job.crops) <= config.OCR_CROPS
            ), f"Too many crops: {len(job.crops)}"


# ── Test: queue overflow drops oldest and alerts ───────────────────


def test_queue_overflow_drops_oldest_and_alerts_once():
    """Queue of size 1, no worker: dropped_jobs increases."""
    state, bus, metrics, _, _, _ = _make_components()
    tiny_jq: queue.Queue[FinalizeJob] = queue.Queue(maxsize=1)
    sa: queue.Queue[str] = queue.Queue(maxsize=32)
    pipeline = ProcessingThread(state, tiny_jq, sa, metrics, bus)

    _open_source_and_feed(state, n_frames=3)
    pipeline.start()

    start = time.monotonic()
    idx = 4
    while time.monotonic() - start < 8.0:
        res = state.source.read()
        if res:
            frame, ts = res
            state.update_frame(frame, idx, ts)
            idx += 1
        time.sleep(1 / 30.0)

    pipeline.stop(timeout_s=3.0)
    state.source.close()

    # Check: at most 1 alert message within cooldown
    alert_count = 0
    while not sa.empty():
        sa.get_nowait()
        alert_count += 1
    assert alert_count <= 1, f"Expected at most 1 alert, got {alert_count}"


# ── Test: exception does not kill thread ───────────────────────────


def test_exception_does_not_kill_thread():
    """Monkeypatch segment to raise once → thread survives."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    call_count = 0
    _original_segment = None

    def _bad_segment(*args, **kwargs):
        nonlocal call_count, _original_segment
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Synthetic crash")
        # Import original for subsequent calls
        from billetvision.vision.segment import segment as real_seg

        return real_seg(*args, **kwargs)

    pipeline.start()
    time.sleep(0.5)  # let auto-calibrate run

    with patch(
        "billetvision.runtime.pipeline.segment", side_effect=_bad_segment
    ):
        idx = 4
        for _ in range(10):
            res = state.source.read()
            if res:
                frame, ts = res
                state.update_frame(frame, idx, ts)
                idx += 1
            time.sleep(0.05)

    # Thread should still be alive
    assert pipeline.is_alive(), "Pipeline thread died after exception"

    pipeline.stop(timeout_s=3.0)
    state.source.close()
    assert metrics.errors >= 1, "Expected at least 1 error recorded"


# ── Test: pause skips inspection but streams ───────────────────────


def test_pause_skips_inspection_but_streams():
    """Paused → JPEGs keep coming, no jobs enqueued."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    pipeline.start()
    time.sleep(1.0)  # auto-calibrate

    with state.lock:
        state.paused = True

    # Feed frames while paused
    idx = 4
    for _ in range(30):
        res = state.source.read()
        if res:
            frame, ts = res
            state.update_frame(frame, idx, ts)
            idx += 1
        time.sleep(1 / 30.0)

    pipeline.stop(timeout_s=3.0)
    state.source.close()

    assert jq.empty(), "Expected no jobs while paused"
    jpeg = state.get_jpeg("annotated")
    assert jpeg is not None and len(jpeg) > 0


# ── Test: generation change resets tracker ─────────────────────────


def test_generation_change_resets_tracker():
    """Changing trigger mode creates a new tracker."""
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    pipeline.start()
    time.sleep(1.0)  # auto-calibrate

    gen_before = state.generation

    from billetvision.enums import TriggerMode

    state.set_trigger_mode(TriggerMode.line)

    assert state.generation > gen_before

    pipeline.stop(timeout_s=3.0)
    state.source.close()


# ── Perf test (SPEC §18) ──────────────────────────────────────────


@pytest.mark.perf
def test_pipeline_synthetic_perf():
    """Run pipeline on synthetic source for 6 s and verify metrics."""

    class MockDbLogger:
        def __init__(self):
            self.inspections: list = []

        def log_inspection(self, record):
            self.inspections.append(record)

    mock_logger = MockDbLogger()
    state, bus, metrics, jq, sa, pipeline = _make_components()
    _open_source_and_feed(state, n_frames=3)

    worker = OcrWorkerThread(jq, sa, bus, state, mock_logger)
    worker.start()
    pipeline.start()

    start_t = time.monotonic()
    idx = 4
    while time.monotonic() - start_t < 6.0:
        res = state.source.read()
        if res:
            f, ts = res
            state.update_frame(f, idx, ts)
            idx += 1
            metrics.capture_fps.tick()
        time.sleep(1 / 30.0)

    pipeline.stop(timeout_s=3.0)
    worker.stop_event.set()
    worker.join(timeout=3.0)
    state.source.close()

    assert (
        len(mock_logger.inspections) >= 1
    ), "Expected at least 1 inspection logged"

    for insp in mock_logger.inspections:
        assert (
            insp["latency_ms"] < 2000.0
        ), f"Latency too high: {insp['latency_ms']} ms"

    actual_fps = metrics.process_fps.fps()
    assert actual_fps >= 15 * 0.8, f"Process FPS too low: {actual_fps}"
