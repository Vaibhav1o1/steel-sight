from __future__ import annotations

from fastapi import APIRouter, HTTPException

from billetvision.api.deps import StateDep
from billetvision.api.routes.status import get_status
from billetvision.runtime.sources import SyntheticSource, WebcamSource
from billetvision.schemas import SourceRequest, StationStatus, TriggerModeRequest

router = APIRouter()


@router.post("/control/pause", response_model=StationStatus, tags=["Control"])
def pause(state: StateDep) -> StationStatus:
    with state.lock:
        state.paused = True
    return get_status(state)


@router.post("/control/resume", response_model=StationStatus, tags=["Control"])
def resume(state: StateDep) -> StationStatus:
    with state.lock:
        state.paused = False
    return get_status(state)


@router.post("/control/trigger-mode", response_model=StationStatus, tags=["Control"])
def set_trigger_mode(req: TriggerModeRequest, state: StateDep) -> StationStatus:
    with state.lock:
        state.trigger_mode = req.mode
    return get_status(state)


@router.post("/source", response_model=StationStatus, tags=["Control"])
def set_source(req: SourceRequest, state: StateDep) -> StationStatus:
    if req.type == "synthetic":
        new_source = SyntheticSource("station", fps=30)
    elif req.type == "webcam":
        device = int(req.device_id) if req.device_id is not None else 0
        new_source = WebcamSource(device)
    else:
        raise HTTPException(status_code=422, detail="Invalid source type")

    if not new_source.open():
        raise HTTPException(
            status_code=503,
            detail={"code": "CAMERA_UNAVAILABLE", "message": "Could not open source"}
        )

    with state.lock:
        old_source = state.source
        state.source = new_source
    
    if old_source:
        old_source.close()

    return get_status(state)
