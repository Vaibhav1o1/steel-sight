from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.schemas import Roi
from billetvision.vision.types import Detection, Measurement


def _find_crossing(
    t_arr: NDArray[np.float32],
    y_arr: NDArray[np.uint8],
    glare_arr: NDArray[np.uint8] | None,
    side: int,
    rough_t: float,
    level: float,
    polarity: int,
    max_dist: float,
) -> float:
    """Find sub-pixel zero-crossing of (y - level) * polarity nearest to rough_t on the given side."""
    f = (y_arr.astype(np.float64) - level) * polarity
    zero_crossings = np.where(f[:-1] * f[1:] <= 0)[0]
    if len(zero_crossings) == 0:
        return float(np.nan)

    cross_t: list[float] = []
    for idx in zero_crossings:
        if glare_arr is not None and (glare_arr[idx] > 0 or glare_arr[idx + 1] > 0):
            continue

        denom = f[idx + 1] - f[idx]
        if abs(denom) < 1e-6:
            ct = float(t_arr[idx])
        else:
            ct = float(t_arr[idx] + (t_arr[idx + 1] - t_arr[idx]) * (-f[idx] / denom))

        # Must lie on the expected side of the billet center
        if side < 0 and ct >= 0.0:
            continue
        if side > 0 and ct <= 0.0:
            continue
        if abs(ct - rough_t) > max_dist:
            continue

        cross_t.append(ct)

    if len(cross_t) == 0:
        return float(np.nan)

    best_idx = int(np.argmin([abs(ct - rough_t) for ct in cross_t]))
    return cross_t[best_idx]


def measure(
    detection: Detection,
    rect_gray: NDArray[np.uint8],
    rect_bgr: NDArray[np.uint8],
    glare: NDArray[np.uint8] | None = None,
    cfg: Any = None,
    roi: Roi | None = None,
    rect_px_per_mm: float | None = None,
) -> tuple[Measurement, NDArray[np.uint8]]:
    """Perform sub-pixel measurement on a detected billet.

    Computes 21-slice width profile, length, dense defect profile,
    sharpness, and upright BGR crop.
    """
    if cfg is None:
        import billetvision.config as default_cfg

        cfg = default_cfg

    r = float(rect_px_per_mm if rect_px_per_mm is not None else cfg.RECT_PX_PER_MM)
    roi_val = roi if roi is not None else Roi(**cfg.ROI_DEFAULT)
    n_slices = int(getattr(cfg, "N_SLICES", 21))
    slice_span = float(getattr(cfg, "SLICE_SPAN", 0.9))
    sample_step_px = float(getattr(cfg, "SAMPLE_STEP_PX", 0.25))
    search_margin_mm = float(getattr(cfg, "SEARCH_MARGIN_MM", 8.0))
    measure_blur_sigma = float(getattr(cfg, "MEASURE_BLUR_SIGMA", 1.0))
    crop_pad_mm = float(getattr(cfg, "CROP_PAD_MM", 4.0))

    # 1. Geometry from detection
    c_px = np.array(
        [
            (detection.center_mm[0] - roi_val.x0_mm) * r,
            (detection.center_mm[1] - roi_val.y0_mm) * r,
        ],
        dtype=np.float64,
    )
    theta_deg = detection.angle_deg
    theta_rad = np.radians(theta_deg)
    u = np.array([np.cos(theta_rad), np.sin(theta_rad)], dtype=np.float64)
    v = np.array([-np.sin(theta_rad), np.cos(theta_rad)], dtype=np.float64)

    rough_l_px = detection.rough_length_mm * r
    rough_w_px = detection.rough_width_mm * r
    m_px = search_margin_mm * r

    # 2. Blurred image and intensity levels
    ksize = max(3, int(np.ceil(measure_blur_sigma * 3.0)) * 2 + 1)
    blurred_gray = cv2.GaussianBlur(rect_gray, (ksize, ksize), measure_blur_sigma)

    mask = np.zeros(rect_gray.shape, dtype=np.uint8)
    cv2.drawContours(mask, [detection.contour_px], -1, 255, -1)

    erode_k = max(3, int(round(3.0 * r)) | 1)
    fg_mask = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (erode_k, erode_k)))
    if not np.any(fg_mask):
        fg_mask = mask
    i_fg = float(np.median(blurred_gray[fg_mask > 0]))

    d1_k = max(3, int(round(3.0 * r)) | 1)
    d2_k = max(3, int(round(8.0 * r)) | 1)
    m1 = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (d1_k, d1_k)))
    m2 = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (d2_k, d2_k)))
    bg_ring = (m2 > 0) & (m1 == 0)
    i_bg = float(np.median(blurred_gray[bg_ring])) if np.any(bg_ring) else 28.0

    level = (i_fg + i_bg) / 2.0
    polarity = 1 if i_fg >= i_bg else -1

    # 3. 21 Width slices
    t_vals = np.arange(
        -(rough_w_px / 2.0 + m_px),
        rough_w_px / 2.0 + m_px + sample_step_px,
        sample_step_px,
        dtype=np.float32,
    )
    m_t = len(t_vals)
    s_vals = (
        np.array(
            [-slice_span / 2.0 + k * slice_span / (n_slices - 1) for k in range(n_slices)],
            dtype=np.float64,
        )
        * rough_l_px
    )

    pts_x = np.zeros((n_slices, m_t), dtype=np.float32)
    pts_y = np.zeros((n_slices, m_t), dtype=np.float32)
    for k, s_k in enumerate(s_vals):
        ck = c_px + s_k * u
        pts_x[k] = ck[0] + t_vals * v[0]
        pts_y[k] = ck[1] + t_vals * v[1]

    sampled_gray = cv2.remap(
        blurred_gray, pts_x, pts_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
    sampled_glare: NDArray[np.uint8] | None = None
    if glare is not None:
        sampled_glare = cv2.remap(
            glare,
            pts_x,
            pts_y,
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

    raw_widths: list[float] = []
    for k in range(n_slices):
        glare_k = sampled_glare[k] if sampled_glare is not None else None
        t_left = _find_crossing(
            t_vals, sampled_gray[k], glare_k, -1, -rough_w_px / 2.0, level, polarity, m_px
        )
        t_right = _find_crossing(t_vals, sampled_gray[k], glare_k, 1, rough_w_px / 2.0, level, polarity, m_px)
        if np.isnan(t_left) or np.isnan(t_right):
            raw_widths.append(float(np.nan))
        else:
            raw_widths.append(float((t_right - t_left) / r))

    widths_arr = np.array(raw_widths, dtype=np.float64)
    valid_mask = ~np.isnan(widths_arr)
    valid_slices = int(np.sum(valid_mask))

    if valid_slices == 0:
        clean_widths = np.full(n_slices, detection.rough_width_mm, dtype=np.float64)
    elif valid_slices == n_slices:
        clean_widths = widths_arr
    else:
        valid_indices = np.where(valid_mask)[0]
        clean_widths = np.interp(np.arange(n_slices), valid_indices, widths_arr[valid_indices])

    width_profile_mm = tuple(float(w) for w in clean_widths)
    width_mm = float(np.median(clean_widths))

    # 4. Length (3 lines along u at offsets 0, +-W/4)
    t_len_vals = np.arange(
        -(rough_l_px / 2.0 + m_px),
        rough_l_px / 2.0 + m_px + sample_step_px,
        sample_step_px,
        dtype=np.float32,
    )
    m_len_t = len(t_len_vals)
    offsets_v = [0.0, -rough_w_px / 4.0, rough_w_px / 4.0]

    pts_len_x = np.zeros((3, m_len_t), dtype=np.float32)
    pts_len_y = np.zeros((3, m_len_t), dtype=np.float32)
    for i, off in enumerate(offsets_v):
        c_off = c_px + off * v
        pts_len_x[i] = c_off[0] + t_len_vals * u[0]
        pts_len_y[i] = c_off[1] + t_len_vals * u[1]

    sampled_len_gray = cv2.remap(
        blurred_gray,
        pts_len_x,
        pts_len_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    sampled_len_glare: NDArray[np.uint8] | None = None
    if glare is not None:
        sampled_len_glare = cv2.remap(
            glare,
            pts_len_x,
            pts_len_y,
            interpolation=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

    measured_lengths: list[float] = []
    for i in range(3):
        glare_line = sampled_len_glare[i] if sampled_len_glare is not None else None
        t_start = _find_crossing(
            t_len_vals, sampled_len_gray[i], glare_line, -1, -rough_l_px / 2.0, level, polarity, m_px
        )
        t_end = _find_crossing(
            t_len_vals, sampled_len_gray[i], glare_line, 1, rough_l_px / 2.0, level, polarity, m_px
        )
        if not np.isnan(t_start) and not np.isnan(t_end):
            measured_lengths.append(float((t_end - t_start) / r))

    if len(measured_lengths) > 0:
        length_mm = float(np.median(measured_lengths))
    else:
        length_mm = float(detection.rough_length_mm)

    # 5. Dense profile (for defects)
    pad_dense = 10.0 * r
    crop_w = int(round(rough_l_px + 2 * pad_dense))
    crop_h = int(round(rough_w_px + 2 * pad_dense))

    m_rot = cv2.getRotationMatrix2D((float(c_px[0]), float(c_px[1])), theta_deg, 1.0)
    m_rot[0, 2] += crop_w / 2.0 - c_px[0]
    m_rot[1, 2] += crop_h / 2.0 - c_px[1]

    rot_mask = cv2.warpAffine(mask, m_rot, (crop_w, crop_h), flags=cv2.INTER_NEAREST)

    pos_mm: list[float] = []
    top_mm: list[float] = []
    bot_mm: list[float] = []
    y_mid = crop_h / 2.0
    x_mid = crop_w / 2.0

    for x in range(crop_w):
        col = rot_mask[:, x]
        fg_rows = np.where(col > 0)[0]
        if len(fg_rows) > 0:
            pos_mm.append((x - x_mid) / r)
            top_mm.append((y_mid - fg_rows[0]) / r)
            bot_mm.append((y_mid - fg_rows[-1]) / r)

    dense_pos_mm = np.array(pos_mm, dtype=np.float64)
    dense_top_mm = np.array(top_mm, dtype=np.float64)
    dense_bottom_mm = np.array(bot_mm, dtype=np.float64)

    # 6. Sharpness
    rot_gray = cv2.warpAffine(rect_gray, m_rot, (crop_w, crop_h), flags=cv2.INTER_LINEAR)
    x0 = int(round(x_mid - rough_l_px / 2.0))
    x1 = int(round(x_mid + rough_l_px / 2.0))
    y0 = int(round(y_mid - rough_w_px / 2.0))
    y1 = int(round(y_mid + rough_w_px / 2.0))
    billet_crop_gray = rot_gray[max(0, y0) : min(crop_h, y1), max(0, x0) : min(crop_w, x1)]
    sharpness = float(cv2.Laplacian(billet_crop_gray, cv2.CV_64F).var()) if billet_crop_gray.size > 0 else 0.0

    # 7. Upright BGR crop for OCR
    pad_ocr = int(round(crop_pad_mm * r))
    ocr_w = int(round(rough_l_px + 2 * pad_ocr))
    ocr_h = int(round(rough_w_px + 2 * pad_ocr))

    m_ocr = cv2.getRotationMatrix2D((float(c_px[0]), float(c_px[1])), theta_deg, 1.0)
    m_ocr[0, 2] += ocr_w / 2.0 - c_px[0]
    m_ocr[1, 2] += ocr_h / 2.0 - c_px[1]

    upright_bgr = cv2.warpAffine(rect_bgr, m_ocr, (ocr_w, ocr_h), flags=cv2.INTER_LINEAR)

    measurement = Measurement(
        length_mm=length_mm,
        width_mm=width_mm,
        width_profile_mm=width_profile_mm,
        valid_slices=valid_slices,
        dense_pos_mm=dense_pos_mm,
        dense_top_mm=dense_top_mm,
        dense_bottom_mm=dense_bottom_mm,
        sharpness=sharpness,
        angle_deg=theta_deg,
    )

    return measurement, upright_bgr
