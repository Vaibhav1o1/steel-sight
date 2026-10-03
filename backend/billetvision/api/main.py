from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from billetvision.api.routes import (
    alerts,
    calibration,
    control,
    export,
    inspections,
    metrics,
    specs,
    status,
    stream,
    ws,
)


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="BilletVision API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(status.router)
    app.include_router(stream.router)
    app.include_router(control.router)
    app.include_router(calibration.router)
    app.include_router(specs.router)
    app.include_router(inspections.router)
    app.include_router(export.router)
    app.include_router(ws.router)
    app.include_router(alerts.router)
    app.include_router(metrics.router)

    # Health check
    @app.get("/health", tags=["Health"])
    def health():
        return {"status": "ok"}

    return app
