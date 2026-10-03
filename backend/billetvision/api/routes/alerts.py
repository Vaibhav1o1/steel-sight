from __future__ import annotations

from fastapi import APIRouter, HTTPException

from billetvision.api.deps import EngineDep
from billetvision.db import ack_alert as db_ack_alert
from billetvision.db import get_alerts as db_get_alerts
from billetvision.schemas import Alert

router = APIRouter(tags=["Alerts"])


@router.get("/alerts", response_model=list[Alert])
def get_alerts(engine: EngineDep, limit: int = 50):
    return db_get_alerts(engine, limit=limit)


@router.post("/alerts/{id}/ack", response_model=Alert)
def ack_alert(id: int, engine: EngineDep):
    try:
        return db_ack_alert(id, engine)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
