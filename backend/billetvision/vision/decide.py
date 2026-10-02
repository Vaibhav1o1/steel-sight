from __future__ import annotations

from billetvision.schemas import Spec
from billetvision.vision.types import Decision, DefectResult, IdResult, Measurement


def decide(
    measurement: Measurement,
    defects: DefectResult,
    spec: Spec,
    id_result: IdResult | None = None,
    billet_id: str | None = None,
    id_mismatch: bool = False,
    ocr_text: str | None = None,
    qr_text: str | None = None,
) -> Decision:
    """Evaluate inspection rules and produce a PASS / REWORK / REJECT decision with reason strings."""
    if id_result is not None:
        eff_id = id_result.billet_id
        eff_mismatch = id_result.id_mismatch
        eff_ocr = id_result.ocr_text
        eff_qr = id_result.qr_text
    else:
        eff_id = billet_id
        eff_mismatch = id_mismatch
        eff_ocr = ocr_text
        eff_qr = qr_text

    reasons: list[str] = []
    has_fail = False
    has_rework = False

    # 1. Length checks
    min_l = spec.nominal_length_mm - spec.tol_length_mm
    max_l = spec.nominal_length_mm + spec.tol_length_mm
    length = measurement.length_mm

    if length < min_l:
        d = min_l - length
        reasons.append(f"Length {length:.1f} mm is {d:.1f} mm below minimum {min_l:.1f} mm")
        has_fail = True
    elif length > max_l:
        d = length - max_l
        reasons.append(f"Length {length:.1f} mm is {d:.1f} mm over maximum {max_l:.1f} mm (trim)")
        has_rework = True

    # 2. Width checks
    min_w = spec.nominal_width_mm - spec.tol_width_mm
    max_w = spec.nominal_width_mm + spec.tol_width_mm
    width = measurement.width_mm

    if width < min_w:
        d = min_w - width
        reasons.append(f"Width {width:.1f} mm is {d:.1f} mm below minimum {min_w:.1f} mm")
        has_fail = True
    elif width > max_w:
        d = width - max_w
        reasons.append(f"Width {width:.1f} mm is {d:.1f} mm over maximum {max_w:.1f} mm")
        has_rework = True

    # 3. Defect checks
    if "notch" in defects.defects:
        reasons.append(f"Notch {defects.notch_depth_mm:.1f} mm deep detected")
        has_fail = True

    if defects.cs_var_pct >= spec.cs_var_fail_pct:
        reasons.append(f"Cross-section variation {defects.cs_var_pct:.1f}% ≥ {spec.cs_var_fail_pct:.1f}%")
        has_fail = True
    elif defects.cs_var_pct >= spec.cs_var_warn_pct:
        reasons.append(f"Cross-section variation {defects.cs_var_pct:.1f}% ≥ {spec.cs_var_warn_pct:.1f}%")
        has_rework = True

    if "taper" in defects.defects:
        reasons.append(f"Taper {defects.taper_mm:.1f} mm")
        has_rework = True

    if "bulge" in defects.defects:
        reasons.append("Bulge detected")
        has_rework = True

    if "camber" in defects.defects:
        reasons.append(f"Camber {defects.camber_mm:.1f} mm")
        has_rework = True

    # 4. ID checks
    if eff_id is None:
        reasons.append("ID unreadable — tag manually")
        has_rework = True

    if eff_mismatch:
        reasons.append(f"OCR '{eff_ocr or ''}' does not match QR '{eff_qr or ''}'")
        has_rework = True

    # 5. Determine status
    if has_fail:
        status = "Fail"
    elif has_rework:
        status = "Rework"
    else:
        status = "Pass"
        reasons = ["Within spec"]

    return Decision(status=status, reasons=tuple(reasons))
