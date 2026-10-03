from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.config import CALIB_MAX_RESIDUAL_MM, DEFAULT_PLANE_HEIGHT_MM
from billetvision.schemas import CalibrationState, Roi, VerifyResult
from billetvision.vision.types import Calibration


def detect_marker(
    gray: NDArray[np.uint8],
    marker_id: int = 0,
    dict_name: str = "DICT_4X4_50",
) -> tuple[NDArray[np.float64], float] | None:
    """Detect and refine a single ArUco marker by ID."""
    dict_attr = getattr(cv2.aruco, dict_name, cv2.aruco.DICT_4X4_50)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_attr)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return None

    flat_ids = ids.flatten()
    match_indices = np.where(flat_ids == marker_id)[0]
    if len(match_indices) == 0:
        return None

    raw_corners = corners[match_indices[0]][0].astype(np.float32)

    # Subpixel refinement
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    refined_corners = cv2.cornerSubPix(gray, raw_corners.copy(), (5, 5), (-1, -1), criteria)

    # Shift caused by subpixel refinement
    refine_shift_px = float(np.mean(np.linalg.norm(refined_corners - raw_corners, axis=1)))

    return refined_corners.astype(np.float64), refine_shift_px


def detect_markers(
    gray: NDArray[np.uint8],
    dict_name: str = "DICT_4X4_50",
) -> dict[int, tuple[NDArray[np.float64], float]]:
    """Detect and refine all visible ArUco markers in the frame.

    Returns mapping of marker_id -> (4x2 refined corners_px, subpixel shift px).
    """
    dict_attr = getattr(cv2.aruco, dict_name, cv2.aruco.DICT_4X4_50)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_attr)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return {}

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    results: dict[int, tuple[NDArray[np.float64], float]] = {}

    flat_ids = ids.flatten()
    for idx, mid in enumerate(flat_ids):
        raw_corners = corners[idx][0].astype(np.float32)
        refined = cv2.cornerSubPix(gray, raw_corners.copy(), (5, 5), (-1, -1), criteria)
        shift = float(np.mean(np.linalg.norm(refined - raw_corners, axis=1)))
        results[int(mid)] = (refined.astype(np.float64), shift)

    return results


def calibrate_from_markers(
    markers: dict[int, NDArray[np.float64]],
    marker_mm: float = 80.0,
    marker_positions: dict[int, tuple[float, float]] | None = None,
    image_size: tuple[int, int] = (1920, 1080),
    marker_side_measured_mm: float | None = None,
    marker_plane_height_mm: float = DEFAULT_PLANE_HEIGHT_MM,
    calib_version: str = "cal-001",
    roi: Roi | None = None,
    rect_px_per_mm: float = 3.0,
    camera_matrix: NDArray[np.float64] | None = None,
    dist_coeffs: NDArray[np.float64] | None = None,
    created_at: float | None = None,
) -> Calibration:
    """Jointly calibrate homography using N >= 1 ArUco markers."""
    if not markers:
        raise ValueError("At least one marker must be provided for calibration.")

    if roi is None:
        roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)

    half_m = marker_mm / 2.0
    if marker_positions is None:
        if len(markers) == 1:
            mid = next(iter(markers.keys()))
            marker_positions = {mid: (0.0, 0.0)}
        else:
            default_locs = {
                0: (-100.0, -150.0),
                1: (650.0, -150.0),
                2: (650.0, 150.0),
                3: (-100.0, 150.0),
            }
            marker_positions = {mid: default_locs.get(mid, (0.0, 0.0)) for mid in markers}

    all_img_pts: list[NDArray[np.float64]] = []
    all_bed_pts: list[NDArray[np.float64]] = []
    marker_bed_corners: dict[int, NDArray[np.float64]] = {}
    sides_px_list: list[float] = []

    for mid, corners_px in markers.items():
        cx, cy = marker_positions.get(mid, (0.0, 0.0))
        bed_c = np.array(
            [
                [cx - half_m, cy - half_m],
                [cx + half_m, cy - half_m],
                [cx + half_m, cy + half_m],
                [cx - half_m, cy + half_m],
            ],
            dtype=np.float64,
        )
        marker_bed_corners[mid] = bed_c
        all_img_pts.append(corners_px)
        all_bed_pts.append(bed_c)

        for i in range(4):
            sides_px_list.append(float(np.linalg.norm(corners_px[i] - corners_px[(i + 1) % 4])))

    img_concat = np.concatenate(all_img_pts, axis=0)
    bed_concat = np.concatenate(all_bed_pts, axis=0)

    if len(markers) == 1:
        h_img_to_bed = cv2.getPerspectiveTransform(
            img_concat[:4].astype(np.float32),
            bed_concat[:4].astype(np.float32),
        ).astype(np.float64)
        baseline = "reduced-baseline"
        warning: str | None = (
            "Single marker calibration uses reduced baseline; multi-marker (N>=4) recommended."
        )
    else:
        h_img_to_bed, _ = cv2.findHomography(img_concat, bed_concat, cv2.RANSAC, 3.0)
        if h_img_to_bed is None:
            h_img_to_bed, _ = cv2.findHomography(img_concat, bed_concat, 0)
        if h_img_to_bed is None:
            raise RuntimeError("Failed to compute homography matrix from marker points.")
        h_img_to_bed = h_img_to_bed.astype(np.float64)

        if len(markers) >= 4:
            baseline = "full-baseline"
            warning = None
        else:
            baseline = "reduced-baseline"
            warning = (
                f"Only {len(markers)} markers detected; multi-marker (N>=4) recommended for full baseline."
            )

    mean_side_px = float(np.mean(sides_px_list))
    image_px_per_mm = mean_side_px / max(marker_mm, 1e-6)

    # Compute reprojection error in image pixels
    h_bed_to_img = np.linalg.inv(h_img_to_bed)
    bed_hom = np.column_stack([bed_concat, np.ones(len(bed_concat), dtype=np.float64)])
    reproj_hom = (h_bed_to_img @ bed_hom.T).T
    reproj_px = reproj_hom[:, :2] / np.maximum(reproj_hom[:, 2:], 1e-9)
    reproj_error_px = float(np.mean(np.linalg.norm(reproj_px - img_concat, axis=1)))

    # Compute residuals in mm (mapping image points to bed and comparing with true bed coords)
    img_hom = np.column_stack([img_concat, np.ones(len(img_concat), dtype=np.float64)])
    proj_bed_hom = (h_img_to_bed @ img_hom.T).T
    proj_bed = proj_bed_hom[:, :2] / np.maximum(proj_bed_hom[:, 2:], 1e-9)
    all_dists_mm = np.linalg.norm(proj_bed - bed_concat, axis=1)
    rms_residual_mm = float(np.sqrt(np.mean(np.square(all_dists_mm))))

    per_marker_residuals_mm: dict[int, float] = {}
    pt_offset = 0
    for mid in markers:
        marker_dists = all_dists_mm[pt_offset : pt_offset + 4]
        per_marker_residuals_mm[mid] = float(np.mean(marker_dists))
        pt_offset += 4

    if created_at is None:
        import time

        created_at = time.time()

    primary_corners = next(iter(markers.values()))

    # If marker_side_measured_mm is not supplied, fallback to marker_mm for default initialization
    eff_measured_side = marker_side_measured_mm if marker_side_measured_mm is not None else marker_mm

    return Calibration(
        h_img_to_bed=h_img_to_bed,
        roi=roi,
        rect_px_per_mm=rect_px_per_mm,
        image_px_per_mm=image_px_per_mm,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        marker_corners_px=primary_corners,
        marker_mm=marker_mm,
        image_size=image_size,
        reprojection_error_px=reproj_error_px,
        created_at=created_at,
        calib_version=calib_version,
        marker_plane_height_mm=marker_plane_height_mm,
        marker_side_measured_mm=eff_measured_side,
        baseline=baseline,
        residual_mm=rms_residual_mm,
        per_marker_residuals_mm=per_marker_residuals_mm,
        warning=warning,
    )


def calibrate_from_marker(
    corners_px: NDArray[np.float64],
    image_size: tuple[int, int],
    marker_mm: float = 80.0,
    roi: Roi | None = None,
    rect_px_per_mm: float = 3.0,
    camera_matrix: NDArray[np.float64] | None = None,
    dist_coeffs: NDArray[np.float64] | None = None,
    created_at: float | None = None,
    marker_side_measured_mm: float | None = None,
    marker_plane_height_mm: float = DEFAULT_PLANE_HEIGHT_MM,
    calib_version: str = "cal-001",
) -> Calibration:
    """Calibrate from a single ArUco marker."""
    return calibrate_from_markers(
        markers={0: corners_px},
        marker_mm=marker_mm,
        marker_positions={0: (0.0, 0.0)},
        image_size=image_size,
        marker_side_measured_mm=marker_side_measured_mm,
        marker_plane_height_mm=marker_plane_height_mm,
        calib_version=calib_version,
        roi=roi,
        rect_px_per_mm=rect_px_per_mm,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        created_at=created_at,
    )


def drift_mm(
    corners_px_current: NDArray[np.float64],
    corners_px_calib: NDArray[np.float64],
    image_px_per_mm: float,
) -> float:
    safe_px_per_mm = max(image_px_per_mm, 1e-6)
    corner_dists_px = np.linalg.norm(corners_px_current - corners_px_calib, axis=1)
    mean_dist_px = float(np.mean(corner_dists_px))
    return mean_dist_px / safe_px_per_mm


def load_intrinsics(
    path: str | Path,
) -> tuple[NDArray[np.float64], NDArray[np.float64], float] | None:
    p = Path(path)
    if not p.is_file():
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cam_mat = np.array(data["camera_matrix"], dtype=np.float64)
        dist_coeffs = np.array(data["dist_coeffs"], dtype=np.float64)
        rms = float(data.get("rms", 0.0))
        return cam_mat, dist_coeffs, rms
    except Exception:
        return None


def save_calibration(cal: Calibration, path: str | Path) -> None:
    """Save calibration to JSON.

    Refuses to save if measured marker side is missing/<=0 or if residual exceeds limit.
    """
    if cal.marker_side_measured_mm is None or cal.marker_side_measured_mm <= 0:
        raise ValueError("Cannot save calibration: measured marker side is missing or invalid")
    if cal.residual_mm > CALIB_MAX_RESIDUAL_MM:
        msg = (
            f"Cannot save calibration: residual {cal.residual_mm:.2f} mm "
            f"exceeds limit {CALIB_MAX_RESIDUAL_MM:.2f} mm"
        )
        raise ValueError(msg)

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "h_img_to_bed": cal.h_img_to_bed.tolist(),
        "roi": cal.roi.model_dump(),
        "rect_px_per_mm": cal.rect_px_per_mm,
        "image_px_per_mm": cal.image_px_per_mm,
        "camera_matrix": cal.camera_matrix.tolist() if cal.camera_matrix is not None else None,
        "dist_coeffs": cal.dist_coeffs.tolist() if cal.dist_coeffs is not None else None,
        "marker_corners_px": cal.marker_corners_px.tolist(),
        "marker_mm": cal.marker_mm,
        "image_size": list(cal.image_size),
        "reprojection_error_px": cal.reprojection_error_px,
        "created_at": cal.created_at,
        "calib_version": cal.calib_version,
        "marker_plane_height_mm": cal.marker_plane_height_mm,
        "marker_side_measured_mm": cal.marker_side_measured_mm,
        "baseline": cal.baseline,
        "residual_mm": cal.residual_mm,
        "per_marker_residuals_mm": cal.per_marker_residuals_mm,
        "warning": cal.warning,
    }

    temp_path = p.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(p)


def load_calibration(path: str | Path) -> Calibration | None:
    p = Path(path)
    if not p.is_file():
        return None

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        roi = Roi.model_validate(data["roi"])
        cam_mat = (
            np.array(data["camera_matrix"], dtype=np.float64)
            if data.get("camera_matrix") is not None
            else None
        )
        dist_coeffs = (
            np.array(data["dist_coeffs"], dtype=np.float64) if data.get("dist_coeffs") is not None else None
        )

        per_m_res = data.get("per_marker_residuals_mm")
        if per_m_res is not None:
            per_m_res = {int(k): float(v) for k, v in per_m_res.items()}

        return Calibration(
            h_img_to_bed=np.array(data["h_img_to_bed"], dtype=np.float64),
            roi=roi,
            rect_px_per_mm=float(data["rect_px_per_mm"]),
            image_px_per_mm=float(data["image_px_per_mm"]),
            camera_matrix=cam_mat,
            dist_coeffs=dist_coeffs,
            marker_corners_px=np.array(data["marker_corners_px"], dtype=np.float64),
            marker_mm=float(data["marker_mm"]),
            image_size=(int(data["image_size"][0]), int(data["image_size"][1])),
            reprojection_error_px=float(data["reprojection_error_px"]),
            created_at=float(data["created_at"]),
            calib_version=str(data.get("calib_version", "cal-001")),
            marker_plane_height_mm=float(data.get("marker_plane_height_mm", DEFAULT_PLANE_HEIGHT_MM)),
            marker_side_measured_mm=(
                float(data["marker_side_measured_mm"])
                if data.get("marker_side_measured_mm") is not None
                else None
            ),
            baseline=str(data.get("baseline", "reduced-baseline")),
            residual_mm=float(data.get("residual_mm", 0.0)),
            per_marker_residuals_mm=per_m_res,
            warning=data.get("warning"),
        )
    except Exception:
        return None


def calibration_to_state(
    cal: Calibration,
    has_background: bool = False,
    verify: VerifyResult | None = None,
    drift_val_mm: float | None = None,
    drift_ok: bool = True,
) -> CalibrationState:
    return CalibrationState(
        calibrated=True,
        has_background=has_background,
        has_intrinsics=cal.camera_matrix is not None,
        marker_mm=cal.marker_mm,
        image_px_per_mm=cal.image_px_per_mm,
        rect_px_per_mm=cal.rect_px_per_mm,
        roi=cal.roi,
        reprojection_error_px=cal.reprojection_error_px,
        verify=verify,
        drift_mm=drift_val_mm,
        drift_ok=drift_ok,
        created_at=cal.created_at,
        calib_version=cal.calib_version,
        baseline=cal.baseline,
        residual_mm=cal.residual_mm,
        marker_plane_height_mm=cal.marker_plane_height_mm,
        marker_side_measured_mm=cal.marker_side_measured_mm,
        warning=cal.warning,
    )
