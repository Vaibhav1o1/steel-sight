from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from billetvision.api.deps import StateDep
from billetvision.api.routes.status import get_status
from billetvision.db import DEFAULT_SPEC_DICT
from billetvision.schemas import Spec, StationStatus

router = APIRouter(tags=["Specs"])


class SpecActivationRequest(BaseModel):
    id: str


@router.get("/specs", response_model=list[Spec])
def list_specs() -> list[Spec]:
    # Hardcoded for now per requirements, or maybe loaded from config
    return [Spec(**DEFAULT_SPEC_DICT)]


@router.put("/specs/active", response_model=StationStatus)
def set_active_spec(req: SpecActivationRequest, state: StateDep) -> StationStatus:
    # We only have one spec currently
    if req.id != DEFAULT_SPEC_DICT["id"]:
        raise HTTPException(status_code=404, detail="Spec not found")
        
    with state.lock:
        state._active_spec = Spec(**DEFAULT_SPEC_DICT)
        
    return get_status(state)
