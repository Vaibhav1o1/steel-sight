from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision.schemas import Roi, Spec
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.rectify import build_rectifier, glare_mask, rect_to_image
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


def test_rectifier_without_intrinsics_and_rect_to_image() -> None:
    rng = np.random.default_rng(42)
    scene = random_scene(rng, "clean")
    img, gt = render_scene(scene, rng)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    res = detect_marker(gray)
    assert res is not None
    corners, _ = res

    cal = calibrate_from_marker(corners, (1920, 1080))
    rectifier = build_rectifier(cal)

    # 1. Apply rectification
    rect_bgr = rectifier.apply(img)
    expected_w = int(round(cal.roi.w_mm * cal.rect_px_per_mm))
    expected_h = int(round(cal.roi.h_mm * cal.rect_px_per_mm))
    assert rect_bgr.shape == (expected_h, expected_w, 3)

    # 2. Coordinate mapping round trip
    b = gt.billets[0]
    expected_rect_u = (b.center_mm[0] - cal.roi.x0_mm) * cal.rect_px_per_mm
    expected_rect_v = (b.center_mm[1] - cal.roi.y0_mm) * cal.rect_px_per_mm

    rect_pts = np.array([[expected_rect_u, expected_rect_v]], dtype=np.float64)
    img_pt = rect_to_image(rectifier, rect_pts)
    assert img_pt.shape == (1, 2)

    # Sample pixel at rect_to_image location: should be bright billet surface
    ix, iy = int(round(img_pt[0, 0])), int(round(img_pt[0, 1]))
    assert 0 <= ix < 1920
    assert 0 <= iy < 1080
    assert img[iy, ix].mean() > 100  # billet is bright steel


def test_rectifier_with_intrinsics() -> None:
    # Synthetic camera intrinsics
    camera_matrix = np.array(
        [[2000.0, 0.0, 960.0], [0.0, 2000.0, 540.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    dist_coeffs = np.array([-0.05, 0.01, 0.001, 0.001, 0.0], dtype=np.float64)

    rng = np.random.default_rng(10)
    scene = random_scene(rng, "clean")
    img, _ = render_scene(scene, rng)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    res = detect_marker(gray)
    assert res is not None
    corners, _ = res

    cal = calibrate_from_marker(
        corners,
        (1920, 1080),
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
    )
    rectifier = build_rectifier(cal)
    assert rectifier.map_x is not None
    assert rectifier.map_y is not None

    rect_bgr = rectifier.apply(img)
    expected_w = int(round(cal.roi.w_mm * cal.rect_px_per_mm))
    expected_h = int(round(cal.roi.h_mm * cal.rect_px_per_mm))
    assert rect_bgr.shape == (expected_h, expected_w, 3)

    # Test rect_to_image
    test_rect_pt = np.array([[300.0, 400.0]], dtype=np.float64)
    img_pt = rectifier.rect_to_image(test_rect_pt)
    assert img_pt.shape == (1, 2)
    assert np.all(np.isfinite(img_pt))


def test_glare_mask() -> None:
    gray = np.full((100, 100), 120, dtype=np.uint8)
    # Add a saturated spot at (50, 50) of radius 5
    cv2.circle(gray, (50, 50), 5, 255, -1)

    mask = glare_mask(gray, saturation_level=250)
    assert mask.shape == (100, 100)
    assert mask[50, 50] == 255

    # Check dilation: original circle radius was 5, with 3 px dilation it should cover radius 8
    assert mask[50, 50 + 7] == 255
    # Outside dilated region should be 0
    assert mask[50, 50 + 15] == 0
    assert mask[10, 10] == 0


@pytest.mark.parametrize(
    "variant",
    [
        "clean",
        "dim",
        "bright",
        "gradient",
        "noise",
        "blur",
        "dust",
        "scale",
        "glare",
    ],
)
def test_one_detection_per_billet_across_all_variants(variant: str, default_spec: Spec) -> None:
    rng = np.random.default_rng(123)
    scene = random_scene(rng, variant)
    img, gt = render_scene(scene, rng)

    # Background frame (same optical effects, no billets)
    bg_scene = SceneSpec(
        billets=(),
        camera=CameraSpec(),
        effects=scene.effects,
        with_marker=True,
    )
    bg_img, _ = render_scene(bg_scene, np.random.default_rng(123))

    corners, _ = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]
    cal = calibrate_from_marker(corners, (1920, 1080))
    rectifier = build_rectifier(cal)

    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    # With background
    dets_with_bg = segment(rect_gray, bg_gray, default_spec, roi=cal.roi, rect_px_per_mm=cal.rect_px_per_mm)
    assert len(dets_with_bg) == len(gt.billets), (
        f"Variant {variant} with_bg expected {len(gt.billets)} got {len(dets_with_bg)}"
    )

    # Without background
    dets_no_bg = segment(rect_gray, None, default_spec, roi=cal.roi, rect_px_per_mm=cal.rect_px_per_mm)
    assert len(dets_no_bg) == len(gt.billets), (
        f"Variant {variant} no_bg expected {len(gt.billets)} got {len(dets_no_bg)}"
    )

    # Check geometry of the detection
    for d in dets_with_bg:
        assert d.rough_length_mm > 0
        assert d.rough_width_mm > 0
        assert -90.0 < d.angle_deg <= 90.0
        assert not d.merged


def test_full_inside_false_for_billet_crossing_roi_edge(default_spec: Spec) -> None:
    # Place a billet crossing the left ROI boundary (x0 = 60 mm)
    # Center at 100 mm with length 400 mm extends from -100 mm to 300 mm
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
    scene = SceneSpec(billets=(billet,), camera=CameraSpec(), effects=Effects(), with_marker=True)
    rng = np.random.default_rng(42)
    img, _ = render_scene(scene, rng)

    bg_scene = SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True)
    bg_img, _ = render_scene(bg_scene, rng)

    corners, _ = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]
    cal = calibrate_from_marker(corners, (1920, 1080))
    rectifier = build_rectifier(cal)

    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(rect_gray, bg_gray, default_spec, roi=cal.roi, rect_px_per_mm=cal.rect_px_per_mm)
    assert len(dets) == 1
    assert not dets[0].full_inside


def test_merged_true_for_two_touching_billets(default_spec: Spec) -> None:
    # Two billets touching side by side: each width 100 mm, side by side at y=-50 and y=+50
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
    scene = SceneSpec(billets=(b1, b2), camera=CameraSpec(), effects=Effects(), with_marker=True)
    rng = np.random.default_rng(42)
    img, _ = render_scene(scene, rng)

    bg_scene = SceneSpec(billets=(), camera=CameraSpec(), effects=Effects(), with_marker=True)
    bg_img, _ = render_scene(bg_scene, rng)

    corners, _ = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]
    cal = calibrate_from_marker(corners, (1920, 1080))
    rectifier = build_rectifier(cal)

    rect_gray = cv2.cvtColor(rectifier.apply(img), cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(rect_gray, bg_gray, default_spec, roi=cal.roi, rect_px_per_mm=cal.rect_px_per_mm)
    assert len(dets) == 1
    assert dets[0].merged is True


def test_hand_sized_blobs_rejected(default_spec: Spec) -> None:
    roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)
    r = 3.0
    w_px = int(round(roi.w_mm * r))
    h_px = int(round(roi.h_mm * r))

    # Dark background
    rect_gray = np.full((h_px, w_px), 28, dtype=np.uint8)
    bg_gray = np.full((h_px, w_px), 28, dtype=np.uint8)

    # 1. Hand-shaped blob with low aspect ratio: 150 mm x 130 mm (aspect = 1.15 < 1.5)
    center_px = (int(w_px // 2), int(h_px // 2))
    blob_w_px = int(150.0 * r)
    blob_h_px = int(130.0 * r)
    cv2.ellipse(rect_gray, center_px, (blob_w_px // 2, blob_h_px // 2), 0, 0, 360, 180, -1)

    dets = segment(rect_gray, bg_gray, default_spec, roi=roi, rect_px_per_mm=r)
    assert len(dets) == 0, "Hand-shaped blob should be rejected by aspect ratio"

    # 2. Small hand/glove blob with area < min_area_factor * nominal_area
    rect_gray2 = np.full((h_px, w_px), 28, dtype=np.uint8)
    small_w_px = int(100.0 * r)
    small_h_px = int(40.0 * r)
    cv2.rectangle(
        rect_gray2,
        (center_px[0] - small_w_px // 2, center_px[1] - small_h_px // 2),
        (center_px[0] + small_w_px // 2, center_px[1] + small_h_px // 2),
        180,
        -1,
    )
    dets2 = segment(rect_gray2, bg_gray, default_spec, roi=roi, rect_px_per_mm=r)
    assert len(dets2) == 0, "Small blob below min_area_factor should be rejected"
