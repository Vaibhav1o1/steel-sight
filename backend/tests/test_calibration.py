from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from billetvision.schemas import CalibrationState
from billetvision.vision.calibration import (
    calibrate_from_marker,
    calibration_to_state,
    detect_marker,
    drift_mm,
    load_calibration,
    load_intrinsics,
    save_calibration,
)
from billetvision.vision.synth import CameraSpec, Effects, SceneSpec, render_scene


def test_calibration_from_synthetic_marker() -> None:
    rng = np.random.default_rng(42)
    spec = SceneSpec(
        billets=(),
        camera=CameraSpec(),
        effects=Effects(noise_sigma=0.0),
        with_marker=True,
    )
    img, gt = render_scene(spec, rng)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    res = detect_marker(gray, marker_id=0)
    assert res is not None, "Marker must be detected on clean synthetic frame"
    corners_px, shift_px = res
    assert shift_px < 1.0

    cal = calibrate_from_marker(corners_px, (1920, 1080), marker_mm=80.0)

    # 1. image_px_per_mm within 2% of truth
    rel_scale_err = abs(cal.image_px_per_mm - gt.image_px_per_mm) / gt.image_px_per_mm
    assert rel_scale_err < 0.02, f"Scale relative error {rel_scale_err:.4f} exceeds 2%"

    # 2. Homography maps known bed points to within 0.3 mm
    test_pts_bed = np.array(
        [
            [100.0, 0.0, 1.0],
            [200.0, 0.0, 1.0],
            [300.0, 0.0, 1.0],
        ]
    )
    img_pts_hom = (gt.h_bed_to_img @ test_pts_bed.T).T
    img_pts_px = img_pts_hom[:, :2] / img_pts_hom[:, 2:]
    img_pts_h = np.column_stack([img_pts_px, np.ones(len(img_pts_px))])

    rec_bed_hom = (cal.h_img_to_bed @ img_pts_h.T).T
    rec_bed = rec_bed_hom[:, :2] / rec_bed_hom[:, 2:]
    errs_mm = np.linalg.norm(rec_bed - test_pts_bed[:, :2], axis=1)

    for i, err in enumerate(errs_mm):
        assert err < 0.3, f"Point {test_pts_bed[i, :2]} mapping error {err:.4f} mm exceeds 0.3 mm"


def test_drift_detection() -> None:
    rng = np.random.default_rng(99)
    spec = SceneSpec(
        billets=(),
        camera=CameraSpec(),
        effects=Effects(noise_sigma=0.0),
        with_marker=True,
    )
    img, _ = render_scene(spec, rng)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    res = detect_marker(gray)
    assert res is not None
    corners_calib, _ = res
    image_px_per_mm = 2.5

    # Test 3 mm physical shift
    shift_px = 3.0 * image_px_per_mm
    shifted_corners = corners_calib + np.array([[shift_px, 0.0]])

    measured_drift = drift_mm(shifted_corners, corners_calib, image_px_per_mm)
    assert abs(measured_drift - 3.0) < 0.01, f"Expected drift ≈ 3.0 mm, got {measured_drift:.4f}"

    # Zero shift
    assert drift_mm(corners_calib, corners_calib, image_px_per_mm) == 0.0


def test_calibration_persistence_roundtrip(tmp_path: Path) -> None:
    corners = np.array(
        [[120.0, 440.0], [320.0, 440.0], [320.0, 640.0], [120.0, 640.0]],
        dtype=np.float64,
    )
    cal = calibrate_from_marker(corners, (1920, 1080), marker_mm=80.0)

    cal_path = tmp_path / "calibration.json"
    save_calibration(cal, cal_path)
    assert cal_path.is_file()

    loaded = load_calibration(cal_path)
    assert loaded is not None
    assert np.allclose(loaded.h_img_to_bed, cal.h_img_to_bed)
    assert np.allclose(loaded.marker_corners_px, cal.marker_corners_px)
    assert loaded.marker_mm == cal.marker_mm
    assert loaded.image_size == cal.image_size
    assert loaded.rect_px_per_mm == cal.rect_px_per_mm
    assert loaded.roi.x0_mm == cal.roi.x0_mm


def test_load_intrinsics(tmp_path: Path) -> None:
    data = {
        "camera_matrix": np.eye(3).tolist(),
        "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
        "rms": 0.12,
    }
    p = tmp_path / "intrinsics.json"
    p.write_text(json.dumps(data))

    res = load_intrinsics(p)
    assert res is not None
    mtx, dist, rms = res
    assert mtx.shape == (3, 3)
    assert dist.shape == (5,)
    assert rms == 0.12

    # Missing file returns None
    assert load_intrinsics(tmp_path / "nonexistent.json") is None


def test_calibration_to_state() -> None:
    corners = np.array(
        [[100.0, 400.0], [300.0, 400.0], [300.0, 600.0], [100.0, 600.0]],
        dtype=np.float64,
    )
    cal = calibrate_from_marker(corners, (1920, 1080), marker_mm=80.0)
    state = calibration_to_state(cal, has_background=True, drift_val_mm=0.2, drift_ok=True)

    assert isinstance(state, CalibrationState)
    assert state.calibrated is True
    assert state.has_background is True
    assert state.drift_mm == 0.2
    assert state.drift_ok is True
