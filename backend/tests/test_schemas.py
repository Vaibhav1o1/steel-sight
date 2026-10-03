from __future__ import annotations

from collections import deque

import numpy as np
import pytest
from pydantic import ValidationError

from billetvision.enums import (
    DefectType,
    IdSource,
    InspectionStatus,
    SourceType,
)
from billetvision.schemas import (
    Inspection,
    Override,
    Roi,
    Spec,
    SpecUpsert,
    VerifyRequest,
)
from billetvision.vision.types import (
    Calibration,
    Decision,
    DefectResult,
    Detection,
    FinalizeJob,
    IdResult,
    Measurement,
    Track,
)


def _sample_spec() -> Spec:
    return Spec(
        id="spec_test",
        name="Test Spec",
        nominal_length_mm=120.0,
        nominal_width_mm=40.0,
        nominal_height_mm=None,
        tol_length_mm=2.0,
        tol_width_mm=1.0,
        cs_var_warn_pct=1.5,
        cs_var_fail_pct=3.0,
        notch_min_mm=1.0,
        camber_max_mm=1.5,
        taper_max_mm=1.0,
        id_template="H##-####",
        min_area_factor=0.4,
        max_area_factor=1.6,
        active=True,
    )


def test_inspection_roundtrip_json() -> None:
    override = Override(
        billet_id=None,
        status=None,
        note="Manual pass verify",
        at=1700000005.0,
    )
    inspection = Inspection(
        id=1,
        ts="2026-10-03T02:00:00.000Z",
        billet_id="H24-1187",
        id_source=IdSource.ocr,
        ocr_text="H24-1187",
        ocr_confidence=0.98,
        ocr_agreement=1.0,
        qr_text="H24-1187",
        id_mismatch=False,
        length_mm=120.4,
        width_mm=40.1,
        height_mm=None,
        length_dev_mm=0.4,
        width_dev_mm=0.1,
        cs_var_pct=0.45,
        taper_mm=0.12,
        camber_mm=0.22,
        min_width_mm=39.9,
        max_width_mm=40.3,
        width_profile_mm=[40.1] * 21,
        defects=[DefectType.notch],
        status=InspectionStatus.Pass,
        auto_status=InspectionStatus.Pass,
        reasons=[],
        spec_id="spec_test",
        n_samples=7,
        angle_deg=1.2,
        latency_ms=42.5,
        snapshot_url="/inspections/1/snapshot.jpg",
        source=SourceType.synthetic,
        track_id=101,
        override=override,
        created_at=1700000000.0,
    )

    json_str = inspection.model_dump_json()
    reloaded = Inspection.model_validate_json(json_str)

    assert reloaded.id == inspection.id
    assert reloaded.ts == inspection.ts
    assert reloaded.billet_id == inspection.billet_id
    assert reloaded.id_source == IdSource.ocr.value
    assert reloaded.ocr_text == "H24-1187"
    assert reloaded.width_profile_mm == [40.1] * 21
    assert reloaded.defects == [DefectType.notch.value]
    assert reloaded.status == InspectionStatus.Pass.value
    assert reloaded.override is not None
    assert reloaded.override.note == "Manual pass verify"
    assert reloaded.created_at == 1700000000.0


def test_extra_fields_rejected() -> None:
    valid_spec_data = _sample_spec().model_dump()
    valid_spec_data["unexpected_extra_field"] = "malicious"

    with pytest.raises(ValidationError) as exc_info:
        Spec.model_validate(valid_spec_data)
    assert "extra" in str(exc_info.value).lower()

    with pytest.raises(ValidationError):
        Roi.model_validate({"x0_mm": 0, "y0_mm": 0, "w_mm": 100, "h_mm": 100, "extra": 1})

    with pytest.raises(ValidationError):
        VerifyRequest.model_validate({"known_length_mm": 100.0, "unknown_field": True})


@pytest.mark.parametrize(
    "field_name",
    [
        "nominal_length_mm",
        "nominal_width_mm",
        "tol_length_mm",
        "tol_width_mm",
        "cs_var_warn_pct",
        "cs_var_fail_pct",
        "notch_min_mm",
        "camber_max_mm",
        "taper_max_mm",
    ],
)
def test_spec_validation_rejects_non_positive_values(field_name: str) -> None:
    data = _sample_spec().model_dump()

    # Test 0
    data[field_name] = 0.0
    with pytest.raises(ValidationError):
        Spec.model_validate(data)

    # Test negative
    data[field_name] = -2.5
    with pytest.raises(ValidationError):
        Spec.model_validate(data)

    # Same for SpecUpsert
    upsert_data = dict(data)
    upsert_data.pop("active", None)
    with pytest.raises(ValidationError):
        SpecUpsert.model_validate(upsert_data)


def test_id_template_length_validation() -> None:
    data = _sample_spec().model_dump()

    # Empty string
    data["id_template"] = ""
    with pytest.raises(ValidationError):
        Spec.model_validate(data)

    # Exceeds 20 chars
    data["id_template"] = "A" * 21
    with pytest.raises(ValidationError):
        Spec.model_validate(data)


def test_roi_and_verify_request_validation() -> None:
    with pytest.raises(ValidationError):
        Roi(x0_mm=0.0, y0_mm=0.0, w_mm=0.0, h_mm=50.0)

    with pytest.raises(ValidationError):
        Roi(x0_mm=0.0, y0_mm=0.0, w_mm=50.0, h_mm=-10.0)

    with pytest.raises(ValidationError):
        VerifyRequest(known_length_mm=0.0)

    with pytest.raises(ValidationError):
        VerifyRequest(known_length_mm=100.0, known_width_mm=0.0)


def test_vision_types_dataclasses() -> None:
    roi = Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0)
    spec = _sample_spec()

    calib = Calibration(
        h_img_to_bed=np.eye(3),
        roi=roi,
        rect_px_per_mm=3.0,
        image_px_per_mm=2.8,
        camera_matrix=None,
        dist_coeffs=None,
        marker_corners_px=np.zeros((4, 2)),
        marker_mm=80.0,
        image_size=(1920, 1080),
        reprojection_error_px=0.15,
        created_at=1700000000.0,
    )
    assert calib.marker_mm == 80.0

    det = Detection(
        contour_px=np.zeros((10, 2)),
        center_mm=(100.0, 50.0),
        angle_deg=5.0,
        rough_length_mm=120.0,
        rough_width_mm=40.0,
        area_mm2=4800.0,
        full_inside=True,
        merged=False,
    )
    assert det.full_inside is True

    meas = Measurement(
        length_mm=120.2,
        width_mm=40.1,
        width_profile_mm=tuple([40.1] * 21),
        valid_slices=21,
        dense_pos_mm=np.linspace(0, 120, 100),
        dense_top_mm=np.full(100, 20.0),
        dense_bottom_mm=np.full(100, -20.0),
        sharpness=120.5,
        angle_deg=5.0,
    )
    assert len(meas.width_profile_mm) == 21

    defects = DefectResult(
        cs_var_pct=0.8,
        taper_mm=0.2,
        camber_mm=0.3,
        min_width_mm=39.8,
        max_width_mm=40.4,
        defects=("notch",),
        notch_depth_mm=1.5,
    )
    assert defects.defects == ("notch",)

    track = Track(
        id=1,
        center_mm=(100.0, 50.0),
        history=deque([(1.0, (100.0, 50.0))]),
        missing=0,
        samples=[meas],
        crops=[(120.5, np.zeros((40, 120, 3), dtype=np.uint8))],
        first_sample_t=1.0,
        crossed_line=False,
        finalized=False,
    )
    assert track.id == 1

    finalize_job = FinalizeJob(
        track_id=1,
        samples=(meas,),
        crops=(np.zeros((40, 120, 3), dtype=np.uint8),),
        snapshot_jpeg=b"fake_jpeg",
        first_sample_t=1.0,
        source="synthetic",
        spec=spec,
    )
    assert finalize_job.source == "synthetic"

    id_result = IdResult(
        billet_id="H24-1187",
        id_source="ocr",
        ocr_text="H24-1187",
        ocr_confidence=0.99,
        ocr_agreement=1.0,
        qr_text="H24-1187",
        id_mismatch=False,
    )
    assert id_result.billet_id == "H24-1187"
    decision = Decision(status="Pass", reasons=())
    assert decision.status == "Pass"


def test_export_columns_order_and_width_variation_pct_alias() -> None:
    from billetvision.schemas import EXPORT_COLUMNS

    expected_columns = (
        "record_id",
        "timestamp",
        "track_id",
        "billet_id",
        "id_source",
        "id_confidence",
        "length_mm",
        "width_mm",
        "width_variation_pct",
        "camber_mm",
        "notch_depth_mm",
        "taper_mm",
        "status",
        "reason_codes",
        "flags",
        "calib_version",
        "frames_used",
        "evidence_image",
    )
    assert EXPORT_COLUMNS == expected_columns

    # Verify both width_variation_pct and cs_var_pct are accepted and map to canonical name
    base_dict = {
        "id": 1,
        "ts": "2026-10-04T14:32:10.482+05:30",
        "billet_id": "H24-1187",
        "id_source": "ocr",
        "ocr_text": "H24-1187",
        "ocr_confidence": 0.8,
        "ocr_agreement": 1.0,
        "qr_text": "H24-1187",
        "id_mismatch": False,
        "length_mm": 599.4,
        "width_mm": 100.3,
        "height_mm": None,
        "length_dev_mm": -0.6,
        "width_dev_mm": 0.3,
        "taper_mm": 0.4,
        "camber_mm": 0.9,
        "min_width_mm": 99.5,
        "max_width_mm": 100.7,
        "width_profile_mm": [100.3] * 21,
        "defects": [],
        "status": "Pass",
        "auto_status": "Pass",
        "reasons": [],
        "spec_id": "FLAT-500x100",
        "n_samples": 7,
        "angle_deg": 0.0,
        "latency_ms": 12.0,
        "snapshot_url": "evidence/1.jpg",
        "source": "synthetic",
        "track_id": 41,
        "override": None,
        "created_at": 1700000000.0,
    }

    # Case 1: with width_variation_pct
    d1 = dict(base_dict, width_variation_pct=1.2)
    insp1 = Inspection.model_validate(d1)
    assert insp1.width_variation_pct == 1.2
    assert insp1.cs_var_pct == 1.2
    assert "width_variation_pct" in insp1.model_dump()

    # Case 2: with legacy alias cs_var_pct
    d2 = dict(base_dict, cs_var_pct=1.5)
    insp2 = Inspection.model_validate(d2)
    assert insp2.width_variation_pct == 1.5
    assert insp2.cs_var_pct == 1.5
    assert "width_variation_pct" in insp2.model_dump()
