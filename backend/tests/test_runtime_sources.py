from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from billetvision.enums import SourceType
from billetvision.runtime.sources import (
    FileSource,
    SyntheticSource,
)
from billetvision.runtime.state import CaptureThread, RuntimeState
from tools.record import record_session


def test_synthetic_source_lifecycle() -> None:
    src = SyntheticSource(mode="station", fps=30)
    assert src.open() is True

    # Read two frames, check monotonic time
    f1 = src.read()
    assert f1 is not None
    img1, t1 = f1
    assert img1.shape == (1080, 1920, 3)

    f2 = src.read()
    assert f2 is not None
    img2, t2 = f2
    assert t2 >= t1

    # Empty background frame for calibration
    empty = src.empty_frame()
    assert empty is not None
    assert empty.shape == (1080, 1920, 3)

    info = src.info()
    assert info.type == SourceType.synthetic
    assert info.frame_width == 1920
    assert info.frame_height == 1080

    src.close()
    assert src.read() is None


def test_file_source_and_loop_on_eof(tmp_path: Path) -> None:
    # Generate a small 10-frame test video
    vid_file = tmp_path / "test_loop.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(vid_file), fourcc, 30.0, (320, 240))
    for i in range(10):
        frame = np.full((240, 320, 3), i * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    src = FileSource(vid_file, fps=100)  # high fps for fast test
    assert src.open() is True

    frames_read = 0
    for _ in range(25):  # read > 10 frames to trigger loop
        res = src.read()
        assert res is not None
        frames_read += 1

    assert frames_read == 25
    src.close()


def test_capture_thread_and_drop_stale() -> None:
    state = RuntimeState(SyntheticSource(mode="station", fps=30))
    cap_thread = CaptureThread(state)
    cap_thread.start()

    time.sleep(0.2)
    f1 = state.get_frame()
    assert f1 is not None
    assert f1.index >= 1

    # Wait another moment to confirm frame index advances and only newest is kept
    time.sleep(0.15)
    f2 = state.get_frame()
    assert f2 is not None
    assert f2.index > f1.index
    assert f2.t_monotonic >= f1.t_monotonic

    cap_thread.stop()


def test_switch_source_safe_fallback() -> None:
    state = RuntimeState(SyntheticSource(mode="station", fps=30))
    cap_thread = CaptureThread(state)
    cap_thread.start()

    initial_type = state.source_info.type
    assert initial_type == SourceType.synthetic

    # Attempt to switch to nonexistent video file -> must fail and preserve synthetic source
    ok = cap_thread.switch_source("file", "nonexistent_file_path_12345.mp4")
    assert ok is False
    assert state.source_info.type == SourceType.synthetic

    # Switch to synthetic station mode -> succeeds
    ok2 = cap_thread.switch_source("synthetic", "station")
    assert ok2 is True
    assert state.source_info.type == SourceType.synthetic

    cap_thread.stop()


def test_record_tool(tmp_path: Path) -> None:
    rec_dir = tmp_path / "recordings"
    video_path = record_session(
        source_type="synthetic",
        duration_s=0.5,
        out_dir=rec_dir,
        target_fps=20,
    )

    assert video_path.is_file()
    assert video_path.stat().st_size > 0

    manifest_file = rec_dir / "manifest.json"
    assert manifest_file.is_file()
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(data) >= 1
    assert data[0]["source_type"] == "synthetic"
    assert data[0]["frames_recorded"] > 0
