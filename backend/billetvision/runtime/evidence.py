from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.enums import InspectionStatus
from billetvision.schemas import Inspection

logger = logging.getLogger(__name__)


def generate_evidence(
    inspection: Inspection,
    best_crop: NDArray[np.uint8],
) -> str | None:
    """Generate annotated evidence JPEG and save it to disk.

    Returns the evidence URL if generated, or None if skipped.
    """
    if inspection.status == InspectionStatus.Pass:
        return None

    evidence_dir = Path(config.SNAPSHOT_DIR) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{inspection.id}.jpg"
    filepath = evidence_dir / filename

    h, w = best_crop.shape[:2]
    # We want a panel on the right for text.
    panel_w = 400
    canvas = np.zeros((max(h, 300), w + panel_w, 3), dtype=np.uint8)
    
    # Paste crop
    canvas[:h, :w] = best_crop

    # Draw outline (box around crop)
    color = (0, 0, 255) if inspection.status == InspectionStatus.Fail else (0, 200, 255)
    cv2.rectangle(canvas, (0, 0), (w - 1, h - 1), color, 3)

    # Draw text panel
    lines = [
        f"ID: {inspection.billet_id or 'UNKNOWN'}",
        f"Status: {inspection.status}",
        f"L: {inspection.length_mm:.1f} mm",
        f"W: {inspection.width_mm:.1f} mm",
        f"Notch Depth: {inspection.defects.count('notch') and 'Yes' or 'None'}",
        f"Reasons: {', '.join(inspection.reasons) if inspection.reasons else 'None'}",
    ]

    y = 40
    for line in lines:
        cv2.putText(
            canvas,
            line,
            (w + 20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 40

    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
    if ok:
        filepath.write_bytes(buf.tobytes())
        logger.info("Saved evidence to %s", filepath)
        return f"/evidence/{filename}"
    
    return None
