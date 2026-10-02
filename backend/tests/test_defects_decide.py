from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision.schemas import Spec
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.decide import decide
from billetvision.vision.defects import detect_defects
from billetvision.vision.measure import measure
from billetvision.vision.rectify import build_rectifier
from billetvision.vision.segment import segment
from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    render_scene,
)
from billetvision.vision.types import DefectResult, IdResult, Measurement


@pytest.fixture
def default_spec() -> Spec:
    return Spec(
        id="spec_400_100",
        name="Standard 400x100 Billet",
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


def _inspect_scene(scene: SceneSpec, spec: Spec) -> tuple[Measurement, DefectResult]:
    rng = np.random.default_rng(42)
    img, _ = render_scene(scene, rng)
    bg_scene = SceneSpec(billets=(), camera=CameraSpec(), effects=scene.effects, with_marker=True)
    bg_img, _ = render_scene(bg_scene, rng)

    corners, _ = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))  # type: ignore[misc]
    cal = calibrate_from_marker(corners, (1920, 1080))
    rectifier = build_rectifier(cal)

    rect_bgr = rectifier.apply(img)
    rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
    bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)

    dets = segment(rect_gray, bg_gray, spec, roi=rectifier.roi, rect_px_per_mm=rectifier.rect_px_per_mm)
    assert len(dets) >= 1
    m, _ = measure(
        dets[0],
        rect_gray,
        rect_bgr,
        roi=rectifier.roi,
        rect_px_per_mm=rectifier.rect_px_per_mm,
    )
    defects = detect_defects(m, spec)
    return m, defects


@pytest.mark.parametrize(
    ("defect_type", "defect_size_mm"),
    [
        ("notch", 8.0),
        ("bulge", 8.0),
        ("taper", 8.0),
        ("camber", 8.0),
    ],
)
def test_forced_defects_detected(defect_type: str, defect_size_mm: float, default_spec: Spec) -> None:
    billet = BilletSpec(
        center_mm=(350.0, 0.0),
        angle_deg=0.0,
        length_mm=400.0,
        width_mm=100.0,
        id_text="H24-1187",
        qr=False,
        defect=defect_type,  # type: ignore[arg-type]
        defect_size_mm=defect_size_mm,
    )
    scene = SceneSpec(
        billets=(billet,),
        camera=CameraSpec(),
        effects=Effects(),
        with_marker=True,
    )
    _, defects = _inspect_scene(scene, default_spec)
    assert defect_type in defects.defects
    if defect_type == "notch":
        assert defects.notch_depth_mm >= 5.0


def test_clean_scenes_have_no_defects_in_95_percent_cases(default_spec: Spec) -> None:
    no_defect_count = 0
    total_scenes = 20

    for seed in range(total_scenes):
        rng = np.random.default_rng(seed)
        billet = BilletSpec(
            center_mm=(float(rng.uniform(320.0, 380.0)), float(rng.uniform(-10.0, 10.0))),
            angle_deg=float(rng.uniform(-5.0, 5.0)),
            length_mm=400.0,
            width_mm=100.0,
            id_text="H24-1187",
            qr=False,
            defect=None,
            defect_size_mm=0.0,
        )
        scene = SceneSpec(billets=(billet,), camera=CameraSpec(), effects=Effects(), with_marker=True)
        _, defects = _inspect_scene(scene, default_spec)
        if len(defects.defects) == 0:
            no_defect_count += 1

    clean_rate = no_defect_count / total_scenes
    assert clean_rate >= 0.95, f"Clean rate {clean_rate:.2f} is below 0.95"


def _make_dummy_measurement(
    length_mm: float = 400.0,
    width_mm: float = 100.0,
    width_profile: tuple[float, ...] | None = None,
) -> Measurement:
    profile = width_profile if width_profile is not None else tuple([100.0] * 21)
    return Measurement(
        length_mm=length_mm,
        width_mm=width_mm,
        width_profile_mm=profile,
        valid_slices=21,
        dense_pos_mm=np.linspace(-190.0, 190.0, 1000),
        dense_top_mm=np.full(1000, 50.0),
        dense_bottom_mm=np.full(1000, -50.0),
        sharpness=200.0,
        angle_deg=0.0,
    )


def _make_dummy_defects(
    defects: tuple[str, ...] = (),
    cs_var_pct: float = 1.0,
    taper_mm: float = 0.0,
    camber_mm: float = 0.0,
    notch_depth_mm: float = 0.0,
) -> DefectResult:
    return DefectResult(
        cs_var_pct=cs_var_pct,
        taper_mm=taper_mm,
        camber_mm=camber_mm,
        min_width_mm=100.0,
        max_width_mm=101.0,
        defects=defects,
        notch_depth_mm=notch_depth_mm,
    )


def test_decision_pass_when_within_spec(default_spec: Spec) -> None:
    m = _make_dummy_measurement()
    d = _make_dummy_defects()
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Pass"
    assert decision.reasons == ("Within spec",)


def test_decision_fail_on_undersize_length(default_spec: Spec) -> None:
    # nom 400, tol 5 -> min 395. Length 390 is 5 mm below minimum
    m = _make_dummy_measurement(length_mm=390.0)
    d = _make_dummy_defects()
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Fail"
    assert any("below minimum 395.0 mm" in r for r in decision.reasons)


def test_decision_rework_on_oversize_length_trim(default_spec: Spec) -> None:
    # nom 400, tol 5 -> max 405. Length 412 is 7 mm over max (trim)
    m = _make_dummy_measurement(length_mm=412.0)
    d = _make_dummy_defects()
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Rework"
    assert any("over maximum 405.0 mm (trim)" in r for r in decision.reasons)


def test_decision_fail_on_undersize_width(default_spec: Spec) -> None:
    # nom 100, tol 2 -> min 98. Width 95 is 3 mm below minimum
    m = _make_dummy_measurement(width_mm=95.0)
    d = _make_dummy_defects()
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Fail"
    assert any("below minimum 98.0 mm" in r for r in decision.reasons)


def test_decision_rework_on_oversize_width(default_spec: Spec) -> None:
    # nom 100, tol 2 -> max 102. Width 104 is 2 mm over max
    m = _make_dummy_measurement(width_mm=104.0)
    d = _make_dummy_defects()
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Rework"
    assert any("over maximum 102.0 mm" in r for r in decision.reasons)


def test_decision_fail_on_notch(default_spec: Spec) -> None:
    m = _make_dummy_measurement()
    d = _make_dummy_defects(defects=("notch",), notch_depth_mm=6.5)
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Fail"
    assert any("Notch 6.5 mm deep detected" in r for r in decision.reasons)


def test_decision_cs_var_rework_and_fail(default_spec: Spec) -> None:
    m = _make_dummy_measurement()
    # Warn pct is 3.0, fail pct is 5.0
    d_warn = _make_dummy_defects(cs_var_pct=3.8)
    dec_warn = decide(m, d_warn, default_spec, billet_id="H24-1187")
    assert dec_warn.status == "Rework"
    assert any("Cross-section variation 3.8% ≥ 3.0%" in r for r in dec_warn.reasons)

    d_fail = _make_dummy_defects(cs_var_pct=5.5)
    dec_fail = decide(m, d_fail, default_spec, billet_id="H24-1187")
    assert dec_fail.status == "Fail"
    assert any("Cross-section variation 5.5% ≥ 5.0%" in r for r in dec_fail.reasons)


def test_decision_rework_on_taper_bulge_camber(default_spec: Spec) -> None:
    m = _make_dummy_measurement()
    d = _make_dummy_defects(
        defects=("taper", "bulge", "camber"),
        taper_mm=4.2,
        camber_mm=3.6,
    )
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Rework"
    assert any("Taper 4.2 mm" in r for r in decision.reasons)
    assert any("Bulge detected" in r for r in decision.reasons)
    assert any("Camber 3.6 mm" in r for r in decision.reasons)


def test_decision_rework_on_unreadable_id_and_id_mismatch(default_spec: Spec) -> None:
    m = _make_dummy_measurement()
    d = _make_dummy_defects()

    # Unreadable ID
    dec_no_id = decide(m, d, default_spec, billet_id=None)
    assert dec_no_id.status == "Rework"
    assert any("ID unreadable — tag manually" in r for r in dec_no_id.reasons)

    # ID Mismatch
    id_res = IdResult(
        billet_id="H24-1187",
        id_source="ocr",
        ocr_text="H24-1187",
        ocr_confidence=0.95,
        ocr_agreement=1.0,
        qr_text="H24-9999",
        id_mismatch=True,
    )
    dec_mismatch = decide(m, d, default_spec, id_result=id_res)
    assert dec_mismatch.status == "Rework"
    assert any("OCR 'H24-1187' does not match QR 'H24-9999'" in r for r in dec_mismatch.reasons)


def test_decision_status_precedence_fail_over_rework(default_spec: Spec) -> None:
    # Undersize width (Fail) + oversize length (Rework) -> Fail
    m = _make_dummy_measurement(length_mm=415.0, width_mm=90.0)
    d = _make_dummy_defects(defects=("camber",), camber_mm=4.0)
    decision = decide(m, d, default_spec, billet_id="H24-1187")
    assert decision.status == "Fail"
    # Contains reasons for both
    assert any("below minimum" in r for r in decision.reasons)
    assert any("over maximum" in r for r in decision.reasons)
    assert any("Camber" in r for r in decision.reasons)
