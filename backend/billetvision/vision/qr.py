from __future__ import annotations

import logging

import cv2
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

_QR_UPSCALE = 2.0


def read_qr(crops: list[NDArray[np.uint8]]) -> str | None:
    """Decode a QR code from a list of BGR crops per SPEC §12.4.

    Tries each crop (greyscale, upscaled ×2) with cv2.QRCodeDetector.
    Returns the first non-empty decoded string, or None.

    Coordinate frame: crops are upright billet BGR uint8 arrays.
    """
    detector = cv2.QRCodeDetector()
    for crop_bgr in crops:
        if crop_bgr is None or crop_bgr.size == 0:
            continue
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        upscaled = cv2.resize(
            gray,
            (int(round(w * _QR_UPSCALE)), int(round(h * _QR_UPSCALE))),
            interpolation=cv2.INTER_CUBIC,
        )
        try:
            text, _, _ = detector.detectAndDecode(upscaled)
        except Exception:
            logger.debug("QR decode error", exc_info=True)
            continue
        if text:
            return text.strip() or None
    return None
