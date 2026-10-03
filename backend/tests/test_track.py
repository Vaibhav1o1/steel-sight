from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision import config
from billetvision.schemas import Roi, Spec
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.measure import measure
from billetvision.vision.rectify import build_rectifier, glare_mask
from billetvision.vision.segment import segment
from billetvision.vision.synth import render_video
from billetvision.vision.track import (
    Tracker,
    aggregate_defects,
    aggregate_measurements,
)
from billetvision.vision.types import DefectResult, Detection, Measurement


@pytest.fixture
def test_spec() -> Spec:
    return Spec(
        id="test_spec",
        name="Test Spec",
        nominal_length_mm=400.0,
        nominal_width_mm=100.0,
        tol_length_mm=5.0,
        tol_width_mm=2.0,
        cs_var_warn_pct=3.0,
        cs_var_fail_pct=5.0,
        notch_min_mm=5.0,
        camber_max_mm=3.0,
        taper_max_mm=3.0,
        id_template="A99-9999",
    )


def _make_dummy_measurement(length: float, width: float, sharpness: float = 100.0) -> Measurement:
    return Measurement(
        length_mm=length,
        width_mm=width,
        width_profile_mm=(width,) * 21,
        valid_slices=21,
        dense_pos_mm=np.linspace(0, length, 50),
        dense_top_mm=np.full(50, width / 2.0),
        dense_bottom_mm=np.full(50, -width / 2.0),
        sharpness=sharpness,
        angle_deg=0.0,
    )


def _make_dummy_detection(
    center_mm: tuple[float, float],
    full_inside: bool = True,
    merged: bool = False,
) -> Detection:
    return Detection(
        contour_px=np.zeros((4, 2), dtype=np.int32),
        center_mm=center_mm,
        angle_deg=0.0,
        rough_length_mm=400.0,
        rough_width_mm=100.0,
        area_mm2=40000.0,
        full_inside=full_inside,
        merged=merged,
    )


def test_aggregate_measurements() -> None:
    samples = [
        _make_dummy_measurement(401.0, 99.0, sharpness=50.0),
        _make_dummy_measurement(400.0, 100.0, sharpness=120.0),
        _make_dummy_measurement(402.0, 101.0, sharpness=80.0),
    ]
    agg = aggregate_measurements(samples)
    assert agg.length_mm == 401.0
    assert agg.width_mm == 100.0
    assert agg.width_profile_mm[0] == 100.0
    assert agg.sharpness == 120.0


def test_aggregate_defects() -> None:
    results = [
        DefectResult(1.0, 0.5, 0.2, 98.0, 102.0, ("notch", "camber"), 6.0),
        DefectResult(1.2, 0.6, 0.3, 97.5, 102.5, ("notch",), 6.5),
        DefectResult(0.9, 0.4, 0.1, 98.5, 101.5, ("notch", "taper"), 5.8),
    ]
    agg = aggregate_defects(results)
    assert agg.notch_depth_mm == 6.0
    # notch present in 3/3 (> 50%) -> included
    # camber present in 1/3 (<= 50%) -> excluded
    # taper present in 1/3 (<= 50%) -> excluded
    assert "notch" in agg.defects
    assert "camber" not in agg.defects
    assert "taper" not in agg.defects


def test_trigger_modes() -> None:
    roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)
    # 1. Stable mode
    t_stable = Tracker(roi=roi, trigger_mode="stable", stable_frames=4, stable_mm=2.0)
    # Moving billet does not trigger
    for i in range(10):
        det = _make_dummy_detection(center_mm=(100.0 + i * 5.0, 0.0))
        t_stable.update([det], t=float(i))
    assert list(t_stable.tracks.values())[0].first_sample_t is None

    # Stationary billet triggers after stable_frames
    t_stationary = Tracker(roi=roi, trigger_mode="stable", stable_frames=4, stable_mm=2.0)
    for i in range(5):
        det = _make_dummy_detection(center_mm=(360.0, 0.0))
        t_stationary.update([det], t=float(i))
    assert list(t_stationary.tracks.values())[0].first_sample_t is not None

    # 2. Line mode
    t_line = Tracker(roi=roi, trigger_mode="line", line_window_mm=40.0)
    # Outside window (center 360, window 40 -> [320, 400])
    det_out = _make_dummy_detection(center_mm=(250.0, 0.0))
    t_line.update([det_out], t=0.0)
    assert list(t_line.tracks.values())[0].first_sample_t is None
    # Step smoothly into window within track_match_mm (60 mm)
    t_line.update([_make_dummy_detection(center_mm=(290.0, 0.0))], t=0.5)
    t_line.update([_make_dummy_detection(center_mm=(330.0, 0.0))], t=1.0)
    assert t_line.tracks[1].first_sample_t is not None
    assert t_line.tracks[1].crossed_line is True

    # 3. Auto mode
    det_in = _make_dummy_detection(center_mm=(350.0, 0.0))
    t_auto = Tracker(roi=roi, trigger_mode="auto", line_window_mm=40.0)
    t_auto.update([det_in], t=0.0)
    assert list(t_auto.tracks.values())[0].first_sample_t is not None


def test_edge_cases_track() -> None:
    roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)
    tracker = Tracker(roi=roi, trigger_mode="line", samples_min=3, samples_target=7)

    # E-07: Merged detection never samples, raises system alert once
    merged_det = _make_dummy_detection(center_mm=(360.0, 0.0), merged=True)
    tracker.update([merged_det], t=0.0)
    alerts = tracker.pop_alerts()
    assert len(alerts) == 1
    assert "Separate billets" in alerts[0]
    # Subsequent merged frames do not raise duplicate alert
    tracker.update([merged_det], t=1.0)
    assert len(tracker.pop_alerts()) == 0
    assert len(list(tracker.tracks.values())[0].samples) == 0

    # E-08: Removed before enough samples (< samples_min=3) -> discarded, no inspection
    t_under = Tracker(roi=roi, trigger_mode="line", samples_min=3)
    det = _make_dummy_detection(center_mm=(360.0, 0.0))
    dummy_crop = np.zeros((50, 150, 3), dtype=np.uint8)

    def measure_fn(_):
        return _make_dummy_measurement(400.0, 100.0), dummy_crop

    t_under.update([det], t=0.0, measure_fn=measure_fn)
    t_under.update([det], t=1.0, measure_fn=measure_fn)
    # Now billet is removed (empty detections)
    finalized = t_under.update([], t=2.0)
    assert len(finalized) == 0  # Discarded without logging

    # E-09: Exactly one inspection per track even if it rests for many frames
    t_rest = Tracker(roi=roi, trigger_mode="stable", stable_frames=3, samples_target=5)
    finalized_all: list[int] = []
    for f in range(25):
        r = t_rest.update([det], t=float(f), measure_fn=measure_fn)
        finalized_all.extend([trk.id for trk in r])
    assert len(finalized_all) == 1


def test_station_video_e2e(test_spec: Spec) -> None:
    rng = np.random.default_rng(12345)
    video = list(render_video(rng, mode="station", n_billets=2, fps=15))
    assert len(video) > 0

    # Marker calibration
    first_frame = video[0][0]
    gray0 = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    marker_res = detect_marker(gray0)
    assert marker_res is not None
    corners, _ = marker_res
    roi = Roi(**config.ROI_DEFAULT)
    cal = calibrate_from_marker(corners, image_size=(1920, 1080), roi=roi)
    rectifier = build_rectifier(cal)

    tracker = Tracker(roi=roi, trigger_mode="stable")

    finalized = []
    t = 0.0
    for frame, _gt in video:
        rect_bgr = rectifier.apply(frame)
        rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
        g_mask = glare_mask(rect_gray)
        dets = segment(rect_gray, background=None, spec=test_spec, cfg=config)

        def measure_fn(
            d: Detection,
            rg: np.ndarray = rect_gray,
            rb: np.ndarray = rect_bgr,
            gm: np.ndarray = g_mask,
        ) -> tuple[Measurement, np.ndarray]:
            return measure(d, rg, rb, gm, cfg=config)

        ready = tracker.update(dets, t, measure_fn=measure_fn)
        finalized.extend(ready)
        t += 1.0 / 15.0

    # Exactly 2 inspections for 2 billets
    assert len(finalized) == 2
    # No duplicate IDs
    ids = [trk.id for trk in finalized]
    assert len(ids) == len(set(ids))

    for trk in finalized:
        agg = aggregate_measurements(trk.samples)
        assert 300.0 < agg.length_mm < 520.0
        assert 80.0 < agg.width_mm < 120.0


def test_conveyor_video_e2e(test_spec: Spec) -> None:
    rng = np.random.default_rng(54321)
    video = list(render_video(rng, mode="conveyor", n_billets=1, fps=15))
    assert len(video) > 0

    # Ground truth from first frame that contains a billet
    true_billet = None
    for _, gt in video:
        if len(gt) > 0:
            true_billet = gt[0]
            break
    assert true_billet is not None

    first_frame = video[0][0]
    gray0 = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    marker_res = detect_marker(gray0)
    assert marker_res is not None
    corners, _ = marker_res
    roi = Roi(**config.ROI_DEFAULT)
    cal = calibrate_from_marker(corners, image_size=(1920, 1080), roi=roi)
    rectifier = build_rectifier(cal)

    tracker = Tracker(roi=roi, trigger_mode="line", samples_target=7)

    finalized = []
    t = 0.0
    for frame, _gt in video:
        rect_bgr = rectifier.apply(frame)
        rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
        g_mask = glare_mask(rect_gray)
        dets = segment(rect_gray, background=None, spec=test_spec, cfg=config)

        def measure_fn(
            d: Detection,
            rg: np.ndarray = rect_gray,
            rb: np.ndarray = rect_bgr,
            gm: np.ndarray = g_mask,
        ) -> tuple[Measurement, np.ndarray]:
            return measure(d, rg, rb, gm, cfg=config)

        ready = tracker.update(dets, t, measure_fn=measure_fn)
        finalized.extend(ready)
        t += 1.0 / 15.0

    # Exactly 1 inspection
    assert len(finalized) == 1
    agg = aggregate_measurements(finalized[0].samples)

    # Within 1% of ground truth
    len_err_pct = abs(agg.length_mm - true_billet.length_mm) / true_billet.length_mm * 100.0
    width_err_pct = abs(agg.width_mm - true_billet.width_mm) / true_billet.width_mm * 100.0
    assert len_err_pct < 1.0, f"Length error {len_err_pct:.2f}% >= 1.0%"
    assert width_err_pct < 1.0, f"Width error {width_err_pct:.2f}% >= 1.0%"
