from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StatusSeriesBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket_id: str = Field(..., description="Bucket identifier or range key")
    label: str = Field(..., description="Human-readable bucket label")
    ts_start: str | None = Field(None, description="Start timestamp for time mode")
    ts_end: str | None = Field(None, description="End timestamp for time mode")

    pass_count: int = Field(0, description="Pass inspection count")
    rework_count: int = Field(0, description="Rework inspection count")
    fail_count: int = Field(0, description="Fail inspection count")
    review_count: int = Field(0, description="Review inspection count")
    total_count: int = Field(0, description="Total inspection count in bucket")

    evaluated_count: int = Field(
        0, description="Evaluated count (Pass+Rework+Fail, Review excluded)"
    )
    nonconforming_count: int = Field(
        0, description="Nonconforming count (Rework+Fail)"
    )
    p_rate: float | None = Field(
        None, description="Fraction nonconforming p (null if evaluated_count == 0)"
    )

    ucl: float | None = Field(None, description="Upper control limit")
    lcl: float | None = Field(None, description="Lower control limit")
    centerline: float | None = Field(None, description="Centerline p-bar")
    reliable: bool = Field(
        False, description="True if evaluated_count >= 20, False otherwise"
    )


class StatusSeriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["count", "time"] = Field(..., description="Bucketing mode")
    basis: Literal["final", "auto"] = Field(
        ..., description="Status basis (final vs auto)"
    )
    source_filter: Literal["all", "synthetic", "real"] = Field(
        ..., description="Source filter applied"
    )

    buckets: list[StatusSeriesBucket] = Field(
        ..., description="List of aggregated buckets"
    )

    total_inspections: int = Field(
        ..., description="Total inspections in result set"
    )
    total_evaluated: int = Field(
        ..., description="Total evaluated inspections (Review excluded)"
    )
    total_nonconforming: int = Field(
        ..., description="Total nonconforming inspections"
    )
    overall_p_bar: float | None = Field(
        None, description="Overall process average fraction nonconforming"
    )

    pass_count: int = Field(0, description="Overall Pass count")
    rework_count: int = Field(0, description="Overall Rework count")
    fail_count: int = Field(0, description="Overall Fail count")
    review_count: int = Field(0, description="Overall Review count")

    has_synthetic: bool = Field(
        False, description="True if any inspections in dataset are synthetic"
    )
