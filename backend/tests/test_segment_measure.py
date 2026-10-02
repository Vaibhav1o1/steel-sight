from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision.schemas import Roi, Spec
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.measure import measure
from billetvision.vision.rectify import Rectifier, build_rectifier, glare_mask, rect_to_image
from billetvision.vision.segment import segment
from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    random_scene,
    render_scene,
)


@pytest.fixture
def default_spec() -> Spec:
    return Spec(
        id="test_spec",
        name="Test Billet Spec",
        nominal_length_mm=400.0,
        nominal_width_mm=100.0,
        tol_length_mm=5.0,
        tol_width_mm=2.0,
        cs_var_warn_pct=3.0,
        cs_var_fail_pct=5.0,
        notch_min_mm=5.0,
        camber_max_mm=3.0,
        taper_max_mm=3.0,
        id_template="H24-1187",
        min_area_factor=0.35,
        max_area_factor=1.6,
    )


def _setup_rectifier(bg_img: np.ndarray) -> Rectifier:
    corners, _ = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]
    cal = calibrate_from_marker(corners, (1920, 1080))
    return build_rectifier(cal)


def test_rectifier_without_intrinsics_and_rect_to_image() -> None:
    rng = np.random.default_rng(42)
    img, gt = render_scene(random_scene(rng, "clean"), rng)
    rectifier = _setup_rectifier(img)

    rect_bgr = rectifier.apply(img)
    expected_w = int(round(rectifier.roi.w_mm * rectifier.rect_px_per_mm))
    expected_h = int(round(rectifier.roi.h_mm * rectifier.rect_px_per_mm))
    assert rect_bgr.shape == (expected_h, expected_w, 3)

    b = gt.billets[0]
    u = (b.center_mm[0] - rectifier.roi.x0_mm) * rectifier.rect_px_per_mm
    v = (b.center_mm[1] - rectifier.roi.y0_mm) * rectifier.rect_px_per_mm
    img_pt = rect_to_image(rectifier, np.array([[u, v]], dtype=np.float64))

    ix, iy = int(round(img_pt[0, 0])), int(round(img_pt[0, 1]))
    assert 0 <= ix < 1920 and 0 <= iy < 1080
    assert img[iy, ix].mean() > 100


def test_rectifier_with_intrinsics() -> None:
    camera_matrix = np.array(
        [[2000.0, 0.0, 960.0], [0.0, 2000.0, 540.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    dist_coeffs = np.array([-0.05, 0.01, 0.001, 0.001, 0.0], dtype=np.float64)

    rng = np.random.default_rng(10)
    img, _ = render_scene(random_scene(rng, "clean"), rng)
    corners, _ = detect_marker(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]

    cal = calibrate_from_marker(corners, (1920, 1080), camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    rectifier = build_rectifier(cal)
    assert rectifier.map_x is not None and rectifier.map_y is not None

    rect_bgr = rectifier.apply(img)
    assert rect_bgr.shape == (
        int(round(cal.roi.h_mm * cal.rect_px_per_mm)),
        int(round(cal.roi.w_mm * cal.rect_px_per_mm)),
        3,
    )
    img_pt = rectifier.rect_to_image(np.array([[300.0, 400.0]], dtype=np.float64))
    assert img_pt.shape == (1, 2) and np.all(np.isfinite(img_pt))


def test_glare_mask() -> None:
    gray = np.full((100, 100), 120, dtype=np.uint8)
    cv2.circle(gray, (50, 50), 5, 255, -1)

    mask = glare_mask(gray, saturation_level=250)
    assert mask.shape == (100, 100)
    assert mask[50, 50] == 255
    assert mask[50, 50 + 7] == 255
    assert mask[50, 50 + 15] == 0


@pytest.mark.parametrize(
    "variant",
    ["clean", "dim", "bright", "gradient", "noise", "blur", "dust", "scale", "glare"],
)
def test_one_detection_per_billet_across_all_variants(variant: str, default_spec: Spec) -> None:
    rng = np.random.default_rng(123)
    scene = random_scene(rng, variant)
    img, gt = render_scene(scene, rng)

    bg_scene = SceneSpec(billets=(), camera=CameraSpec(), effects=scene.effects, with_marker=True)
    bg_img, _ = render_scene(bg_scene, np.random.default_rng(123))

    rectifier = _setup_rectifier(bg_img)
    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets_with_bg = segment(
        rect_gray, bg_gray, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    assert len(dets_with_bg) == len(gt.billets)

    dets_no_bg = segment(
        rect_gray, None, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    assert len(dets_no_bg) == len(gt.billets)

    for d in dets_with_bg:
        assert d.rough_length_mm > 0 and d.rough_width_mm > 0
        assert -90.0 < d.angle_deg <= 90.0 and not d.merged


def test_full_inside_false_for_billet_crossing_roi_edge(default_spec: Spec) -> None:
    billet = BilletSpec(
        center_mm=(100.0, 0.0),
        angle_deg=0.0,
        length_mm=400.0,
        width_mm=100.0,
        id_text="H24-1187",
        qr=False,
        defect=None,
        defect_size_mm=0.0,
    )
    rng = np.random.default_rng(42)
    img, _ = render_scene(
        SceneSpec(billets=(billet,), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )
    bg_img, _ = render_scene(
        SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )

    rectifier = _setup_rectifier(bg_img)
    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(
        rect_gray, bg_gray, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    assert len(dets) == 1 and not dets[0].full_inside


def test_merged_true_for_two_touching_billets(default_spec: Spec) -> None:
    b1 = BilletSpec(
        center_mm=(350.0, -50.0),
        angle_deg=0.0,
        length_mm=400.0,
        width_mm=100.0,
        id_text="H24-1187",
        qr=False,
        defect=None,
        defect_size_mm=0.0,
    )
    b2 = BilletSpec(
        center_mm=(350.0, 50.0),
        angle_deg=0.0,
        length_mm=400.0,
        width_mm=100.0,
        id_text="H24-1188",
        qr=False,
        defect=None,
        defect_size_mm=0.0,
    )
    rng = np.random.default_rng(42)
    img, _ = render_scene(
        SceneSpec(billets=(b1, b2), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )
    bg_img, _ = render_scene(
        SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )

    rectifier = _setup_rectifier(bg_img)
    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(
        rect_gray, bg_gray, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    assert len(dets) == 1 and dets[0].merged is True


def test_hand_sized_blobs_rejected(default_spec: Spec) -> None:
    roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)
    r = 3.0
    w_px, h_px = int(round(roi.w_mm * r)), int(round(roi.h_mm * r))
    center_px = (int(w_px // 2), int(h_px // 2))

    # 1. Low aspect ratio blob (150x130 mm, aspect 1.15 < 1.5)
    rect_gray = np.full((h_px, w_px), 28, dtype=np.uint8)
    cv2.ellipse(rect_gray, center_px, (int(150.0 * r) // 2, int(130.0 * r) // 2), 0, 0, 360, 180, -1)
    assert (
        len(
            segment(
                rect_gray,
                np.full((h_px, w_px), 28, dtype=np.uint8),
                default_spec,
                roi=roi,
                rect_px_per_mm=r,
            )
        )
        == 0
    )

    # 2. Small blob below min area factor
    rect_gray2 = np.full((h_px, w_px), 28, dtype=np.uint8)
    sw, sh = int(100.0 * r) // 2, int(40.0 * r) // 2
    cv2.rectangle(
        rect_gray2, (center_px[0] - sw, center_px[1] - sh), (center_px[0] + sw, center_px[1] + sh), 180, -1
    )
    assert (
        len(
            segment(
                rect_gray2,
                np.full((h_px, w_px), 28, dtype=np.uint8),
                default_spec,
                roi=roi,
                rect_px_per_mm=r,
            )
        )
        == 0
    )


def test_measurement_on_clean_scene_within_half_percent(default_spec: Spec) -> None:
    rng = np.random.default_rng(1)
    img, gt = render_scene(random_scene(rng, "clean"), rng)
    bg_img, _ = render_scene(
        SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )

    rectifier = _setup_rectifier(bg_img)
    rect_bgr = rectifier.apply(img)
    rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(
        rect_gray, bg_gray, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    assert len(dets) == 1
    det = dets[0]
    gt_b = gt.billets[0]

    meas, upright_bgr = measure(
        det,
        rect_gray,
        rect_bgr,
        glare=None,
        roi=rectifier.roi,
        rect_px_per_mm=rectifier.rect_px_per_mm,
    )

    # Within 0.5% of truth
    len_err_pct = abs(meas.length_mm - gt_b.length_mm) / gt_b.length_mm * 100.0
    wid_err_pct = abs(meas.width_mm - gt_b.width_mm) / gt_b.width_mm * 100.0
    assert len_err_pct <= 0.5, f"Length error {len_err_pct:.3f}% exceeds 0.5%"
    assert wid_err_pct <= 0.5, f"Width error {wid_err_pct:.3f}% exceeds 0.5%"

    # 21 slice profile
    assert len(meas.width_profile_mm) == 21
    assert all(np.isfinite(w) for w in meas.width_profile_mm)
    assert meas.valid_slices == 21

    # Dense profile and crops
    assert len(meas.dense_pos_mm) > 500
    assert len(meas.dense_top_mm) == len(meas.dense_pos_mm)
    assert meas.sharpness > 0
    assert upright_bgr.shape[0] > 0 and upright_bgr.shape[1] > 0


def test_failed_slice_interpolation_with_glare(default_spec: Spec) -> None:
    rng = np.random.default_rng(1)
    img, _ = render_scene(random_scene(rng, "clean"), rng)
    bg_img, _ = render_scene(
        SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True), rng
    )

    rectifier = _setup_rectifier(bg_img)
    rect_bgr = rectifier.apply(img)
    rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(
        rect_gray, bg_gray, default_spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm
    )
    det = dets[0]

    # Create artificial glare mask covering the edge of slice 10 (middle of the billet)
    r = rectifier.rect_px_per_mm
    c_px = np.array(
        [
            (det.center_mm[0] - rectifier.roi.x0_mm) * r,
            (det.center_mm[1] - rectifier.roi.y0_mm) * r,
        ]
    )
    theta_rad = np.radians(det.angle_deg)
    v = np.array([-np.sin(theta_rad), np.cos(theta_rad)])
    edge_px = c_px + (det.rough_width_mm * r / 2.0) * v

    glare = np.zeros_like(rect_gray)
    cv2.circle(
        glare,
        (int(round(edge_px[0])), int(round(edge_px[1]))),
        int(round(15.0 * r)),
        255,
        -1,
    )

    meas, _ = measure(
        det,
        rect_gray,
        rect_bgr,
        glare=glare,
        roi=rectifier.roi,
        rect_px_per_mm=rectifier.rect_px_per_mm,
    )

    # Glare must invalidate at least one slice
    assert meas.valid_slices < 21
    # Profile must still be 21 values, all finite and interpolated
    assert len(meas.width_profile_mm) == 21
    assert all(np.isfinite(w) for w in meas.width_profile_mm)
    # Middle slice 10 was interpolated and should be close to median width
    assert abs(meas.width_profile_mm[10] - meas.width_mm) < 2.0
