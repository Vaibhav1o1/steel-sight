from __future__ import annotations

import json

import pytest

from billetvision import config
from billetvision.enums import (
    AlertLevel,
    DefectType,
    IdSource,
    InspectionStatus,
    LogFileStatus,
    SourceType,
    StreamView,
    TriggerMode,
)


def test_config_camera_defaults() -> None:
    assert config.SEED == 42
    assert config.SOURCE_TYPE == "synthetic"
    assert config.SOURCE_VALUE == ""
    assert config.FRAME_WIDTH == 1920
    assert config.FRAME_HEIGHT == 1080
    assert config.CAPTURE_FPS == 30
    assert config.RECONNECT_S == 2.0
    assert config.STALE_FRAME_S == 1.0


def test_config_calibration_defaults() -> None:
    assert config.ARUCO_DICT == "DICT_4X4_50"
    assert config.MARKER_ID == 0
    assert config.MARKER_MM == 80.0
    assert config.RECT_PX_PER_MM == 3.0
    assert config.ROI_DEFAULT == {"x0_mm": 60.0, "y0_mm": -170.0, "w_mm": 600.0, "h_mm": 340.0}
    assert config.MIN_IMAGE_PX_PER_MM == 2.5
    assert config.BACKGROUND_FRAMES == 15
    assert config.DRIFT_CHECK_S == 30
    assert config.DRIFT_MAX_MM == 1.0


def test_config_segmentation_defaults() -> None:
    assert config.SEG_BLUR_SIGMA == 1.5
    assert config.DIFF_MIN == 25
    assert config.CLOSE_KERNEL_MM == 4.0
    assert config.OPEN_KERNEL_MM == 2.0
    assert config.EDGE_MARGIN_MM == 5.0
    assert config.MIN_ASPECT == 1.5
    assert config.SATURATION_LEVEL == 250


def test_config_measurement_defaults() -> None:
    assert config.N_SLICES == 21
    assert config.SLICE_SPAN == 0.9
    assert config.SAMPLE_STEP_PX == 0.25
    assert config.SEARCH_MARGIN_MM == 8.0
    assert config.MEASURE_BLUR_SIGMA == 1.0
    assert config.END_EXCLUDE_MM == 10.0
    assert config.DEFECT_MIN_SPAN_MM == 3.0


def test_config_tracking_defaults() -> None:
    assert config.TRIGGER_MODE == "auto"
    assert config.TRACK_MATCH_MM == 60.0
    assert config.TRACK_MAX_MISSING == 8
    assert config.STABLE_FRAMES == 6
    assert config.STABLE_MM == 2.0
    assert config.SAMPLES_TARGET == 7
    assert config.SAMPLES_MIN == 3
    assert config.LINE_WINDOW_MM == 40.0
    assert config.SAMPLE_TIMEOUT_S == 3.0
    assert config.OCR_CROPS == 3
    assert config.CROP_PAD_MM == 4.0


def test_config_ocr_defaults() -> None:
    assert config.OCR_MIN_SCORE == 0.5
    assert config.OCR_UPSCALE == 1.5


def test_config_runtime_defaults() -> None:
    assert config.STREAM_FPS == 15
    assert config.JPEG_QUALITY == 80
    assert config.JOB_QUEUE_SIZE == 8
    assert config.EXCEL_DEBOUNCE_S == 2.0
    assert config.EXCEL_RETRY_S == 5.0
    assert config.EXCEL_MAX_ROWS == 20000
    assert config.STATS_INTERVAL_S == 1.0
    assert config.DATABASE_URL == "sqlite:///./data/billetvision.db"
    assert config.LOG_DIR == "logs"
    assert config.SNAPSHOT_DIR == "snapshots"
    assert config.CALIB_DIR == "calibration"
    assert config.REPORT_DIR == "reports"
    assert config.PROPS_CSV == "../data/props.csv"
    assert config.TTS_ENABLED is False


def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "99")
    monkeypatch.setenv("TTS_ENABLED", "true")
    monkeypatch.setenv(
        "ROI_DEFAULT",
        json.dumps({"x0_mm": 10.0, "y0_mm": 20.0, "w_mm": 100.0, "h_mm": 200.0}),
    )

    assert int(config.os.getenv("SEED", "42")) == 99
    assert config._get_bool("TTS_ENABLED", False) is True
    assert config._get_json_dict("ROI_DEFAULT", {}) == {
        "x0_mm": 10.0,
        "y0_mm": 20.0,
        "w_mm": 100.0,
        "h_mm": 200.0,
    }


def test_enums_values_match_contracts() -> None:
    assert [e.value for e in InspectionStatus] == ["Pass", "Rework", "Fail"]
    assert [e.value for e in IdSource] == ["ocr", "qr", "none"]
    assert [e.value for e in DefectType] == ["notch", "taper", "bulge", "camber"]
    assert [e.value for e in SourceType] == ["webcam", "url", "file", "synthetic"]
    assert [e.value for e in TriggerMode] == ["auto", "stable", "line"]
    assert [e.value for e in AlertLevel] == ["Fail", "Rework", "System"]
    assert [e.value for e in LogFileStatus] == ["ok", "locked", "error"]
    assert [e.value for e in StreamView] == ["annotated", "rectified", "raw"]
