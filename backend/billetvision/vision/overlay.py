from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision.schemas import Roi
from billetvision.vision.types import Detection, Track

BGRImage = NDArray[np.uint8]


def draw_detections(
    image: BGRImage,
    detections: list[Detection],
    roi: Roi,
    px_per_mm: float,
) -> BGRImage:
    """Draw bounding boxes and basic info on detected billets."""
    out = image.copy()
    
    # Draw ROI
    x0, y0 = int((0 - roi.x0_mm) * px_per_mm), int((0 - roi.y0_mm) * px_per_mm)
    w, h = int(roi.w_mm * px_per_mm), int(roi.h_mm * px_per_mm)
    
    cv2.rectangle(
        out,
        (x0, y0),
        (x0 + w, y0 + h),
        (255, 255, 0),
        2,
    )

    for det in detections:
        # Bounding box color (PRD E-11)
        if det.merged:
            color = (0, 0, 255)  # Red
        elif not det.full_inside:
            color = (0, 165, 255)  # Orange
        else:
            color = (0, 255, 0)  # Green

        pts = det.contour_px.astype(np.int32)
        cv2.drawContours(out, [pts], 0, color, 2)
        
        # Center in px
        cx_px = int((det.center_mm[0] - roi.x0_mm) * px_per_mm)
        cy_px = int((det.center_mm[1] - roi.y0_mm) * px_per_mm)
        cv2.circle(out, (cx_px, cy_px), 4, color, -1)
        
        # Draw text at center rotated (PRD E-12)
        # For simple detection, just draw basic text
        text = f"{det.rough_length_mm:.0f}x{det.rough_width_mm:.0f}"
        cv2.putText(
            out, text, (cx_px - 40, cy_px - 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
        )

    return out


def draw_tracks(
    image: BGRImage,
    tracks: list[Track],
    roi: Roi,
    px_per_mm: float,
) -> BGRImage:
    """Draw tracks on the image."""
    out = image.copy()
    for trk in tracks:
        det = trk.latest_detection
        if det.merged:
            color = (0, 0, 255)
        elif not det.full_inside:
            color = (0, 165, 255)
        else:
            color = (0, 255, 0)
            
        pts = det.contour_px.astype(np.int32)
        cv2.drawContours(out, [pts], 0, color, 2)
        
        cx_px = int((det.center_mm[0] - roi.x0_mm) * px_per_mm)
        cy_px = int((det.center_mm[1] - roi.y0_mm) * px_per_mm)
        
        # Draw track ID and samples count
        text = f"T{trk.id} s={len(trk.samples)}"
        cv2.putText(
            out, text, (cx_px - 40, cy_px),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )
        
    return out


def draw_hud(
    image: BGRImage,
    calibrated: bool,
    paused: bool,
    fps: float,
    spec_id: str,
) -> BGRImage:
    """Draw top banner HUD."""
    out = image.copy()
    if not calibrated:
        banner = "CALIBRATE FIRST"
        colour = (0, 0, 255)
    elif paused:
        banner = "PAUSED"
        colour = (0, 200, 255)
    else:
        banner = f"{spec_id}  {fps:.0f} fps"
        colour = (80, 220, 80)
    cv2.rectangle(
        out, (0, 0), (out.shape[1], 48), (0, 0, 0), thickness=-1
    )
    cv2.putText(
        out, banner, (16, 34),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, colour, 2, cv2.LINE_AA,
    )
    return out
