from __future__ import annotations

from typing import Any

import numpy as np

from billetvision.schemas import Spec
from billetvision.vision.types import DefectResult, Measurement


def _find_runs_spanning(
    condition: np.ndarray,
    pos: np.ndarray,
    min_span_mm: float,
) -> bool:
    """Check if there is a contiguous run of True in condition spanning >= min_span_mm."""
    indices = np.where(condition)[0]
    if len(indices) == 0:
        return False

    splits = np.where(np.diff(indices) > 1)[0]
    runs = np.split(indices, splits + 1)
    for run in runs:
        if len(run) > 1:
            span = float(pos[run[-1]] - pos[run[0]])
            if span >= min_span_mm:
                return True
    return False


def detect_defects(
    measurement: Measurement,
    spec: Spec,
    cfg: Any = None,
) -> DefectResult:
    """Analyze dense and slice profiles to detect geometrical defects.

    Detects notches, bulges, taper, camber, and cross-section variation.
    """
    if cfg is None:
        import billetvision.config as default_cfg

        cfg = default_cfg

    end_exclude_mm = float(getattr(cfg, "END_EXCLUDE_MM", 10.0))
    defect_min_span_mm = float(getattr(cfg, "DEFECT_MIN_SPAN_MM", 3.0))

    # 1. Cross-section variation and min/max width from 21-slice profile
    slices = np.array(measurement.width_profile_mm, dtype=np.float64)
    min_w = float(np.min(slices))
    max_w = float(np.max(slices))
    med_w = float(np.median(slices))
    cs_var_pct = float((max_w - min_w) / max(med_w, 1e-6) * 100.0)

    # 2. Dense profile filtering
    pos = measurement.dense_pos_mm
    top = measurement.dense_top_mm
    bot = measurement.dense_bottom_mm

    if len(pos) < 10:
        return DefectResult(
            width_variation_pct=cs_var_pct,
            taper_mm=0.0,
            camber_mm=0.0,
            min_width_mm=min_w,
            max_width_mm=max_w,
            defects=(),
            notch_depth_mm=0.0,
        )

    pos_min = float(np.min(pos))
    pos_max = float(np.max(pos))
    valid = (pos >= pos_min + end_exclude_mm) & (pos <= pos_max - end_exclude_mm)
    if int(np.sum(valid)) < 10:
        valid = np.ones(len(pos), dtype=bool)

    pos_sub = pos[valid]
    top_sub = top[valid]
    bot_sub = bot[valid]

    w_sub = np.abs(top_sub - bot_sub)
    med_dense_w = float(np.median(w_sub))

    defects: list[str] = []
    notch_depth_mm = 0.0

    # 3. Notch detection
    notch_min_mm = float(spec.notch_min_mm)
    notch_thresh = med_dense_w - notch_min_mm
    notch_cond = w_sub < notch_thresh
    if _find_runs_spanning(notch_cond, pos_sub, defect_min_span_mm):
        defects.append("notch")
        notch_depth_mm = float(max(0.0, med_dense_w - np.min(w_sub[notch_cond])))

    # 4. Bulge detection
    bulge_thresh = med_dense_w + notch_min_mm
    bulge_cond = w_sub > bulge_thresh
    if _find_runs_spanning(bulge_cond, pos_sub, defect_min_span_mm):
        defects.append("bulge")

    # 5. Taper detection (least-squares linear fit of width vs position)
    slope_w, _ = np.polyfit(pos_sub, w_sub, 1)
    span_x = float(np.max(pos_sub) - np.min(pos_sub))
    taper_mm = float(abs(slope_w) * span_x)
    if taper_mm > spec.taper_max_mm:
        defects.append("taper")

    # 6. Camber detection (maximum deviation of centerline from best-fit line)
    centerline = (top_sub + bot_sub) / 2.0
    slope_c, int_c = np.polyfit(pos_sub, centerline, 1)
    fit_line = slope_c * pos_sub + int_c
    camber_mm = float(np.max(np.abs(centerline - fit_line)))
    if camber_mm > spec.camber_max_mm:
        defects.append("camber")

    return DefectResult(
        width_variation_pct=cs_var_pct,
        taper_mm=taper_mm,
        camber_mm=camber_mm,
        min_width_mm=min_w,
        max_width_mm=max_w,
        defects=tuple(defects),
        notch_depth_mm=notch_depth_mm,
    )
