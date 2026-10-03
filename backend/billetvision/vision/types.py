from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from billetvision.schemas import Roi, Spec
else:
    from billetvision.schemas import Roi, Spec


@dataclass(frozen=True, eq=False)
class Calibration:
    h_img_to_bed: np.ndarray  # 3×3, image px (undistorted) → bed mm
    roi: Roi  # pydantic Roi reused
    rect_px_per_mm: float
    image_px_per_mm: float
    camera_matrix: np.ndarray | None
    dist_coeffs: np.ndarray | None
    marker_corners_px: np.ndarray  # 4×2
    marker_mm: float
    image_size: tuple[int, int]  # (w, h)
    reprojection_error_px: float
    created_at: float
    calib_version: str = "cal-001"
    marker_plane_height_mm: float = 50.0
    marker_side_measured_mm: float | None = None
    baseline: str = "reduced-baseline"
    residual_mm: float = 0.0
    per_marker_residuals_mm: dict[int, float] | None = None
    warning: str | None = None


@dataclass(frozen=True, eq=False)
class Detection:
    contour_px: np.ndarray  # rectified-image px, N×2
    center_mm: tuple[float, float]  # bed mm
    angle_deg: float  # long axis vs +x, in (−90, 90]
    rough_length_mm: float
    rough_width_mm: float
    area_mm2: float
    full_inside: bool  # ≥ EDGE_MARGIN_MM from every ROI border
    merged: bool  # area > max_area_factor × nominal area


@dataclass(frozen=True, eq=False)
class Measurement:
    length_mm: float
    width_mm: float
    width_profile_mm: tuple[float, ...]  # 21 sub-pixel slice widths, NaN-free
    valid_slices: int
    dense_pos_mm: np.ndarray  # positions along the long axis (mask-based dense profile)
    dense_top_mm: np.ndarray  # signed edge offsets from the long axis at each position
    dense_bottom_mm: np.ndarray
    sharpness: float  # variance of Laplacian on the billet crop
    angle_deg: float


@dataclass(frozen=True, eq=False)
class DefectResult:
    width_variation_pct: float
    taper_mm: float
    camber_mm: float
    min_width_mm: float
    max_width_mm: float
    defects: tuple[str, ...]  # DefectType values
    notch_depth_mm: float

    def __init__(
        self,
        width_variation_pct: float | None = None,
        taper_mm: float = 0.0,
        camber_mm: float = 0.0,
        min_width_mm: float = 0.0,
        max_width_mm: float = 0.0,
        defects: tuple[str, ...] = (),
        notch_depth_mm: float = 0.0,
        cs_var_pct: float | None = None,
    ) -> None:
        val = (
            width_variation_pct
            if width_variation_pct is not None
            else (cs_var_pct if cs_var_pct is not None else 0.0)
        )
        object.__setattr__(self, "width_variation_pct", float(val))
        object.__setattr__(self, "taper_mm", float(taper_mm))
        object.__setattr__(self, "camber_mm", float(camber_mm))
        object.__setattr__(self, "min_width_mm", float(min_width_mm))
        object.__setattr__(self, "max_width_mm", float(max_width_mm))
        object.__setattr__(self, "defects", tuple(defects))
        object.__setattr__(self, "notch_depth_mm", float(notch_depth_mm))

    @property
    def cs_var_pct(self) -> float:
        return self.width_variation_pct


@dataclass
class Track:  # mutable, owned by the processing thread
    id: int
    center_mm: tuple[float, float]
    history: deque[tuple[float, tuple[float, float]]]  # (t_monotonic, center)
    missing: int
    samples: list[Measurement]
    crops: list[tuple[float, np.ndarray]]  # (sharpness, upright BGR crop)
    first_sample_t: float | None
    crossed_line: bool
    finalized: bool


@dataclass(frozen=True, eq=False)
class FinalizeJob:
    track_id: int
    samples: tuple[Measurement, ...]
    crops: tuple[np.ndarray, ...]  # ≤ 3 sharpest upright crops (BGR)
    snapshot_jpeg: bytes  # annotated full frame at finalize time
    first_sample_t: float  # time.monotonic()
    source: str
    spec: Spec


@dataclass(frozen=True)
class IdResult:
    billet_id: str | None
    id_source: str  # IdSource
    ocr_text: str | None
    ocr_confidence: float | None
    ocr_agreement: float | None
    qr_text: str | None
    id_mismatch: bool


@dataclass(frozen=True)
class Decision:
    status: str  # InspectionStatus
    reasons: tuple[str, ...]
    flags: tuple[str, ...] = ()
