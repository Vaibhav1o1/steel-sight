from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UploadCalibrationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calibrated: bool
    source: str = Field(description="'marker', 'station', or 'uncalibrated'")
    px_per_mm: float | None = None
    warning: str | None = None


class UploadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    status: str = Field(description="'Pass', 'Rework', 'Fail', or 'Review'")
    calibrated: bool
    calibration: UploadCalibrationInfo
    billet_id: str | None = None
    id_source: str = "none"
    ocr_confidence: float | None = None
    qr_detected: bool = False
    length_mm: float | None = None
    width_mm: float | None = None
    nominal_length_mm: float | None = None
    nominal_width_mm: float | None = None
    tol_length_mm: float | None = None
    tol_width_mm: float | None = None
    length_dev_mm: float | None = None
    length_abs_dev_mm: float | None = None
    length_passed: bool | None = None
    width_dev_mm: float | None = None
    width_abs_dev_mm: float | None = None
    width_passed: bool | None = None
    length_px: float | None = None
    width_px: float | None = None
    defects: list[str] = Field(default_factory=list)
    defect_type: str | None = None
    defect_size_mm: float | None = None
    reasons: list[str] = Field(default_factory=list)
    annotated_url: str
    processing_time_ms: float


class TestDatasetImageItem(BaseModel):
    filename: str
    variant: str
    expected_status: str
    billet_id: str | None = None
    length_mm: float
    width_mm: float
    defect: str | None = None
    defect_size_mm: float = 0.0
    qr: bool = False


class GroundTruthBillet(BaseModel):
    id_text: str | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    qr: bool | None = None
    defect: str | None = None
    defect_size_mm: float | None = None
    expected_status: str | None = None


class GroundTruthComparison(BaseModel):
    status_match: bool | None = None
    length_delta_mm: float | None = None
    width_delta_mm: float | None = None
    defect_type_match: bool | None = None
    defect_size_delta_mm: float | None = None
    id_match: bool | None = None
    qr_match: bool | None = None


class TestInspectResponse(BaseModel):
    system_result: UploadResult
    ground_truth: GroundTruthBillet | None = None
    comparison: GroundTruthComparison | None = None
    is_test_dataset: bool = True
