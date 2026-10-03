from __future__ import annotations

from fastapi import APIRouter

from billetvision.api.deps import StateDep
from billetvision.schemas import StationStatus

router = APIRouter(tags=["Status"])

@router.get("/status", response_model=StationStatus)
def get_status(state: StateDep) -> StationStatus:
    snap = state.status_snapshot()
    
    with state.lock:
        source_info = state.source_info
        has_bg = state._background_rect_gray is not None
        paused = state.paused
        trigger_mode = state.trigger_mode
        active_spec = state._active_spec
        fps_c = state.fps_capture
        fps_p = state.fps_process
    
    return StationStatus(
        source=source_info,
        camera_ok=snap.camera_ok,
        calibrated=snap.calibrated,
        has_background=has_bg,
        paused=paused,
        trigger_mode=trigger_mode,
        active_spec=active_spec,
        fps_capture=fps_c,
        fps_process=fps_p,
        log_status=snap.log_status,
        ocr_ready=True,
    )
