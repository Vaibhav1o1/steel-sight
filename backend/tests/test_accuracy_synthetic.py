from __future__ import annotations

import cv2
import numpy as np

from billetvision.schemas import Spec
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.measure import measure
from billetvision.vision.rectify import build_rectifier, glare_mask
from billetvision.vision.segment import segment
from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    render_scene,
)

VARIANTS = (
    "clean",
    "dim",
    "bright",
    "gradient",
    "noise",
    "blur",
    "dust",
    "scale",
    "glare",
)

EFFECTS_MAP = {
    "clean": Effects(),
    "dim": Effects(brightness=0.6),
    "bright": Effects(brightness=1.35),
    "gradient": Effects(gradient=0.35),
    "noise": Effects(noise_sigma=7.0),
    "blur": Effects(blur_sigma=1.2),
    "dust": Effects(dust=60),
    "scale": Effects(scale=8),
    "glare": Effects(glare=True),
}


def test_accuracy_synthetic_suite() -> None:
    spec = Spec(
        id="synthetic_bench",
        name="Synthetic Benchmark",
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
        min_area_factor=0.3,
        max_area_factor=1.6,
    )

    all_len_errs: list[float] = []
    all_wid_errs: list[float] = []
    per_variant: dict[str, dict[str, list[float]]] = {v: {"len": [], "wid": []} for v in VARIANTS}

    total_scenes = 60

    for i in range(total_scenes):
        variant = VARIANTS[i % len(VARIANTS)]
        eff = EFFECTS_MAP[variant]
        rng = np.random.default_rng(2026 + i)

        length_mm = float(rng.uniform(340.0, 480.0))
        width_mm = float(rng.uniform(85.0, 115.0))
        half_l = length_mm / 2.0
        min_cx = 60.0 + 30.0 + half_l
        max_cx = 660.0 - 30.0 - half_l
        cx = float(rng.uniform(min_cx, max_cx))
        cy = float(rng.uniform(-20.0, 20.0))
        angle = float(rng.uniform(-12.0, 12.0))

        billet = BilletSpec(
            center_mm=(cx, cy),
            angle_deg=angle,
            length_mm=length_mm,
            width_mm=width_mm,
            id_text="H24-1187",
            qr=False,
            defect=None,
            defect_size_mm=0.0,
        )

        scene = SceneSpec(
            billets=(billet,),
            camera=CameraSpec(),
            effects=eff,
            with_marker=True,
        )
        img, gt = render_scene(scene, rng)

        # Background from the same scene without billets
        bg_scene = SceneSpec(
            billets=(),
            camera=scene.camera,
            effects=eff,
            with_marker=True,
        )
        bg_img, _ = render_scene(bg_scene, np.random.default_rng(2026 + i))

        marker_res = detect_marker(cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))
        assert marker_res is not None, f"Failed to detect marker in background for scene {i} ({variant})"
        cal = calibrate_from_marker(marker_res[0], (1920, 1080))
        rectifier = build_rectifier(cal)

        rect_bgr = rectifier.apply(img)
        rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
        bg_gray = cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY)
        glare = glare_mask(rect_gray)

        dets = segment(
            rect_gray,
            bg_gray,
            spec,
            roi=rectifier.roi,
            rect_px_per_mm=rectifier.rect_px_per_mm,
        )
        assert len(dets) >= 1, f"No billet detected in scene {i} ({variant})"
        det = dets[0]
        assert det.full_inside, f"Billet not fully inside in scene {i} ({variant})"
        assert not det.merged, f"Billet unexpectedly flagged as merged in scene {i} ({variant})"

        meas, _ = measure(
            det,
            rect_gray,
            rect_bgr,
            glare=glare,
            roi=rectifier.roi,
            rect_px_per_mm=rectifier.rect_px_per_mm,
        )

        true_billet = gt.billets[0]
        len_err_pct = abs(meas.length_mm - true_billet.length_mm) / true_billet.length_mm * 100.0
        wid_err_pct = abs(meas.width_mm - true_billet.width_mm) / true_billet.width_mm * 100.0

        all_len_errs.append(len_err_pct)
        all_wid_errs.append(wid_err_pct)
        per_variant[variant]["len"].append(len_err_pct)
        per_variant[variant]["wid"].append(wid_err_pct)

    overall_len_mae = float(np.mean(all_len_errs))
    overall_len_max = float(np.max(all_len_errs))
    overall_wid_mae = float(np.mean(all_wid_errs))
    overall_wid_max = float(np.max(all_wid_errs))

    # Print formatted markdown table
    lines = [
        f"Evaluated {total_scenes} scenes across all 9 variants:",
        f"Overall Length: MAE = {overall_len_mae:.3f}%, Max = {overall_len_max:.3f}%",
        f"Overall Width:  MAE = {overall_wid_mae:.3f}%, Max = {overall_wid_max:.3f}%",
        "",
        "| Variant | Count | Len MAE % | Len Max % | Wid MAE % | Wid Max % |",
        "|---|---|---|---|---|---|",
    ]
    for v in VARIANTS:
        l_errs = per_variant[v]["len"]
        w_errs = per_variant[v]["wid"]
        lines.append(
            f"| {v:8s} | {len(l_errs):5d} | {np.mean(l_errs):8.3f}% | {np.max(l_errs):8.3f}% "
            f"| {np.mean(w_errs):8.3f}% | {np.max(w_errs):8.3f}% |"
        )
    table_output = "\n".join(lines)
    print("\n" + table_output + "\n")

    # Assert SPEC §18 accuracy thresholds: Length & Width MAE ≤ 0.5% and Max Error ≤ 1.0%
    assert overall_len_mae <= 0.5, f"Length MAE {overall_len_mae:.3f}% exceeds 0.5% limit"
    assert overall_len_max <= 1.0, f"Length Max {overall_len_max:.3f}% exceeds 1.0% limit"
    assert overall_wid_mae <= 0.5, f"Width MAE {overall_wid_mae:.3f}% exceeds 0.5% limit"
    assert overall_wid_max <= 1.0, f"Width Max {overall_wid_max:.3f}% exceeds 1.0% limit"
