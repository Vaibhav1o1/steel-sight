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
    length_mm: float | None = None
    width_mm: float | None = None
    length_px: float | None = None
    width_px: float | None = None
    defects: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    annotated_url: str
    processing_time_ms: float
