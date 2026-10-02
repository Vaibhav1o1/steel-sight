from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.schemas import Roi, Spec
from billetvision.vision.types import Detection


def segment(
    rect_gray: NDArray[np.uint8],
    background: NDArray[np.uint8] | None,
    spec: Spec,
    cfg: Any = None,
    roi: Roi | None = None,
    rect_px_per_mm: float | None = None,
) -> list[Detection]:
    """Segment billets from a rectified greyscale frame.

    Applies background subtraction or CLAHE-Otsu, morphological filtering,
    and minAreaRect analysis to detect billets and compute geometric properties.
    """
    if cfg is None:
        import billetvision.config as default_cfg

        cfg = default_cfg

    r = float(rect_px_per_mm if rect_px_per_mm is not None else cfg.RECT_PX_PER_MM)
    roi_val = roi if roi is not None else Roi(**cfg.ROI_DEFAULT)
    seg_blur_sigma = float(getattr(cfg, "SEG_BLUR_SIGMA", 1.5))
    diff_min = int(getattr(cfg, "DIFF_MIN", 25))
    close_kernel_mm = float(getattr(cfg, "CLOSE_KERNEL_MM", 4.0))
    open_kernel_mm = float(getattr(cfg, "OPEN_KERNEL_MM", 2.0))
    edge_margin_mm = float(getattr(cfg, "EDGE_MARGIN_MM", 5.0))
    min_aspect = float(getattr(cfg, "MIN_ASPECT", 1.5))

    # 1. Blur
    ksize = max(3, int(np.ceil(seg_blur_sigma * 3.0)) * 2 + 1)
    blurred = cv2.GaussianBlur(rect_gray, (ksize, ksize), seg_blur_sigma)

    # 2. Thresholding
    if background is not None:
        bg_blurred = cv2.GaussianBlur(background, (ksize, ksize), seg_blur_sigma)
        diff = cv2.absdiff(blurred, bg_blurred)
        otsu_val, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh_val = max(int(otsu_val), diff_min)
        _, thresh = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)
        h, w = enhanced.shape
        border_mask = np.ones((h, w), dtype=bool)
        border_mask[int(0.1 * h) : int(0.9 * h), int(0.1 * w) : int(0.9 * w)] = False
        mean_border = float(np.mean(enhanced[border_mask]))
        mean_center = float(np.mean(enhanced[~border_mask]))
        if mean_border > mean_center:
            enhanced = 255 - enhanced
        _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 3. Morphology: close -> open -> fill holes
    close_k = max(3, int(round(close_kernel_mm * r)) | 1)
    open_k = max(3, int(round(open_kernel_mm * r)) | 1)
    close_elem = cv2.getStructuringElement(cv2.MORPH_RECT, (close_k, close_k))
    open_elem = cv2.getStructuringElement(cv2.MORPH_RECT, (open_k, open_k))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_elem)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, open_elem)

    temp_cnts, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask_filled = np.zeros_like(opened)
    cv2.drawContours(mask_filled, temp_cnts, -1, 255, -1)

    # 4. External contours and filtering
    contours, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    nominal_area_mm2 = spec.nominal_length_mm * spec.nominal_width_mm
    h_img, w_img = rect_gray.shape
    margin_px = edge_margin_mm * r

    detections: list[Detection] = []

    for cnt in contours:
        if len(cnt) < 4:
            continue

        rect = cv2.minAreaRect(cnt)
        (cx_px, cy_px), (w_box, h_box), _ = rect
        rough_len_px = max(w_box, h_box)
        rough_wid_px = min(w_box, h_box)
        rough_len_mm = rough_len_px / r
        rough_wid_mm = rough_wid_px / r

        aspect = rough_len_mm / max(rough_wid_mm, 1e-6)
        if aspect < min_aspect:
            continue

        area_mm2 = float(cv2.contourArea(cnt) / (r * r))
        if area_mm2 < spec.min_area_factor * nominal_area_mm2:
            continue
        if area_mm2 > spec.max_area_factor * 1.5 * nominal_area_mm2:
            continue

        # Check if merged
        merged = bool(area_mm2 > spec.max_area_factor * nominal_area_mm2)

        # 5. full_inside
        pts = cnt.reshape(-1, 2)
        min_x = float(np.min(pts[:, 0]))
        max_x = float(np.max(pts[:, 0]))
        min_y = float(np.min(pts[:, 1]))
        max_y = float(np.max(pts[:, 1]))

        full_inside = bool(
            min_x >= margin_px
            and max_x <= (w_img - 1 - margin_px)
            and min_y >= margin_px
            and max_y <= (h_img - 1 - margin_px)
        )

        # 6. angle_deg normalized into (-90, 90]
        box_pts = cv2.boxPoints(rect)
        v01 = box_pts[1] - box_pts[0]
        v12 = box_pts[2] - box_pts[1]
        v_long = v01 if np.linalg.norm(v01) >= np.linalg.norm(v12) else v12

        theta = float(np.degrees(np.arctan2(v_long[1], v_long[0])))
        while theta <= -90.0:
            theta += 180.0
        while theta > 90.0:
            theta -= 180.0

        # Center in bed mm
        cx_mm = float(cx_px / r + roi_val.x0_mm)
        cy_mm = float(cy_px / r + roi_val.y0_mm)

        detections.append(
            Detection(
                contour_px=pts,
                center_mm=(cx_mm, cy_mm),
                angle_deg=theta,
                rough_length_mm=rough_len_mm,
                rough_width_mm=rough_wid_mm,
                area_mm2=area_mm2,
                full_inside=full_inside,
                merged=merged,
            )
        )

    # Sort deterministically by longitudinal center coordinate (X)
    detections.sort(key=lambda d: d.center_mm[0])
    return detections
