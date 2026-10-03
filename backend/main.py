from __future__ import annotations

import logging
import queue
from contextlib import asynccontextmanager

from fastapi import FastAPI

from billetvision.api.main import create_app
from billetvision.db import init_db
from billetvision.logging_io import InspectionLogger
from billetvision.runtime.events import EventBus
from billetvision.runtime.metrics import RuntimeMetrics
from billetvision.runtime.pipeline import ProcessingThread
from billetvision.runtime.sources import WebcamSource
from billetvision.runtime.state import RuntimeState
from billetvision.runtime.worker import OcrWorkerThread

logger = logging.getLogger("billetvision.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    logger.info("Initializing BilletVision backend...")
    
    from sqlalchemy import create_engine

    # In production this might be a configurable URL
    from billetvision import config
    
    engine = create_engine(f"sqlite:///{config.LOG_DIR}/billetvision.db")
    init_db(engine)
    
    db_logger = InspectionLogger(db_engine=engine)
    
    from billetvision.runtime.sources import make_source
    source = make_source(config.SOURCE_TYPE, config.SOURCE_VALUE)
    state = RuntimeState(initial_source=source)
    
    from billetvision.db import DEFAULT_SPEC_DICT
    from billetvision.schemas import Spec
    state.active_spec = Spec(**DEFAULT_SPEC_DICT)
    
    bus = EventBus()
    metrics = RuntimeMetrics()
    job_queue = queue.Queue(maxsize=16)
    system_alerts = queue.Queue(maxsize=32)
    
    worker = OcrWorkerThread(job_queue, system_alerts, bus, state, db_logger)
    pipeline = ProcessingThread(state, job_queue, system_alerts, metrics, bus)
    
    from billetvision.runtime.state import CaptureThread
    capture = CaptureThread(state)
    
    app.state.runtime_state = state
    app.state.event_bus = bus
    app.state.db_engine = engine
    app.state.db_logger = db_logger
    app.state.job_queue = job_queue
    app.state.system_alerts = system_alerts
    app.state.metrics = metrics
    app.state.worker = worker
    app.state.pipeline = pipeline
    app.state.capture = capture
    
    worker.start()
    pipeline.start()
    capture.start()
    
    with state.lock:
        state.source.open()
        
    yield
    
    # Teardown
    logger.info("Shutting down BilletVision backend...")
    capture.stop()
    pipeline.stop()
    worker.stop_event.set()
    worker.join()
    with state.lock:
        if state.source:
            state.source.close()


from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

app = create_app(lifespan=lifespan)

web_out = Path(__file__).parent.parent / "web" / "out"
if web_out.is_dir():
    app.mount("/", StaticFiles(directory=str(web_out), html=True), name="static")
