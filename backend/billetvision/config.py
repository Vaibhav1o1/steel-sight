from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load root .env if it exists, otherwise fall back to default dotenv discovery
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.is_file():
    load_dotenv(_root_env)
else:
    load_dotenv()


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def _get_json_dict(key: str, default: dict[str, float]) -> dict[str, float]:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        parsed = json.loads(val)
        if isinstance(parsed, dict):
            return {k: float(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError):
        pass
    return default


# Camera
SEED: int = int(os.getenv("SEED", "42"))
SOURCE_TYPE: str = os.getenv("SOURCE_TYPE", "synthetic")
SOURCE_VALUE: str = os.getenv("SOURCE_VALUE", "")
FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", "1920"))
FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", "1080"))
CAPTURE_FPS: int = int(os.getenv("CAPTURE_FPS", "30"))
RECONNECT_S: float = float(os.getenv("RECONNECT_S", "2.0"))
STALE_FRAME_S: float = float(os.getenv("STALE_FRAME_S", "1.0"))

# Calibration & geometry
ARUCO_DICT: str = os.getenv("ARUCO_DICT", "DICT_4X4_50")
MARKER_ID: int = int(os.getenv("MARKER_ID", "0"))
MARKER_MM: float = float(os.getenv("MARKER_MM", "80.0"))
RECT_PX_PER_MM: float = float(os.getenv("RECT_PX_PER_MM", "3.0"))
ROI_DEFAULT: dict[str, float] = _get_json_dict(
    "ROI_DEFAULT",
    {"x0_mm": 60.0, "y0_mm": -170.0, "w_mm": 600.0, "h_mm": 340.0},
)
MIN_IMAGE_PX_PER_MM: float = float(os.getenv("MIN_IMAGE_PX_PER_MM", "2.5"))
BACKGROUND_FRAMES: int = int(os.getenv("BACKGROUND_FRAMES", "15"))
DRIFT_CHECK_S: int = int(os.getenv("DRIFT_CHECK_S", "30"))
DRIFT_MAX_MM: float = float(os.getenv("DRIFT_MAX_MM", "1.0"))

# Segmentation
SEG_BLUR_SIGMA: float = float(os.getenv("SEG_BLUR_SIGMA", "1.5"))
DIFF_MIN: int = int(os.getenv("DIFF_MIN", "25"))
CLOSE_KERNEL_MM: float = float(os.getenv("CLOSE_KERNEL_MM", "4.0"))
OPEN_KERNEL_MM: float = float(os.getenv("OPEN_KERNEL_MM", "2.0"))
EDGE_MARGIN_MM: float = float(os.getenv("EDGE_MARGIN_MM", "5.0"))
MIN_ASPECT: float = float(os.getenv("MIN_ASPECT", "1.5"))
SATURATION_LEVEL: int = int(os.getenv("SATURATION_LEVEL", "250"))

# Measurement & defects
N_SLICES: int = int(os.getenv("N_SLICES", "21"))
SLICE_SPAN: float = float(os.getenv("SLICE_SPAN", "0.9"))
SAMPLE_STEP_PX: float = float(os.getenv("SAMPLE_STEP_PX", "0.25"))
SEARCH_MARGIN_MM: float = float(os.getenv("SEARCH_MARGIN_MM", "8.0"))
MEASURE_BLUR_SIGMA: float = float(os.getenv("MEASURE_BLUR_SIGMA", "1.0"))
END_EXCLUDE_MM: float = float(os.getenv("END_EXCLUDE_MM", "10.0"))
DEFECT_MIN_SPAN_MM: float = float(os.getenv("DEFECT_MIN_SPAN_MM", "3.0"))

# Tracking & triggers
TRIGGER_MODE: str = os.getenv("TRIGGER_MODE", "auto")
TRACK_MATCH_MM: float = float(os.getenv("TRACK_MATCH_MM", "60.0"))
TRACK_MAX_MISSING: int = int(os.getenv("TRACK_MAX_MISSING", "8"))
STABLE_FRAMES: int = int(os.getenv("STABLE_FRAMES", "6"))
STABLE_MM: float = float(os.getenv("STABLE_MM", "2.0"))
SAMPLES_TARGET: int = int(os.getenv("SAMPLES_TARGET", "7"))
SAMPLES_MIN: int = int(os.getenv("SAMPLES_MIN", "3"))
LINE_WINDOW_MM: float = float(os.getenv("LINE_WINDOW_MM", "40.0"))
SAMPLE_TIMEOUT_S: float = float(os.getenv("SAMPLE_TIMEOUT_S", "3.0"))
OCR_CROPS: int = int(os.getenv("OCR_CROPS", "3"))
CROP_PAD_MM: float = float(os.getenv("CROP_PAD_MM", "4.0"))

# OCR
OCR_MIN_SCORE: float = float(os.getenv("OCR_MIN_SCORE", "0.5"))
OCR_UPSCALE: float = float(os.getenv("OCR_UPSCALE", "1.5"))

# Runtime & logging
STREAM_FPS: int = int(os.getenv("STREAM_FPS", "15"))
JPEG_QUALITY: int = int(os.getenv("JPEG_QUALITY", "80"))
JOB_QUEUE_SIZE: int = int(os.getenv("JOB_QUEUE_SIZE", "8"))
EXCEL_DEBOUNCE_S: float = float(os.getenv("EXCEL_DEBOUNCE_S", "2.0"))
EXCEL_RETRY_S: float = float(os.getenv("EXCEL_RETRY_S", "5.0"))
EXCEL_MAX_ROWS: int = int(os.getenv("EXCEL_MAX_ROWS", "20000"))
STATS_INTERVAL_S: float = float(os.getenv("STATS_INTERVAL_S", "1.0"))
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/billetvision.db")
LOG_DIR: str = os.getenv("LOG_DIR", "logs")
SNAPSHOT_DIR: str = os.getenv("SNAPSHOT_DIR", "snapshots")
CALIB_DIR: str = os.getenv("CALIB_DIR", "calibration")
REPORT_DIR: str = os.getenv("REPORT_DIR", "reports")
PROPS_CSV: str = os.getenv("PROPS_CSV", "../data/props.csv")
TTS_ENABLED: bool = _get_bool("TTS_ENABLED", False)
