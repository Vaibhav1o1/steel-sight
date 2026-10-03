from __future__ import annotations

import io
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from billetvision import config
from billetvision.schemas import Roi, Spec
from billetvision.schemas_upload import (
    GroundTruthBillet,
    GroundTruthComparison,
    TestDatasetImageItem,
    TestInspectResponse,
    UploadCalibrationInfo,
    UploadResult,
)
from billetvision.vision.calibration import calibrate_from_markers, detect_markers
from billetvision.vision.defects import detect_defects
from billetvision.vision.measure import measure
from billetvision.vision.rectify import build_rectifier
from billetvision.vision.segment import segment

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
        expired = [k for k, (_, ts) in _image_cache.items() if (now - ts) > CACHE_TTL_SECONDS]
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
    try:
        pil_img = Image.open(io.BytesIO(data))
        w, h = pil_img.size
        if w * h > MAX_PIXELS:
            raise ValueError(f"PAYLOAD_TOO_LARGE: Image dimensions ({w}x{h}) exceed 50MP limit")

        pil_img = pil_img.convert("RGB")
        rgb_arr = np.array(pil_img, dtype=np.uint8)
        bgr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"UNPROCESSABLE_ENTITY: Failed to decode image: {e}") from e

    h, w = bgr.shape[:2]
    max_side = max(h, w)
    if max_side > MAX_SIDE_PX:
        scale = MAX_SIDE_PX / float(max_side)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return bgr


def _compute_full_image_roi(h_img_to_bed: NDArray[np.float64], img_shape: tuple[int, int]) -> Roi:
    """Compute physical bed Roi (in mm) covering the full uncropped image bounds."""
    h, w = img_shape[:2]
    img_corners = np.array(
        [[0.0, 0.0, 1.0], [float(w), 0.0, 1.0], [float(w), float(h), 1.0], [0.0, float(h), 1.0]],
        dtype=np.float64,
    )
    bed_pts_hom = (h_img_to_bed @ img_corners.T).T
    denom = np.maximum(np.abs(bed_pts_hom[:, 2:]), 1e-9)
    bed_pts_mm = bed_pts_hom[:, :2] / denom

    x_min = float(np.min(bed_pts_mm[:, 0]))
    x_max = float(np.max(bed_pts_mm[:, 0]))
    y_min = float(np.min(bed_pts_mm[:, 1]))
    y_max = float(np.max(bed_pts_mm[:, 1]))

    roi_w = max(10.0, x_max - x_min)
    roi_h = max(10.0, y_max - y_min)
    return Roi(x0_mm=x_min, y0_mm=y_min, w_mm=roi_w, h_mm=roi_h)


def _detect_billet_contour(
    img: NDArray[np.uint8],
) -> tuple[NDArray[np.int32] | None, list[str]]:
    """Segment the billet contour from raw image (fallback mode) and return Review reasons."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    std_dev = float(np.std(gray))
    if std_dev < 15.0:
        return None, ["Low contrast image"]

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if np.mean(thresh) > 127:
        thresh = cv2.bitwise_not(thresh)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_area = max(500.0, 0.01 * (w * h))
    candidates = [c for c in contours if cv2.contourArea(c) >= min_area]

    if not candidates:
        return None, ["No billet contour detected in image"]

    if len(candidates) > 1:
        candidates.sort(key=cv2.contourArea, reverse=True)
        area0 = cv2.contourArea(candidates[0])
        area1 = cv2.contourArea(candidates[1])
        if area1 > 0.4 * area0:
            return None, ["Multiple billet contours detected"]

    best_cnt = candidates[0]

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


def _read_id(img: NDArray[np.uint8]) -> tuple[str | None, str, float | None, bool]:
    """Attempt OCR or QR code reading. Returns (billet_id, source, ocr_conf, qr_detected)."""
    qr_detected = False
    qr_text: str | None = None

    # 1. Try QR code detector
    try:
        qr_detector = cv2.QRCodeDetector()
        data, _, _ = qr_detector.detectAndDecode(img)
        if data and data.strip():
            qr_text = data.strip()
            qr_detected = True
    except Exception:
        pass

    if qr_text:
        return qr_text, "qr", 1.0, True

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
                return best_text, "ocr", float(round(best_conf, 2)), qr_detected
    except Exception:
        pass

    return None, "none", None, qr_detected


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

    hud_h = 50
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, hud_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, out, 0.25, 0, out)

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
    """Process an uploaded image using calibration, rectification, and measurement."""
    t0 = time.monotonic()
    image_id = str(uuid.uuid4())

    # 1. Validate magic bytes and payload size
    validate_image_bytes(data)

    # 2. Decode and sanitize (EXIF stripped, size checked)
    img = decode_and_sanitize_image(data)
    h, w = img.shape[:2]

    # Effective spec fallback (authoritative FLAT-500x100 from camera.json)
    eff_spec = spec or Spec(
        id="FLAT-500x100",
        name="FLAT-500x100",
        nominal_length_mm=500.0,
        nominal_width_mm=100.0,
        nominal_height_mm=None,
        tol_length_mm=5.0,
        tol_width_mm=2.0,
        cs_var_warn_pct=3.0,
        cs_var_fail_pct=5.0,
        notch_min_mm=5.0,
        camber_max_mm=5.0,
        taper_max_mm=5.0,
        id_template="*",
        min_area_factor=0.4,
        max_area_factor=1.6,
        active=1,
        created_at=0.0,
    )

    # 3. Detect ArUco markers for marker-based calibration
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    markers = detect_markers(gray, dict_name=config.ARUCO_DICT)

    length_px: float | None = None
    width_px: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    defects: list[str] = []
    defect_type: str | None = None
    defect_size_mm: float | None = None
    reasons: list[str] = []
    status: str = "Review"
    drawn_contour: NDArray[np.int32] | None = None
    crop_for_id: NDArray[np.uint8] | None = None

    calib_info: UploadCalibrationInfo

    # ── Path A: Marker-based calibration & rectification ───────────────
    if markers and config.MARKER_ID in markers:
        try:
            marker_pts = markers[config.MARKER_ID][0]
            # Compute initial homography to derive full-image physical ROI
            init_cal = calibrate_from_markers(
                {config.MARKER_ID: marker_pts},
                marker_mm=config.MARKER_MM,
            )
            full_roi = _compute_full_image_roi(init_cal.h_img_to_bed, (h, w))

            # Calibrate with full-image physical ROI
            cal = calibrate_from_markers(
                {config.MARKER_ID: marker_pts},
                marker_mm=config.MARKER_MM,
                roi=full_roi,
                rect_px_per_mm=init_cal.rect_px_per_mm,
            )
            rectifier = build_rectifier(cal)
            rect_bgr = rectifier.apply(img)
            rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)

            # Segment billet on rectified frame
            detections = segment(
                rect_gray,
                background=None,
                spec=eff_spec,
                roi=cal.roi,
                rect_px_per_mm=cal.rect_px_per_mm,
            )

            if detections:
                det = max(detections, key=lambda d: d.area_mm2)
                meas, crop_bgr = measure(
                    det,
                    rect_gray,
                    rect_bgr,
                    roi=cal.roi,
                    rect_px_per_mm=cal.rect_px_per_mm,
                )
                defect_res = detect_defects(meas, eff_spec)

                length_mm = float(round(meas.length_mm, 1))
                width_mm = float(round(meas.width_mm, 1))
                length_px = float(round(meas.length_mm * cal.image_px_per_mm, 1))
                width_px = float(round(meas.width_mm * cal.image_px_per_mm, 1))
                crop_for_id = crop_bgr

                defects = [d.value if hasattr(d, "value") else str(d) for d in defect_res.defects]
                if defects:
                    defect_type = defects[0]
                    if defect_type == "camber":
                        defect_size_mm = float(round(defect_res.camber_mm, 2))
                    elif defect_type == "taper":
                        defect_size_mm = float(round(defect_res.taper_mm, 2))
                    elif defect_type == "notch":
                        defect_size_mm = float(round(defect_res.notch_depth_mm, 2))
                    else:
                        defect_size_mm = float(round(defect_res.cs_var_pct, 2))

                # Map rectified contour back to raw image pixels for annotation
                raw_pts = rectifier.rect_to_image(det.contour_px.astype(np.float64))
                drawn_contour = raw_pts.astype(np.int32).reshape(-1, 1, 2)

                # Evaluate Pass / Rework / Fail strictly aligned with decide.py rules
                min_l = eff_spec.nominal_length_mm - eff_spec.tol_length_mm
                max_l = eff_spec.nominal_length_mm + eff_spec.tol_length_mm
                min_w = eff_spec.nominal_width_mm - eff_spec.tol_width_mm
                max_w = eff_spec.nominal_width_mm + eff_spec.tol_width_mm

                has_fail = False
                has_rework = False

                # 1. Length checks
                if length_mm < min_l:
                    d = min_l - length_mm
                    reasons.append(f"Length {length_mm:.1f} mm is {d:.1f} mm below minimum {min_l:.1f} mm")
                    has_fail = True
                elif length_mm > max_l:
                    d = length_mm - max_l
                    reasons.append(
                        f"Length {length_mm:.1f} mm is {d:.1f} mm over maximum {max_l:.1f} mm (trim)"
                    )
                    has_rework = True

                # 2. Width checks
                if width_mm < min_w:
                    d = min_w - width_mm
                    reasons.append(f"Width {width_mm:.1f} mm is {d:.1f} mm below minimum {min_w:.1f} mm")
                    has_fail = True
                elif width_mm > max_w:
                    d = width_mm - max_w
                    reasons.append(
                        f"Width {width_mm:.1f} mm is {d:.1f} mm over maximum {max_w:.1f} mm (planish)"
                    )
                    has_rework = True

                # 3. Defect checks
                if "notch" in defects:
                    reasons.append(f"Notch {defect_res.notch_depth_mm:.1f} mm deep detected")
                    has_fail = True
                if defect_res.width_variation_pct >= eff_spec.cs_var_fail_pct:
                    reasons.append(
                        f"Cross-section variation {defect_res.width_variation_pct:.1f}% "
                        f">= {eff_spec.cs_var_fail_pct:.1f}%"
                    )
                    has_fail = True
                elif defect_res.width_variation_pct >= eff_spec.cs_var_warn_pct:
                    reasons.append(
                        f"Cross-section variation {defect_res.width_variation_pct:.1f}% "
                        f">= {eff_spec.cs_var_warn_pct:.1f}%"
                    )
                    has_rework = True

                if "taper" in defects:
                    reasons.append(f"Taper {defect_res.taper_mm:.1f} mm detected")
                    has_rework = True
                if "bulge" in defects:
                    reasons.append("Bulge defect detected")
                    has_rework = True
                if "camber" in defects:
                    reasons.append(f"Camber {defect_res.camber_mm:.1f} mm detected")
                    has_rework = True

                if has_fail:
                    status = "Fail"
                elif has_rework:
                    status = "Rework"
                else:
                    status = "Pass"
                    reasons.append("Within dimensional tolerance")

                calib_info = UploadCalibrationInfo(
                    calibrated=True,
                    source="marker",
                    px_per_mm=float(round(cal.image_px_per_mm, 3)),
                    warning="accuracy assumes the marker lies in the billet top-face plane",
                )
            else:
                # Rectified segmentation found no candidate; fallback to raw contour
                calib_info = UploadCalibrationInfo(
                    calibrated=True,
                    source="marker",
                    px_per_mm=float(round(cal.image_px_per_mm, 3)),
                    warning="accuracy assumes the marker lies in the billet top-face plane",
                )
                raw_cnt, review_reasons = _detect_billet_contour(img)
                reasons.extend(review_reasons)
                if raw_cnt is not None:
                    drawn_contour = raw_cnt
                    rect = cv2.minAreaRect(raw_cnt)
                    dim1, dim2 = rect[1]
                    length_px = float(round(max(dim1, dim2), 1))
                    width_px = float(round(min(dim1, dim2), 1))
                    length_mm = float(round(length_px / cal.image_px_per_mm, 1))
                    width_mm = float(round(width_px / cal.image_px_per_mm, 1))
                    status = "Review"
                else:
                    status = "Review"
                    if not reasons:
                        reasons.append("No billet contour detected in image")
        except Exception as e:
            logger.warning("Marker calibration/rectification failed: %s", e)
            calib_info = UploadCalibrationInfo(
                calibrated=False,
                source="uncalibrated",
                px_per_mm=None,
                warning=None,
            )
    # ── Path B: Station camera with active calibration ─────────────────
    elif (
        station_camera
        and station_calibration is not None
        and getattr(station_calibration, "calibrated", False)
    ):
        station_px_per_mm = getattr(station_calibration, "rect_px_per_mm", None) or getattr(
            station_calibration, "image_px_per_mm", None
        )
        calib_info = UploadCalibrationInfo(
            calibrated=True,
            source="station",
            px_per_mm=station_px_per_mm,
            warning=None,
        )
        raw_cnt, review_reasons = _detect_billet_contour(img)
        reasons.extend(review_reasons)
        if raw_cnt is not None:
            drawn_contour = raw_cnt
            rect = cv2.minAreaRect(raw_cnt)
            dim1, dim2 = rect[1]
            length_px = float(round(max(dim1, dim2), 1))
            width_px = float(round(min(dim1, dim2), 1))
            bx, by, bw, bh = cv2.boundingRect(raw_cnt)
            crop_for_id = img[by : by + bh, bx : bx + bw]
            if station_px_per_mm:
                length_mm = float(round(length_px / station_px_per_mm, 1))
                width_mm = float(round(width_px / station_px_per_mm, 1))
                status = "Review"
            else:
                status = "Review"
        else:
            status = "Review"
            if not reasons:
                reasons.append("No billet contour detected in image")
    # ── Path C: Uncalibrated fallback ──────────────────────────────────
    else:
        calib_info = UploadCalibrationInfo(
            calibrated=False,
            source="uncalibrated",
            px_per_mm=None,
            warning=None,
        )
        raw_cnt, review_reasons = _detect_billet_contour(img)
        reasons.extend(review_reasons)
        if raw_cnt is not None:
            drawn_contour = raw_cnt
            rect = cv2.minAreaRect(raw_cnt)
            dim1, dim2 = rect[1]
            length_px = float(round(max(dim1, dim2), 1))
            width_px = float(round(min(dim1, dim2), 1))
            bx, by, bw, bh = cv2.boundingRect(raw_cnt)
            crop_for_id = img[by : by + bh, bx : bx + bw]
        length_mm = None
        width_mm = None
        status = "Review"
        if not reasons:
            reasons.append("Uncalibrated image — requires visual review")

    # 4. Read Billet ID (OCR / QR) strictly from the selected billet crop
    billet_id, id_source, ocr_conf, qr_detected = (
        _read_id(crop_for_id)
        if crop_for_id is not None and crop_for_id.size > 0
        else (None, "none", None, False)
    )

    # 5. Calculate dimensional deviations and pass/fail indicators
    length_dev_mm: float | None = None
    length_abs_dev_mm: float | None = None
    length_passed: bool | None = None
    width_dev_mm: float | None = None
    width_abs_dev_mm: float | None = None
    width_passed: bool | None = None

    if length_mm is not None:
        length_dev_mm = float(round(length_mm - eff_spec.nominal_length_mm, 2))
        length_abs_dev_mm = float(round(abs(length_dev_mm), 2))
        length_passed = length_abs_dev_mm <= eff_spec.tol_length_mm

    if width_mm is not None:
        width_dev_mm = float(round(width_mm - eff_spec.nominal_width_mm, 2))
        width_abs_dev_mm = float(round(abs(width_dev_mm), 2))
        width_passed = width_abs_dev_mm <= eff_spec.tol_width_mm

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
        qr_detected=qr_detected,
        length_mm=length_mm,
        width_mm=width_mm,
        nominal_length_mm=eff_spec.nominal_length_mm,
        nominal_width_mm=eff_spec.nominal_width_mm,
        tol_length_mm=eff_spec.tol_length_mm,
        tol_width_mm=eff_spec.tol_width_mm,
        length_dev_mm=length_dev_mm,
        length_abs_dev_mm=length_abs_dev_mm,
        length_passed=length_passed,
        width_dev_mm=width_dev_mm,
        width_abs_dev_mm=width_abs_dev_mm,
        width_passed=width_passed,
        length_px=length_px,
        width_px=width_px,
        defects=defects,
        defect_type=defect_type,
        defect_size_mm=defect_size_mm,
        reasons=reasons,
        annotated_url=annotated_url,
        processing_time_ms=proc_time_ms,
    )

    annotated_jpeg = _draw_annotated_upload(img, drawn_contour, result)
    _store_image(image_id, annotated_jpeg)

    return result


# ── Test Dataset Helpers ───────────────────────────────────────────────


def _get_dataset_paths() -> tuple[Path | None, Path | None, Path | None]:
    """Find data_pack root, camera.json, and scenes.json."""
    proj_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        Path("D:/steel-sight/Code_Utsava X.O/bv_part1_images/data_pack"),
        proj_root / "Code_Utsava X.O" / "bv_part1_images" / "data_pack",
        Path("data_pack"),
    ]
    for p in candidates:
        cam_file = p / "camera.json"
        scenes_file = p / "images" / "scenes.json"
        if cam_file.is_file() and scenes_file.is_file():
            return p, cam_file, scenes_file

    return None, None, None


def load_test_dataset_spec() -> Spec:
    """Load authoritative spec from camera.json if available, or fallback."""
    _, cam_file, _ = _get_dataset_paths()
    if cam_file and cam_file.is_file():
        try:
            with open(cam_file, encoding="utf-8") as f:
                data = json.load(f)
            sp = data.get("spec", {})
            return Spec(
                id=sp.get("id", "FLAT-500x100"),
                name=sp.get("id", "FLAT-500x100"),
                nominal_length_mm=float(sp.get("nominal_length_mm", 500.0)),
                nominal_width_mm=float(sp.get("nominal_width_mm", 100.0)),
                nominal_height_mm=None,
                tol_length_mm=float(sp.get("tol_length_mm", 5.0)),
                tol_width_mm=float(sp.get("tol_width_mm", 2.0)),
                cs_var_warn_pct=3.0,
                cs_var_fail_pct=5.0,
                notch_min_mm=5.0,
                camber_max_mm=5.0,
                taper_max_mm=5.0,
                id_template=sp.get("id_template", "A99-9999"),
                min_area_factor=0.4,
                max_area_factor=1.6,
                active=True,
            )
        except Exception as e:
            logger.warning("Failed to parse camera.json spec: %s", e)

    return Spec(
        id="FLAT-500x100",
        name="FLAT-500x100",
        nominal_length_mm=500.0,
        nominal_width_mm=100.0,
        nominal_height_mm=None,
        tol_length_mm=5.0,
        tol_width_mm=2.0,
        cs_var_warn_pct=3.0,
        cs_var_fail_pct=5.0,
        notch_min_mm=5.0,
        camber_max_mm=5.0,
        taper_max_mm=5.0,
        id_template="A99-9999",
        min_area_factor=0.4,
        max_area_factor=1.6,
        active=True,
    )


def list_test_dataset_images() -> list[TestDatasetImageItem]:
    """List available test dataset images with metadata from scenes.json."""
    _, _, scenes_file = _get_dataset_paths()
    if not scenes_file or not scenes_file.is_file():
        return []

    try:
        with open(scenes_file, encoding="utf-8") as f:
            scenes = json.load(f)

        items: list[TestDatasetImageItem] = []
        for s in scenes:
            img_name = s.get("image", "")
            variant = s.get("variant", "unknown")
            billets = s.get("billets", [])
            b0 = billets[0] if billets else {}

            items.append(
                TestDatasetImageItem(
                    filename=img_name,
                    variant=variant,
                    expected_status=b0.get("expected_status", "Review"),
                    billet_id=b0.get("id_text"),
                    length_mm=float(b0.get("length_mm", 0.0)),
                    width_mm=float(b0.get("width_mm", 0.0)),
                    defect=b0.get("defect"),
                    defect_size_mm=float(b0.get("defect_size_mm", 0.0)),
                    qr=bool(b0.get("qr", False)),
                )
            )
        return items
    except Exception as e:
        logger.warning("Error reading scenes.json: %s", e)
        return []


def inspect_test_dataset_image(image_name: str) -> TestInspectResponse:
    """Inspect a test dataset image and compute ground truth comparison."""
    data_pack_dir, _, scenes_file = _get_dataset_paths()
    if not data_pack_dir:
        raise ValueError("Test dataset data_pack directory not found")

    img_path = data_pack_dir / "images" / image_name
    if not img_path.is_file():
        raise FileNotFoundError(f"Test image not found: {image_name}")

    with open(img_path, "rb") as f:
        img_bytes = f.read()

    spec = load_test_dataset_spec()
    system_res = process_upload_image(img_bytes, station_camera=False, spec=spec)

    # Extract ground truth from scenes.json
    gt_billet: GroundTruthBillet | None = None
    if scenes_file and scenes_file.is_file():
        try:
            with open(scenes_file, encoding="utf-8") as f:
                scenes = json.load(f)
            for s in scenes:
                if s.get("image") == image_name:
                    billets = s.get("billets", [])
                    if (
                        len(billets) > 1
                        and system_res.length_mm is not None
                        and system_res.width_mm is not None
                    ):
                        # Match the ground-truth billet that corresponds to the segmented one
                        b = min(
                            billets,
                            key=lambda x: (
                                abs(float(x.get("length_mm", 0.0)) - (system_res.length_mm or 0.0))
                                + abs(float(x.get("width_mm", 0.0)) - (system_res.width_mm or 0.0))
                            ),
                        )
                    else:
                        b = billets[0] if billets else {}

                    gt_billet = GroundTruthBillet(
                        id_text=b.get("id_text"),
                        length_mm=float(b.get("length_mm", 0.0)),
                        width_mm=float(b.get("width_mm", 0.0)),
                        qr=bool(b.get("qr", False)),
                        defect=b.get("defect"),
                        defect_size_mm=float(b.get("defect_size_mm", 0.0)),
                        expected_status=b.get("expected_status"),
                    )
                    break
        except Exception as e:
            logger.warning("Error loading ground truth for %s: %s", image_name, e)

    # Compute comparison
    comparison: GroundTruthComparison | None = None
    if gt_billet is not None:
        status_match = (
            system_res.status.lower() == gt_billet.expected_status.lower()
            if gt_billet.expected_status
            else None
        )

        len_delta = (
            float(round(system_res.length_mm - gt_billet.length_mm, 2))
            if system_res.length_mm is not None and gt_billet.length_mm is not None
            else None
        )

        wid_delta = (
            float(round(system_res.width_mm - gt_billet.width_mm, 2))
            if system_res.width_mm is not None and gt_billet.width_mm is not None
            else None
        )

        sys_defect = system_res.defect_type.lower() if system_res.defect_type else None
        gt_defect = gt_billet.defect.lower() if gt_billet.defect else None
        defect_match = sys_defect == gt_defect

        defect_size_delta = (
            float(round(system_res.defect_size_mm - gt_billet.defect_size_mm, 2))
            if system_res.defect_size_mm is not None and gt_billet.defect_size_mm is not None
            else None
        )

        id_match = (
            system_res.billet_id.upper() == gt_billet.id_text.upper()
            if system_res.billet_id and gt_billet.id_text
            else None
        )

        qr_match = system_res.qr_detected == gt_billet.qr if gt_billet.qr is not None else None

        comparison = GroundTruthComparison(
            status_match=status_match,
            length_delta_mm=len_delta,
            width_delta_mm=wid_delta,
            defect_type_match=defect_match,
            defect_size_delta_mm=defect_size_delta,
            id_match=id_match,
            qr_match=qr_match,
        )

    return TestInspectResponse(
        system_result=system_res,
        ground_truth=gt_billet,
        comparison=comparison,
        is_test_dataset=True,
    )
