from __future__ import annotations

import logging
import threading
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_engine: Any | None = None  # rapidocr.RapidOCR, narrowed at boundary
_ready: bool = False


def _load_engine() -> tuple[Any, bool]:
    """Load RapidOCR engine and run smoke test. Returns (engine, ready)."""
    try:
        from rapidocr import RapidOCR  # type: ignore[import-untyped]

        engine = RapidOCR()

        # Smoke test: white text on black background
        smoke = np.zeros((50, 200, 3), dtype=np.uint8)
        cv2.putText(smoke, "TEST", (10, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        result = engine(smoke)
        txts: tuple[str, ...] = result.txts if hasattr(result, "txts") else ()
        ok = len(txts) > 0
        logger.info("OcrEngine loaded; smoke test %s", "PASS" if ok else "FAIL")
        return engine, ok
    except Exception:
        logger.warning("OcrEngine failed to load — OCR will be unavailable", exc_info=True)
        return None, False


def _get_engine() -> tuple[Any | None, bool]:
    """Return the singleton engine (lazy-loads on first call)."""
    global _engine, _ready
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine, _ready = _load_engine()
    return _engine, _ready


def ocr_ready() -> bool:
    """Return True if the OCR engine is loaded and passed its smoke test."""
    _, ready = _get_engine()
    return ready


def _preprocess(crop_bgr: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """CLAHE → upscale → back to 3-channel BGR per SPEC §12.2."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    scale = max(config.OCR_UPSCALE, 1.0)
    h, w = enhanced.shape[:2]
    new_size = (int(round(w * scale)), int(round(h * scale)))
    upscaled = cv2.resize(enhanced, new_size, interpolation=cv2.INTER_CUBIC)
    return cv2.cvtColor(upscaled, cv2.COLOR_GRAY2BGR)


def _adapt_result(result: Any) -> list[tuple[str, float]]:
    """Extract (text, score) pairs from a RapidOCROutput, adapting to installed API."""
    if result is None:
        return []

    # Modern API: result.txts and result.scores are parallel tuples
    if hasattr(result, "txts") and hasattr(result, "scores"):
        txts: tuple[str, ...] = result.txts or ()
        scores: tuple[float, ...] = result.scores or ()
        out: list[tuple[str, float]] = []
        for txt, score in zip(txts, scores, strict=False):
            if isinstance(txt, str) and isinstance(score, float | int):
                s = float(score)
                if s >= config.OCR_MIN_SCORE:
                    out.append((txt, s))
        return out

    # Legacy API: result is a list/tuple of (boxes, text, score) triples
    out_legacy: list[tuple[str, float]] = []
    try:
        items = list(result)
        for item in items:
            if item is None:
                continue
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                txt_val = item[1]
                score_val = item[2]
                if isinstance(txt_val, str) and isinstance(score_val, float | int):
                    s = float(score_val)
                    if s >= config.OCR_MIN_SCORE:
                        out_legacy.append((txt_val, s))
    except Exception:
        pass

    return out_legacy


def read(crop_bgr: NDArray[np.uint8]) -> list[tuple[str, float]]:
    """Run OCR on a single BGR crop.

    Returns a list of (text, score) pairs with score >= OCR_MIN_SCORE.
    Returns [] if the engine is not ready or detects nothing.

    Coordinate frame: crop_bgr is an upright billet crop (BGR uint8).
    """
    engine, ready = _get_engine()
    if not ready or engine is None:
        return []

    processed = _preprocess(crop_bgr)
    try:
        result = engine(processed)
    except Exception:
        logger.debug("OCR inference error", exc_info=True)
        return []

    return _adapt_result(result)
