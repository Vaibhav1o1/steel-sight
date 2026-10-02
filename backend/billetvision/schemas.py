from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AlertLevel,
    DefectType,
    IdSource,
    InspectionStatus,
    LogFileStatus,
    SourceType,
    TriggerMode,
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ── Specs ───────────────────────────────────────────
class Spec(Contract):
    id: str
    name: str
    nominal_length_mm: float = Field(gt=0)
    nominal_width_mm: float = Field(gt=0)
    nominal_height_mm: float | None = None
    tol_length_mm: float = Field(gt=0)
    tol_width_mm: float = Field(gt=0)
    cs_var_warn_pct: float = Field(gt=0)
    cs_var_fail_pct: float = Field(gt=0)
    notch_min_mm: float = Field(gt=0)
    camber_max_mm: float = Field(gt=0)
    taper_max_mm: float = Field(gt=0)
    id_template: str = Field(min_length=1, max_length=20)
    min_area_factor: float = 0.4
    max_area_factor: float = 1.6
    active: bool = False


class SpecUpsert(Contract):
    id: str
    name: str
    nominal_length_mm: float = Field(gt=0)
    nominal_width_mm: float = Field(gt=0)
    nominal_height_mm: float | None = None
    tol_length_mm: float = Field(gt=0)
    tol_width_mm: float = Field(gt=0)
    cs_var_warn_pct: float = Field(gt=0)
    cs_var_fail_pct: float = Field(gt=0)
    notch_min_mm: float = Field(gt=0)
    camber_max_mm: float = Field(gt=0)
    taper_max_mm: float = Field(gt=0)
    id_template: str = Field(min_length=1, max_length=20)
    min_area_factor: float = 0.4
    max_area_factor: float = 1.6


# ── Inspections ─────────────────────────────────────
class Override(Contract):
    billet_id: str | None = None
    status: InspectionStatus | None = None
    note: str = Field(min_length=1, max_length=500)
    at: float


class Inspection(Contract):
    id: int
    ts: str
    billet_id: str | None
    id_source: IdSource
    ocr_text: str | None
    ocr_confidence: float | None
    ocr_agreement: float | None
    qr_text: str | None
    id_mismatch: bool
    length_mm: float
    width_mm: float
    height_mm: float | None
    length_dev_mm: float
    width_dev_mm: float
    cs_var_pct: float
    taper_mm: float
    camber_mm: float
    min_width_mm: float
    max_width_mm: float
    width_profile_mm: list[float]
    defects: list[DefectType]
    status: InspectionStatus
    auto_status: InspectionStatus
    reasons: list[str]
    spec_id: str
    n_samples: int
    angle_deg: float
    latency_ms: float
    snapshot_url: str
    source: SourceType
    track_id: int
    override: Override | None
    created_at: float


class InspectionPatch(Contract):
    billet_id: str | None = None
    status: InspectionStatus | None = None
    note: str = Field(min_length=1, max_length=500)


class InspectionList(Contract):
    items: list[Inspection]
    total: int


class Alert(Contract):
    id: int
    inspection_id: int | None
    ts: str
    level: AlertLevel
    message: str
    acknowledged: bool
    created_at: float


# ── Calibration ─────────────────────────────────────
class Roi(Contract):
    x0_mm: float
    y0_mm: float
    w_mm: float = Field(gt=0)
    h_mm: float = Field(gt=0)


class VerifyRequest(Contract):
    known_length_mm: float = Field(gt=0)
    known_width_mm: float | None = Field(default=None, gt=0)


class VerifyResult(Contract):
    known_length_mm: float
    measured_length_mm: float
    length_error_pct: float
    known_width_mm: float | None
    measured_width_mm: float | None
    width_error_pct: float | None
    ok: bool
    at: float


class CalibrationState(Contract):
    calibrated: bool
    has_background: bool
    has_intrinsics: bool
    marker_mm: float
    image_px_per_mm: float | None
    rect_px_per_mm: float
    roi: Roi
    reprojection_error_px: float | None
    verify: VerifyResult | None
    drift_mm: float | None
    drift_ok: bool
    created_at: float | None


class MarkerResult(Contract):
    found: bool
    marker_id: int
    corners_px: list[list[float]]
    image_px_per_mm: float
    reprojection_error_px: float
    calibration: CalibrationState


# ── Station control / status ────────────────────────
class SourceRequest(Contract):
    type: SourceType
    value: str = ""


class SourceInfo(Contract):
    type: SourceType
    value: str
    frame_width: int | None
    frame_height: int | None


class TriggerModeRequest(Contract):
    mode: TriggerMode


class StationStatus(Contract):
    source: SourceInfo
    camera_ok: bool
    calibrated: bool
    has_background: bool
    paused: bool
    trigger_mode: TriggerMode
    active_spec: Spec
    fps_capture: float
    fps_process: float
    log_status: LogFileStatus
    ocr_ready: bool


class Health(Contract):
    ok: bool
    db: bool
    camera_ok: bool
    calibrated: bool
    ocr_ready: bool


# ── Metrics & evaluation ────────────────────────────
class Metrics(Contract):
    fps_capture: float
    fps_process: float
    process_ms_p50: float
    process_ms_p95: float
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    inspections_total: int
    by_status: dict[str, int]
    throughput_per_min: float
    ocr_read_rate: float | None
    queue_depth: int
    dropped_jobs: int
    uptime_s: float


class PropAccuracy(Contract):
    prop_id: str
    gt_length_mm: float
    gt_width_mm: float
    n: int
    mean_length_mm: float
    mean_width_mm: float
    length_error_pct: float
    width_error_pct: float
    max_abs_error_pct: float
    ocr_correct_rate: float | None


class EvalReal(Contract):
    n_inspections: int
    n_props_seen: int
    length_mae_pct: float
    length_p95_pct: float
    width_mae_pct: float
    width_p95_pct: float
    within_1pct_rate: float
    ocr_accuracy: float | None
    ocr_n: int
    read_rate: float
    props: list[PropAccuracy]


class SyntheticVariant(Contract):
    n: int
    length_mae_pct: float
    length_max_pct: float
    width_mae_pct: float
    width_max_pct: float
    ocr_accuracy: float | None


class SyntheticBench(Contract):
    n: int
    generated_at: float
    overall: SyntheticVariant
    variants: dict[str, SyntheticVariant]
    defect_accuracy: float
    mean_process_ms: float


class EvalResponse(Contract):
    real: EvalReal | None
    synthetic: SyntheticBench | None


class ApiErrorBody(Contract):
    code: Literal[
        "NOT_FOUND",
        "BAD_REQUEST",
        "MARKER_NOT_FOUND",
        "NO_OBJECT",
        "NOT_CALIBRATED",
        "CAMERA_UNAVAILABLE",
        "INTERNAL",
    ]
    message: str
    hint: str | None = None
