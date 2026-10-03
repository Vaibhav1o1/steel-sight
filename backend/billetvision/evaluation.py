from __future__ import annotations

import csv
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from billetvision.schemas import EvalReal, PropAccuracy

logger = logging.getLogger(__name__)


def compute_mae(errors: Sequence[float]) -> float:
    """Mean absolute error (in percent or units)."""
    if not errors:
        return 0.0
    return float(np.mean(np.abs(errors)))


def compute_max_error(errors: Sequence[float]) -> float:
    """Maximum absolute error."""
    if not errors:
        return 0.0
    return float(np.max(np.abs(errors)))


def compute_p95(errors: Sequence[float]) -> float:
    """95th percentile of absolute error."""
    if not errors:
        return 0.0
    return float(np.percentile(np.abs(errors), 95))


def compute_within_threshold(errors: Sequence[float], threshold: float = 1.0) -> float:
    """Fraction of errors whose absolute value is within the given threshold (0.0 to 1.0)."""
    if not errors:
        return 0.0
    arr = np.abs(errors)
    return float(np.mean(arr <= threshold))


def compute_repeatability(values: Sequence[float]) -> float:
    """Sample standard deviation (repeatability) of measurements."""
    if len(values) < 2:
        return 0.0
    return float(np.std(values, ddof=1))


def compute_confusion_matrix(
    predictions: Sequence[str],
    ground_truths: Sequence[str],
) -> dict[str, Any]:
    """Compute inspection decision confusion matrix.

    Specifically isolates wrong-PASS (critical failure: defective/rework billet passed).
    """
    total = len(predictions)
    if total == 0:
        return {
            "n": 0,
            "pass_accuracy": 0.0,
            "wrong_pass": 0,
            "wrong_pass_rate": 0.0,
            "matrix": {},
        }

    matrix: dict[str, dict[str, int]] = {}
    wrong_pass = 0
    correct = 0

    for pred, gt in zip(predictions, ground_truths, strict=False):
        matrix.setdefault(gt, {})
        matrix[gt][pred] = matrix[gt].get(pred, 0) + 1

        if pred == gt:
            correct += 1

        # Safety-critical: Ground truth was Fail or Rework, but system called Pass
        if gt in ("Fail", "Rework", "Defective") and pred == "Pass":
            wrong_pass += 1

    return {
        "n": total,
        "overall_accuracy": float(correct / total),
        "wrong_pass": wrong_pass,
        "wrong_pass_rate": float(wrong_pass / total),
        "matrix": matrix,
    }


def load_ground_truth(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load ground truth from data/ground_truth.csv or data/props.csv."""
    p = Path(path)
    if not p.is_file():
        return {}

    gt: dict[str, dict[str, Any]] = {}
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            obj_id = row.get("object_id") or row.get("id") or row.get("prop_id")
            if not obj_id:
                continue

            l_str = row.get("true_length_mm") or row.get("length_mm")
            w_str = row.get("true_width_mm") or row.get("width_mm")
            if not l_str or not w_str:
                continue

            try:
                l_val = float(l_str)
                w_val = float(w_str)
            except ValueError:
                continue

            res_mm = float(row.get("instrument_resolution_mm", 0.05))
            condition = row.get("condition", "nominal")

            gt[obj_id] = {
                "id": obj_id,
                "length_mm": l_val,
                "width_mm": w_val,
                "resolution_mm": res_mm,
                "condition": condition,
            }
    return gt


def evaluate_records(
    records: Sequence[dict[str, Any]],
    ground_truth: dict[str, dict[str, Any]],
    source_label: str = "REAL",
) -> dict[str, Any] | None:
    """Evaluate inspection records against ground truth data."""
    if not ground_truth or not records:
        return None

    matched_records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for r in records:
        key = r.get("qr_text") or r.get("billet_id")
        if key and key in ground_truth:
            matched_records.append((r, ground_truth[key]))

    if not matched_records:
        return None

    length_errs_pct: list[float] = []
    width_errs_pct: list[float] = []
    both_within_1pct = 0
    ocr_matches = 0
    ocr_n = 0
    any_id_count = 0

    per_prop_data: dict[str, dict[str, list[Any]]] = {}

    for r, gt in matched_records:
        prop_id = gt["id"]
        gt_l = gt["length_mm"]
        gt_w = gt["width_mm"]

        m_l = float(r.get("length_mm", 0.0))
        m_w = float(r.get("width_mm", 0.0))

        l_err = ((m_l - gt_l) / max(gt_l, 1e-6)) * 100.0
        w_err = ((m_w - gt_w) / max(gt_w, 1e-6)) * 100.0

        length_errs_pct.append(l_err)
        width_errs_pct.append(w_err)

        if abs(l_err) <= 1.0 and abs(w_err) <= 1.0:
            both_within_1pct += 1

        if r.get("billet_id"):
            any_id_count += 1

        qr = r.get("qr_text")
        ocr = r.get("ocr_text")
        if qr:
            ocr_n += 1
            if ocr and ocr.strip().upper() == qr.strip().upper():
                ocr_matches += 1

        if prop_id not in per_prop_data:
            per_prop_data[prop_id] = {
                "lengths": [],
                "widths": [],
                "l_errs": [],
                "w_errs": [],
                "ocr_correct": [],
            }
        per_prop_data[prop_id]["lengths"].append(m_l)
        per_prop_data[prop_id]["widths"].append(m_w)
        per_prop_data[prop_id]["l_errs"].append(l_err)
        per_prop_data[prop_id]["w_errs"].append(w_err)
        if qr and ocr:
            matched = 1 if ocr.strip().upper() == qr.strip().upper() else 0
            per_prop_data[prop_id]["ocr_correct"].append(matched)

    n_total = len(matched_records)
    props_list: list[PropAccuracy] = []

    for pid, pdata in per_prop_data.items():
        gt_item = ground_truth[pid]
        p_n = len(pdata["lengths"])
        mean_l = float(np.mean(pdata["lengths"]))
        mean_w = float(np.mean(pdata["widths"]))
        l_err_mean = float(np.mean(pdata["l_errs"]))
        w_err_mean = float(np.mean(pdata["w_errs"]))
        max_abs_err = float(max(np.max(np.abs(pdata["l_errs"])), np.max(np.abs(pdata["w_errs"]))))
        ocr_rate = float(np.mean(pdata["ocr_correct"])) if pdata["ocr_correct"] else None

        props_list.append(
            PropAccuracy(
                prop_id=pid,
                gt_length_mm=gt_item["length_mm"],
                gt_width_mm=gt_item["width_mm"],
                n=p_n,
                mean_length_mm=round(mean_l, 2),
                mean_width_mm=round(mean_w, 2),
                length_error_pct=round(l_err_mean, 2),
                width_error_pct=round(w_err_mean, 2),
                max_abs_error_pct=round(max_abs_err, 2),
                ocr_correct_rate=round(ocr_rate, 2) if ocr_rate is not None else None,
            )
        )

    eval_real = EvalReal(
        n_inspections=n_total,
        n_props_seen=len(props_list),
        length_mae_pct=round(compute_mae(length_errs_pct), 2),
        length_p95_pct=round(compute_p95(length_errs_pct), 2),
        width_mae_pct=round(compute_mae(width_errs_pct), 2),
        width_p95_pct=round(compute_p95(width_errs_pct), 2),
        within_1pct_rate=round(both_within_1pct / n_total, 4),
        ocr_accuracy=round(ocr_matches / ocr_n, 4) if ocr_n > 0 else None,
        ocr_n=ocr_n,
        read_rate=round(any_id_count / n_total, 4),
        props=props_list,
    )

    out = eval_real.model_dump()
    out["source"] = source_label
    out["n"] = n_total
    l_vals = [r[0].get("length_mm", 0.0) for r in matched_records]
    w_vals = [r[0].get("width_mm", 0.0) for r in matched_records]
    out["length_repeatability_mm"] = round(compute_repeatability(l_vals), 2)
    out["width_repeatability_mm"] = round(compute_repeatability(w_vals), 2)
    return out


def evaluate_real(
    inspections: Sequence[dict[str, Any]],
    props_csv_path: str | Path | None = None,
) -> EvalReal | None:
    """Entry point for /eval -> real endpoint, adhering to EvalReal contract."""
    from billetvision import config

    path = props_csv_path or config.PROPS_CSV
    gt = load_ground_truth(path)
    if not gt:
        # Fall back to data/ground_truth.csv if props.csv was missing
        alt = Path(path).parent / "ground_truth.csv"
        gt = load_ground_truth(alt)

    res = evaluate_records(inspections, gt, source_label="REAL")
    if res is None:
        return None
    cleaned = {k: v for k, v in res.items() if k in EvalReal.model_fields}
    return EvalReal.model_validate(cleaned)
