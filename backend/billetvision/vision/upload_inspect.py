from __future__ import annotations

import io
import logging
import threading
import time
import uuid
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from billetvision import config
from billetvision.schemas import Spec
from billetvision.schemas_upload import UploadCalibrationInfo, UploadResult

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PIXELS = 50_000_000  # 50 MP
MAX_SIDE_PX = 2560
CACHE_TTL_SECONDS = 3600.0  # 1 hour

# In-memory storage for annotated result images: uuid -> (jpeg_bytes, created_at)
_image_cache: dict[str, tuple[bytes, float]] = {}
_cache_lock = threading.Lock()


def get_cached_image(image_id: str) -> bytes | None:
    """Retrieve an annotated image from the cache if not expired."""
    _cleanup_cache()
    with _cache_lock:
        item = _image_cache.get(image_id)
        if item is not None:
            return item[0]
    return None


def _cleanup_cache() -> None:
    now = time.monotonic()
    with _cache_lock:
        expired = [
            k for k, (_, ts) in _image_cache.items() if (now - ts) > CACHE_TTL_SECONDS
        ]
        for k in expired:
            _image_cache.pop(k, None)


def _store_image(image_id: str, jpeg_bytes: bytes) -> None:
    _cleanup_cache()
    with _cache_lock:
        _image_cache[image_id] = (jpeg_bytes, time.monotonic())


def validate_image_bytes(data: bytes) -> str:
    """Validate file size and magic bytes.

    Returns 'jpeg' or 'png', or raises ValueError.
    """
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE: Image size exceeds 15 MB limit")

    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    raise ValueError("UNSUPPORTED_MEDIA_TYPE: Only JPEG and PNG images are supported")


def decode_and_sanitize_image(data: bytes) -> NDArray[np.uint8]:
    """Decode image bytes, strip EXIF metadata, guard MAX_PIXELS and downscale."""
    # Decode with PIL first to verify dimensions and strip EXIF
    try:
        pil_img = Image.open(io.BytesIO(data))
        w, h = pil_img.size
        if w * h > MAX_PIXELS:
            raise ValueError(
                f"PAYLOAD_TOO_LARGE: Image dimensions ({w}x{h}) exceed 50MP limit"
            )

        # Convert to RGB numpy array (stripping any EXIF)
        pil_img = pil_img.convert("RGB")
        rgb_arr = np.array(pil_img, dtype=np.uint8)
        # Convert RGB to BGR for OpenCV
        bgr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"UNPROCESSABLE_ENTITY: Failed to decode image: {e}") from e

    # Downscale if max side > MAX_SIDE_PX
    h, w = bgr.shape[:2]
    max_side = max(h, w)
    if max_side > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / float(max_side)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return bgr


def _detect_marker_calibration(
    img: NDArray[np.uint8],
) -> tuple[bool, float | None, str | None]:
    """Detect ArUco marker in the image and compute px_per_mm if valid."""
    try:
        dict_name = getattr(cv2.aruco, config.ARUCO_DICT, cv2.aruco.DICT_4X4_50)
        dictionary = cv2.aruco.getPredefinedDictionary(dict_name)
        params = cv2.aruco.DetectorParameters()
        detector = cv2.aruco.ArucoDetector(dictionary, params)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)

        if ids is not None and len(ids) > 0:
            for i, marker_id in enumerate(ids.flatten()):
                if marker_id == config.MARKER_ID:
                    pts = corners[i][0]  # shape (4, 2)
                    # Check if all corners are fully inside with 5px margin
                    h, w = img.shape[:2]
                    margin = 5
                    all_inside = bool(
                        np.all(pts[:, 0] >= margin)
                        and np.all(pts[:, 0] <= w - margin)
                        and np.all(pts[:, 1] >= margin)
                        and np.all(pts[:, 1] <= h - margin)
                    )
                    if not all_inside:
                        continue

                    # Calculate pixel perimeter/side length
                    s0 = np.linalg.norm(pts[0] - pts[1])
                    s1 = np.linalg.norm(pts[1] - pts[2])
                    s2 = np.linalg.norm(pts[2] - pts[3])
                    s3 = np.linalg.norm(pts[3] - pts[0])
                    avg_side_px = float((s0 + s1 + s2 + s3) / 4.0)

                    px_per_mm = avg_side_px / max(config.MARKER_MM, 1e-6)
                    if px_per_mm >= config.MIN_IMAGE_PX_PER_MM:
                        return (
                            True,
                            float(round(px_per_mm, 3)),
                            "accuracy assumes the marker lies in the billet top-face plane",
                        )
    except Exception as e:
        logger.debug("Marker detection error: %s", e)

    return False, None, None


def _detect_billet_contour(
    img: NDArray[np.uint8],
) -> tuple[NDArray[np.int32] | None, list[str]]:
    """Segment the billet contour and return any Review reasons."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Check contrast
    std_dev = float(np.std(gray))
    if std_dev < 15.0:
        return None, ["Low contrast image"]

    # Thresholding
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # Invert if dark background
    if np.mean(thresh) > 127:
        thresh = cv2.bitwise_not(thresh)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    min_area = max(500.0, 0.01 * (w * h))
    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]

    if not candidates:
        return None, ["No billet contour detected in image"]

    if len(candidates) > 1:
        # Check if the largest is significantly larger than the second
        candidates.sort(key=cv2.contourArea, reverse=True)
        area0 = cv2.contourArea(candidates[0])
        area1 = cv2.contourArea(candidates[1])
        if area1 > 0.4 * area0:
            return None, ["Multiple billet contours detected"]

    best_cnt = candidates[0]

    # Check if contour touches image border (within 2 px)
    pts = best_cnt.reshape(-1, 2)
    touches_border = bool(
        np.any(pts[:, 0] <= 2)
        or np.any(pts[:, 1] <= 2)
        or np.any(pts[:, 0] >= w - 3)
        or np.any(pts[:, 1] >= h - 3)
    )
    if touches_border:
        return best_cnt, ["Billet contour touches image border"]

    return best_cnt, []


def _read_id(img: NDArray[np.uint8]) -> tuple[str | None, str, float | None]:
    """Attempt OCR or QR code reading."""
    # 1. Try QR code detector
    try:
        qr_detector = cv2.QRCodeDetector()
        data, _, _ = qr_detector.detectAndDecode(img)
        if data:
            return data.strip(), "qr", 1.0
    except Exception:
        pass

    # 2. Try RapidOCR
    try:
        from rapidocr import RapidOCR

        ocr = RapidOCR()
        results, _ = ocr(img)
        if results:
            best_text = ""
            best_conf = 0.0
            for _box, text, conf in results:
                if float(conf) > best_conf and len(text.strip()) >= 3:
                    best_text = text.strip()
                    best_conf = float(conf)
            if best_text:
                return best_text, "ocr", float(round(best_conf, 2))
    except Exception:
        pass

    return None, "none", None


def _draw_annotated_upload(
    img: NDArray[np.uint8],
    contour: NDArray[np.int32] | None,
    result: UploadResult,
) -> bytes:
    """Draw clean annotations on the upload image and return JPEG bytes."""
    out = img.copy()
    h, w = out.shape[:2]

    status_colors: dict[str, tuple[int, int, int]] = {
        "Pass": (0, 200, 0),  # Green
        "Rework": (0, 165, 255),  # Amber
        "Fail": (0, 0, 255),  # Red
        "Review": (255, 120, 0),  # Blue
    }
    color = status_colors.get(result.status, (255, 255, 255))

    if contour is not None:
        cv2.drawContours(out, [contour], -1, color, 3)

        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect).astype(np.int32)
        cv2.drawContours(out, [box], 0, (255, 255, 255), 1)

    # Top HUD Bar
    hud_h = 50
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, out, 0.25, 0, out)

    # Status text
    status_str = f"STATUS: {result.status}"
    cv2.putText(
        out,
        status_str,
        (15, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        color,
        2,
        cv2.LINE_AA,
    )

    # Calib and dimensions text
    dim_str = ""
    if result.calibrated and result.length_mm and result.width_mm:
        dim_str = f"| L: {result.length_mm:.1f}mm  W: {result.width_mm:.1f}mm ({result.calibration.source})"
    elif result.length_px and result.width_px:
        dim_str = f"| L: {result.length_px:.0f}px  W: {result.width_px:.0f}px (uncalibrated)"

    if dim_str:
        cv2.putText(
            out,
            dim_str,
            (280, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )

    # Encode as JPEG
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
    success, enc = cv2.imencode(".jpg", out, encode_params)
    if not success:
        return b""
    return bytes(enc.tobytes())


def process_upload_image(
    data: bytes,
    station_camera: bool = False,
    station_calibration: Any = None,
    spec: Spec | None = None,
) -> UploadResult:
    """Process an uploaded image and return UploadResult."""
    t0 = time.monotonic()
    image_id = str(uuid.uuid4())

    # 1. Validate magic bytes and payload size
    validate_image_bytes(data)

    # 2. Decode and sanitize (EXIF stripped, size checked)
    img = decode_and_sanitize_image(data)

    # 3. Determine calibration
    is_marker_calib, px_per_mm, marker_warning = _detect_marker_calibration(img)

    calib_info: UploadCalibrationInfo
    if is_marker_calib and px_per_mm is not None:
        calib_info = UploadCalibrationInfo(
            calibrated=True,
            source="marker",
            px_per_mm=px_per_mm,
            warning=marker_warning,
        )
    elif (
        station_camera
        and station_calibration is not None
        and getattr(station_calibration, "calibrated", False)
    ):
        station_px_per_mm = getattr(station_calibration, "rect_px_per_mm", None)
        calib_info = UploadCalibrationInfo(
            calibrated=True,
            source="station",
            px_per_mm=station_px_per_mm,
            warning=None,
        )
    else:
        calib_info = UploadCalibrationInfo(
            calibrated=False,
            source="uncalibrated",
            px_per_mm=None,
            warning=None,
        )

    # 4. Contour detection & segmentation fallback
    contour, review_reasons = _detect_billet_contour(img)

    length_px: float | None = None
    width_px: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    defects: list[str] = []
    reasons: list[str] = list(review_reasons)
    status: str = "Review"

    if contour is not None:
        rect = cv2.minAreaRect(contour)
        dim1, dim2 = rect[1]
        length_px = float(round(max(dim1, dim2), 1))
        width_px = float(round(min(dim1, dim2), 1))

        if calib_info.calibrated and calib_info.px_per_mm:
            length_mm = float(round(length_px / calib_info.px_per_mm, 1))
            width_mm = float(round(width_px / calib_info.px_per_mm, 1))

            if not reasons:
                # If calibrated with spec, evaluate Pass/Rework/Fail
                if spec is not None:
                    len_err = abs(length_mm - spec.nominal_length_mm)
                    wid_err = abs(width_mm - spec.nominal_width_mm)

                    if (
                        len_err <= spec.tol_length_mm
                        and wid_err <= spec.tol_width_mm
                    ):
                        status = "Pass"
                    elif (
                        len_err <= spec.tol_length_mm * 1.5
                        and wid_err <= spec.tol_width_mm * 1.5
                    ):
                        status = "Rework"
                        reasons.append("Dimensions slightly out of tolerance")
                    else:
                        status = "Fail"
                        reasons.append("Dimensions exceed tolerance limits")
                else:
                    status = "Pass"
        else:
            # Uncalibrated: mm fields remain None, status is Review
            length_mm = None
            width_mm = None
            status = "Review"
            if not reasons:
                reasons.append("Uncalibrated image — requires visual review")

    # 5. Read Billet ID (OCR / QR)
    billet_id, id_source, ocr_conf = _read_id(img)

    # 6. Generate annotated JPEG and cache it
    proc_time_ms = float(round((time.monotonic() - t0) * 1000.0, 1))
    annotated_url = f"/inspect/image/{image_id}.jpg"

    result = UploadResult(
        image_id=image_id,
        status=status,
        calibrated=calib_info.calibrated,
        calibration=calib_info,
        billet_id=billet_id,
        id_source=id_source,
        ocr_confidence=ocr_conf,
        length_mm=length_mm,
        width_mm=width_mm,
        length_px=length_px,
        width_px=width_px,
        defects=defects,
        reasons=reasons,
        annotated_url=annotated_url,
        processing_time_ms=proc_time_ms,
    )

    annotated_jpeg = _draw_annotated_upload(img, contour, result)
    _store_image(image_id, annotated_jpeg)

    return result
