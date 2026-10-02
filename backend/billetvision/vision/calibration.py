from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.schemas import CalibrationState, Roi, VerifyResult
from billetvision.vision.types import Calibration

if TYPE_CHECKING:
    pass


def detect_marker(
    gray: NDArray[np.uint8],
    marker_id: int = 0,
    dict_name: str = "DICT_4X4_50",
) -> tuple[NDArray[np.float64], float] | None:
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


def calibrate_from_marker(
    corners_px: NDArray[np.float64],
    image_size: tuple[int, int],
    marker_mm: float = 80.0,
    roi: Roi | None = None,
    rect_px_per_mm: float = 3.0,
    camera_matrix: NDArray[np.float64] | None = None,
    dist_coeffs: NDArray[np.float64] | None = None,
    created_at: float | None = None,
) -> Calibration:
    if roi is None:
        roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)

    half_m = marker_mm / 2.0
    corners_bed = np.array(
        [
            [-half_m, -half_m],
            [half_m, -half_m],
            [half_m, half_m],
            [-half_m, half_m],
        ],
        dtype=np.float32,
    )

    h_img_to_bed = cv2.getPerspectiveTransform(
        corners_px.astype(np.float32),
        corners_bed,
    ).astype(np.float64)

    # Calculate image_px_per_mm from marker perimeter
    sides_px = [
        np.linalg.norm(corners_px[0] - corners_px[1]),
        np.linalg.norm(corners_px[1] - corners_px[2]),
        np.linalg.norm(corners_px[2] - corners_px[3]),
        np.linalg.norm(corners_px[3] - corners_px[0]),
    ]
    mean_side_px = float(np.mean(sides_px))
    image_px_per_mm = mean_side_px / marker_mm

    # Reprojection error
    h_bed_to_img = np.linalg.inv(h_img_to_bed)
    corners_bed_hom = np.column_stack([corners_bed, np.ones(4, dtype=np.float64)])
    reproj_hom = (h_bed_to_img @ corners_bed_hom.T).T
    reproj_px = reproj_hom[:, :2] / reproj_hom[:, 2:]
    reproj_error_px = float(np.mean(np.linalg.norm(reproj_px - corners_px, axis=1)))

    if created_at is None:
        import time

        created_at = time.time()

    return Calibration(
        h_img_to_bed=h_img_to_bed,
        roi=roi,
        rect_px_per_mm=rect_px_per_mm,
        image_px_per_mm=image_px_per_mm,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        marker_corners_px=corners_px,
        marker_mm=marker_mm,
        image_size=image_size,
        reprojection_error_px=reproj_error_px,
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
        cam_mat = np.array(data["camera_matrix"], dtype=np.float64) if data.get("camera_matrix") else None
        dist_coeffs = np.array(data["dist_coeffs"], dtype=np.float64) if data.get("dist_coeffs") else None

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
    )
