#!/usr/bin/env python3
"""Synthetic accuracy & metrology benchmark runner for BilletVision.

Runs N synthetic scenes across 9 visual variants and generates
reports/bench_synthetic.json labelled strictly as SYNTHETIC.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.evaluation import (
    compute_confusion_matrix,
    compute_mae,
    compute_max_error,
)
from billetvision.schemas import Spec, SyntheticBench, SyntheticVariant
from billetvision.vision.calibration import calibrate_from_marker, detect_marker
from billetvision.vision.decide import decide
from billetvision.vision.defects import detect_defects
from billetvision.vision.idparse import read_id
from billetvision.vision.measure import measure
from billetvision.vision.ocr import read as ocr_read
from billetvision.vision.qr import read_qr
from billetvision.vision.rectify import build_rectifier, glare_mask
from billetvision.vision.segment import segment
from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    render_scene,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bench_synthetic")

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


def run_benchmark(n_scenes: int = 180, seed: int = 42) -> dict[str, Any]:
    """Execute synthetic benchmark and compute metrology accuracy."""
    spec = Spec(
        id="FLAT-500x100",
        name="Flat bar 500 × 100 mm",
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
        min_area_factor=0.3,
        max_area_factor=1.6,
    )
    results_by_variant: dict[str, dict[str, list[Any]]] = {
        v: {
            "len_err": [],
            "wid_err": [],
            "ocr_matches": [],
            "defect_correct": [],
            "process_ms": [],
        }
        for v in VARIANTS
    }

    preds: list[str] = []
    gts: list[str] = []

    total_start = time.perf_counter()

    for idx in range(n_scenes):
        variant = VARIANTS[idx % len(VARIANTS)]
        eff = EFFECTS_MAP[variant]
        rng = np.random.default_rng(seed + idx)

        # Decide defect condition for scene
        has_defect = (idx % 3) != 0  # 2/3 of scenes have defects
        defect_type: Literal["notch", "taper", "camber", "bulge"] | None = None
        defect_size = 0.0
        gt_status = "Pass"

        if has_defect:
            defect_type = cast("Literal['notch', 'taper', 'camber', 'bulge']", ["notch", "taper", "camber"][idx % 3])
            if defect_type == "notch":
                defect_size = 6.0
                gt_status = "Fail"
            elif defect_type == "taper":
                defect_size = 4.0
                gt_status = "Rework"
            elif defect_type == "camber":
                defect_size = 4.0
                gt_status = "Rework"

        # Dimensions around 400x100
        length_mm = 400.0 + float(rng.uniform(-3.0, 3.0))
        width_mm = 100.0 + float(rng.uniform(-1.5, 1.5))
        billet_id_text = f"H24-11{idx:02d}"

        billet = BilletSpec(
            center_mm=(320.0, float(rng.uniform(-15.0, 15.0))),
            angle_deg=float(rng.uniform(-8.0, 8.0)),
            length_mm=length_mm,
            width_mm=width_mm,
            id_text=billet_id_text,
            qr=(idx % 2 == 0),
            defect=defect_type,
            defect_size_mm=defect_size,
        )

        scene = SceneSpec(
            billets=(billet,),
            camera=CameraSpec(),
            effects=eff,
            with_marker=True,
        )
        img, gt = render_scene(scene, rng)

        # Background scene without billets
        bg_scene = SceneSpec(
            billets=(),
            camera=scene.camera,
            effects=eff,
            with_marker=True,
        )
        bg_img, _ = render_scene(bg_scene, np.random.default_rng(seed + idx))

        t_proc_start = time.perf_counter()

        # 1. Calibration & Rectify
        gray_bg = cast("NDArray[np.uint8]", cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY))
        marker_res = detect_marker(gray_bg)
        if marker_res is None:
            continue
        cal = calibrate_from_marker(marker_res[0], (1920, 1080))
        rectifier = build_rectifier(cal)

        rect_bgr = cast("NDArray[np.uint8]", rectifier.apply(img))
        rect_gray = cast("NDArray[np.uint8]", cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY))
        bg_gray = cast("NDArray[np.uint8]", cv2.cvtColor(rectifier.apply(bg_img), cv2.COLOR_BGR2GRAY))
        glare = glare_mask(rect_gray)

        # 2. Segment
        dets = segment(
            rect_gray,
            bg_gray,
            spec,
            roi=rectifier.roi,
            rect_px_per_mm=rectifier.rect_px_per_mm,
        )
        if not dets or not dets[0].full_inside:
            continue

        det = dets[0]

        # 3. Measure & Defects
        meas, crop = measure(
            det,
            rect_gray,
            rect_bgr,
            glare=glare,
            rect_px_per_mm=rectifier.rect_px_per_mm,
        )
        defects = detect_defects(meas, spec)

        # 4. OCR / QR
        crops = [crop] if crop is not None and crop.size > 0 else []
        id_res = read_id(
            crops=crops,
            ocr_fn=ocr_read,
            qr_fn=read_qr,
            template=spec.id_template,
        )
        pred_id = id_res.billet_id
        dec = decide(
            meas,
            defects,
            spec,
            id_result=id_res,
        )

        t_proc_ms = (time.perf_counter() - t_proc_start) * 1000.0

        # Metrology errors
        l_err = ((meas.length_mm - length_mm) / length_mm) * 100.0
        w_err = ((meas.width_mm - width_mm) / width_mm) * 100.0

        v_data = results_by_variant[variant]
        v_data["len_err"].append(l_err)
        v_data["wid_err"].append(w_err)
        v_data["process_ms"].append(t_proc_ms)

        # Defect accuracy
        detected_defect = len(defects.defects) > 0
        expected_defect = defect_type is not None
        v_data["defect_correct"].append(1 if (detected_defect == expected_defect) else 0)

        # OCR match
        clean_pred = pred_id.replace("-", "").upper() if pred_id else ""
        clean_true = billet_id_text.replace("-", "").upper()
        is_ocr_match = bool(clean_pred and clean_pred == clean_true)
        v_data["ocr_matches"].append(1 if is_ocr_match else 0)

        preds.append(dec.status)
        gts.append(gt_status)

    total_time_s = time.perf_counter() - total_start
    logger.info(f"Benchmark finished in {total_time_s:.2f} s across {len(preds)} valid scenes")

    # Build Variant Summaries
    all_len: list[float] = []
    all_wid: list[float] = []
    all_ocr: list[int] = []
    all_defects: list[int] = []
    all_times: list[float] = []

    variants_dict: dict[str, SyntheticVariant] = {}
    for v in VARIANTS:
        v_info = results_by_variant[v]
        v_n = len(v_info["len_err"])
        if v_n == 0:
            continue

        l_mae = compute_mae(v_info["len_err"])
        l_max = compute_max_error(v_info["len_err"])
        w_mae = compute_mae(v_info["wid_err"])
        w_max = compute_max_error(v_info["wid_err"])
        ocr_acc = float(np.mean(v_info["ocr_matches"])) if v_info["ocr_matches"] else None

        variants_dict[v] = SyntheticVariant(
            n=v_n,
            length_mae_pct=round(l_mae, 2),
            length_max_pct=round(l_max, 2),
            width_mae_pct=round(w_mae, 2),
            width_max_pct=round(w_max, 2),
            ocr_accuracy=round(ocr_acc, 4) if ocr_acc is not None else None,
        )

        all_len.extend(v_info["len_err"])
        all_wid.extend(v_info["wid_err"])
        all_ocr.extend(v_info["ocr_matches"])
        all_defects.extend(v_info["defect_correct"])
        all_times.extend(v_info["process_ms"])

    tot_n = len(all_len)
    overall_variant = SyntheticVariant(
        n=tot_n,
        length_mae_pct=round(compute_mae(all_len), 2),
        length_max_pct=round(compute_max_error(all_len), 2),
        width_mae_pct=round(compute_mae(all_wid), 2),
        width_max_pct=round(compute_max_error(all_wid), 2),
        ocr_accuracy=round(float(np.mean(all_ocr)), 4) if all_ocr else None,
    )

    confusion = compute_confusion_matrix(preds, gts)

    bench = SyntheticBench(
        n=tot_n,
        generated_at=time.time(),
        overall=overall_variant,
        variants=variants_dict,
        defect_accuracy=round(float(np.mean(all_defects)), 4) if all_defects else 1.0,
        mean_process_ms=round(float(np.mean(all_times)), 1) if all_times else 0.0,
    )

    report_payload = bench.model_dump()
    report_payload["source"] = "SYNTHETIC"
    report_payload["confusion_matrix"] = confusion

    return report_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic benchmark suite.")
    parser.add_argument("--n", type=int, default=180, help="Total synthetic scenes to run")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for generation")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "reports" / "bench_synthetic.json",
        help="Target output report path",
    )
    args = parser.parse_args()

    print(f"Starting BilletVision Synthetic Benchmark (N={args.n}, seed={args.seed})...")
    report = run_benchmark(n_scenes=args.n, seed=args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written successfully to {args.out}")

    # Print summary table
    print("\n" + "=" * 65)
    print(f"{'Variant':<12} {'N':<6} {'L-MAE%':<10} {'L-Max%':<10} {'W-MAE%':<10} {'W-Max%':<10}")
    print("-" * 65)
    for vname, vdata in report["variants"].items():
        print(
            f"{vname:<12} {vdata['n']:<6} {vdata['length_mae_pct']:<10} {vdata['length_max_pct']:<10} "
            f"{vdata['width_mae_pct']:<10} {vdata['width_max_pct']:<10}"
        )
    print("-" * 65)
    ov = report["overall"]
    print(
        f"{'OVERALL':<12} {ov['n']:<6} {ov['length_mae_pct']:<10} {ov['length_max_pct']:<10} "
        f"{ov['width_mae_pct']:<10} {ov['width_max_pct']:<10}"
    )
    print("=" * 65)
    print(f"Defect Accuracy: {report['defect_accuracy'] * 100:.1f}%")
    print(f"Mean Processing Time: {report['mean_process_ms']:.1f} ms")
    cm = report["confusion_matrix"]
    print(f"Wrong-PASS count: {cm['wrong_pass']} (rate: {cm['wrong_pass_rate'] * 100:.1f}%)")
    print(f"Source label: {report['source']}\n")


if __name__ == "__main__":
    main()
