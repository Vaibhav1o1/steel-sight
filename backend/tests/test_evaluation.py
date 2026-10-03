from __future__ import annotations

import json
from pathlib import Path

from billetvision.evaluation import (
    compute_confusion_matrix,
    compute_mae,
    compute_max_error,
    compute_p95,
    compute_repeatability,
    compute_within_threshold,
    evaluate_real,
    evaluate_records,
    load_ground_truth,
)
from tools.collect_ground_truth import append_ground_truth


def test_basic_metrics_calculators() -> None:
    errors = [-0.5, 0.5, 1.0, -1.0, 0.0]
    assert compute_mae(errors) == 0.6
    assert compute_max_error(errors) == 1.0
    assert compute_p95(errors) <= 1.0
    assert compute_within_threshold(errors, threshold=1.0) == 1.0
    assert compute_within_threshold(errors, threshold=0.5) == 0.6

    # Repeatability
    vals = [100.0, 100.2, 99.8, 100.1, 99.9]
    rep = compute_repeatability(vals)
    assert 0.1 < rep < 0.2


def test_confusion_matrix_and_wrong_pass() -> None:
    # 2 Pass, 1 Fail called Fail, 1 Fail called Pass (wrong pass!)
    preds = ["Pass", "Pass", "Fail", "Pass"]
    gts = ["Pass", "Pass", "Fail", "Fail"]

    res = compute_confusion_matrix(preds, gts)
    assert res["n"] == 4
    assert res["overall_accuracy"] == 0.75
    assert res["wrong_pass"] == 1
    assert res["wrong_pass_rate"] == 0.25
    assert res["matrix"]["Fail"]["Pass"] == 1


def test_ground_truth_loading_and_evaluation(tmp_path: Path) -> None:
    gt_csv = tmp_path / "ground_truth.csv"
    append_ground_truth(
        gt_csv,
        obj_id="PROP-01",
        length_mm=500.0,
        width_mm=100.0,
        resolution_mm=0.05,
        condition="nominal",
        notes="Calibration reference bar",
    )
    append_ground_truth(
        gt_csv,
        obj_id="PROP-02",
        length_mm=400.0,
        width_mm=80.0,
        condition="notch",
    )

    loaded = load_ground_truth(gt_csv)
    assert len(loaded) == 2
    assert loaded["PROP-01"]["length_mm"] == 500.0
    assert loaded["PROP-01"]["width_mm"] == 100.0

    # Test evaluation
    sample_records = [
        {
            "billet_id": "PROP-01",
            "qr_text": "PROP-01",
            "ocr_text": "PROP-01",
            "length_mm": 501.0,  # +0.2% error
            "width_mm": 100.5,  # +0.5% error
            "status": "Pass",
        },
        {
            "billet_id": "PROP-02",
            "qr_text": "PROP-02",
            "ocr_text": "PROP-02",
            "length_mm": 399.0,  # -0.25% error
            "width_mm": 80.2,  # +0.25% error
            "status": "Fail",
        },
        {
            "billet_id": "UNKNOWN",
            "length_mm": 300.0,
            "width_mm": 50.0,
            "status": "Pass",
        },
    ]

    ev = evaluate_records(sample_records, loaded, source_label="REAL")
    assert ev is not None
    assert ev["source"] == "REAL"
    assert ev["n_inspections"] == 2
    assert ev["within_1pct_rate"] == 1.0
    assert ev["ocr_accuracy"] == 1.0
    assert ev["n_props_seen"] == 2

    # evaluate_real helper
    real_res = evaluate_real(sample_records, props_csv_path=gt_csv)
    assert real_res is not None
    assert real_res.n_inspections == 2
    assert len(real_res.props) == 2


def test_bench_synthetic_small_run(tmp_path: Path) -> None:
    from tools.bench_synthetic import run_benchmark

    # Run 9 scenes (1 per variant)
    report = run_benchmark(n_scenes=9, seed=123)

    assert report["source"] == "SYNTHETIC"
    assert report["n"] >= 8  # all or nearly all valid detections
    assert "overall" in report
    assert "variants" in report
    assert "confusion_matrix" in report
    assert report["overall"]["length_mae_pct"] < 2.0
    assert report["overall"]["width_mae_pct"] < 2.0

    out_file = tmp_path / "bench.json"
    out_file.write_text(json.dumps(report))
    assert out_file.is_file()
