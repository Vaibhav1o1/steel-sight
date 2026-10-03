from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from billetvision import config
from billetvision.api.deps import EngineDep
from billetvision.db import get_inspections

router = APIRouter(tags=["Export"])


@router.get("/export/csv")
def export_csv():
    path = Path(config.LOG_DIR) / "inspections.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="CSV not found")
    return FileResponse(path, media_type="text/csv", filename="inspections.csv")


@router.get("/export/xlsx")
def export_xlsx():
    path = Path(config.LOG_DIR) / "inspections.xlsx"
    if not path.exists():
        raise HTTPException(status_code=503, detail="XLSX not generated yet")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="inspections.xlsx"
    )


@router.get("/export/json")
def export_json(engine: EngineDep):
    items, _ = get_inspections(engine, limit=50000)
    data = [item.model_dump(mode="json") for item in items]
    
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="inspections.json"'}
    )
