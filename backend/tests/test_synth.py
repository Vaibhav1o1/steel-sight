from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    random_scene,
    render_scene,
)


def test_synth_determinism() -> None:
    rng1 = np.random.default_rng(42)
    spec1 = random_scene(rng1, "clean")
    img1, gt1 = render_scene(spec1, np.random.default_rng(42))

    rng2 = np.random.default_rng(42)
    spec2 = random_scene(rng2, "clean")
    img2, gt2 = render_scene(spec2, np.random.default_rng(42))

    assert np.array_equal(img1, img2), "Images with identical seed must be bit-for-bit identical"
    assert np.allclose(gt1.h_bed_to_img, gt2.h_bed_to_img)
    assert np.allclose(gt1.marker_corners_px, gt2.marker_corners_px)
    assert len(gt1.billets) == len(gt2.billets)

    rng3 = np.random.default_rng(99)
    spec3 = random_scene(rng3, "clean")
    img3, _ = render_scene(spec3, np.random.default_rng(99))
    assert not np.array_equal(img1, img3), "Different seeds must produce different images"


def test_marker_detection_accuracy() -> None:
    rng = np.random.default_rng(123)
    spec = SceneSpec(
        billets=(),
        camera=CameraSpec(),
        effects=Effects(noise_sigma=0.0),
        with_marker=True,
    )
    img, gt = render_scene(spec, rng)

    assert img.shape == (1080, 1920, 3)
    assert img.dtype == np.uint8

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    corners, ids, _ = detector.detectMarkers(gray)
    assert ids is not None and len(ids) > 0, "ArUco marker was not detected"
    assert 0 in ids.flatten(), f"Expected marker ID 0, got {ids}"

    detected_corners = corners[0][0]
    max_error_px = float(np.max(np.abs(detected_corners - gt.marker_corners_px)))
    assert max_error_px < 0.5, f"Marker corner error {max_error_px:.4f} px exceeds 0.5 px threshold"


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
def test_each_variant_renders(variant: str) -> None:
    rng = np.random.default_rng(777)
    spec = random_scene(rng, variant=variant)
    img, gt = render_scene(spec, rng)

    assert img.shape == (1080, 1920, 3)
    assert img.dtype == np.uint8
    assert len(gt.billets) >= 1
    assert gt.image_px_per_mm > 0.0
    assert gt.h_bed_to_img.shape == (3, 3)
    assert gt.marker_corners_px.shape == (4, 2)

    for b in gt.billets:
        assert b.length_mm > 0.0
        assert b.width_mm > 0.0
        assert -90.0 <= b.angle_deg <= 90.0
        assert b.id_text is not None


def test_defects_render_properly() -> None:
    rng = np.random.default_rng(555)
    defects = ["notch", "taper", "bulge", "camber"]

    for d in defects:
        billet = BilletSpec(
            center_mm=(300.0, 0.0),
            angle_deg=0.0,
            length_mm=400.0,
            width_mm=100.0,
            id_text="H24-1187",
            qr=True,
            defect=d,  # type: ignore[arg-type]
            defect_size_mm=8.0,
        )
        spec = SceneSpec(
            billets=(billet,),
            camera=CameraSpec(),
            effects=Effects(),
            with_marker=True,
        )
        img, gt = render_scene(spec, rng)
        assert img.shape == (1080, 1920, 3)
        assert len(gt.billets) == 1
        assert gt.billets[0].defect == d
