from __future__ import annotations

import cv2
from fastapi import APIRouter, HTTPException

from billetvision.api.deps import StateDep
from billetvision.schemas import (
    CalibrationState,
    MarkerResult,
    Roi,
    VerifyRequest,
    VerifyResult,
)
from billetvision.vision.calibration import (
    calibrate_from_marker,
    detect_marker,
)
from billetvision.vision.rectify import build_rectifier
from billetvision.vision.segment import segment

router = APIRouter(tags=["Calibration"])


@router.get("/calibration", response_model=CalibrationState)
def get_calibration(state: StateDep) -> CalibrationState:
    return state.calibration_state()


@router.post("/calibration/marker", response_model=MarkerResult)
def calibrate_marker(state: StateDep) -> MarkerResult:
    snap = state.pipeline_snapshot()
    if snap.latest_frame is None:
        raise HTTPException(status_code=503, detail="No frame available")
    
    frame = snap.latest_frame.frame
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    marker_res = detect_marker(gray)
    if marker_res is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "MARKER_NOT_FOUND", "message": "ArUco marker not found"}
        )
    
    corners, refine_shift = marker_res
    cal = calibrate_from_marker(gray.shape, corners, marker_size_mm=30.0)
    
    # Default ROI
    h, w = cal.rect_shape
    roi = Roi(x=0, y=0, w=w, h=h)
    
    with state.lock:
        state._rectifier = build_rectifier(cal, roi)
        state._background_rect_gray = None # invalidate background
    
    return MarkerResult(
        calibration=cal,
        roi=roi,
        refine_shift_px=refine_shift,
    )


@router.post("/calibration/background", response_model=CalibrationState)
def capture_background(state: StateDep) -> CalibrationState:
    snap = state.pipeline_snapshot()
    if snap.latest_frame is None:
        raise HTTPException(status_code=503, detail="No frame available")
    if snap.rectifier is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "NOT_CALIBRATED", "message": "Run marker calibration first"}
        )
    
    frame = snap.latest_frame.frame
    rect_bgr = snap.rectifier.apply(frame)
    rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
    
    with state.lock:
        state._background_rect_gray = rect_gray
    
    return get_calibration(state)


@router.post("/calibration/verify", response_model=VerifyResult)
def verify_calibration(req: VerifyRequest, state: StateDep) -> VerifyResult:
    snap = state.pipeline_snapshot()
    if snap.latest_frame is None:
        raise HTTPException(status_code=503, detail="No frame available")
    if snap.rectifier is None or snap.background is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "NOT_CALIBRATED", "message": "Missing calibration or background"}
        )
    
    frame = snap.latest_frame.frame
    rect_bgr = snap.rectifier.apply(frame)
    rect_gray = cv2.cvtColor(rect_bgr, cv2.COLOR_BGR2GRAY)
    
    dets = segment(
        rect_gray,
        background=snap.background,
        spec=snap.spec,
        roi=snap.rectifier.roi,
        rect_px_per_mm=snap.rectifier.cal.rect_px_per_mm,
    )
    
    if not dets:
        raise HTTPException(
            status_code=422,
            detail={"code": "NO_OBJECT", "message": "No object detected in ROI"}
        )
    
    det = max(dets, key=lambda d: d.area_px)
    l_mm = det.length_px / snap.rectifier.cal.rect_px_per_mm
    w_mm = det.width_px / snap.rectifier.cal.rect_px_per_mm
    
    return VerifyResult(
        length_mm=l_mm,
        width_mm=w_mm,
        expected_length_mm=req.expected_length_mm,
        expected_width_mm=req.expected_width_mm,
    )


@router.put("/calibration/roi", response_model=CalibrationState)
def set_roi(roi: Roi, state: StateDep) -> CalibrationState:
    with state.lock:
        if state._rectifier is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "NOT_CALIBRATED", "message": "Run marker calibration first"}
            )
        # Update rectifier with new ROI
        state._rectifier = build_rectifier(state._rectifier.cal, roi)
    return get_calibration(state)


@router.delete("/calibration", response_model=CalibrationState)
def reset_calibration(state: StateDep) -> CalibrationState:
    with state.lock:
        state._rectifier = None
        state._background_rect_gray = None
    return get_calibration(state)
