from __future__ import annotations

import logging
import queue
import time

from billetvision.db import init_db
from billetvision.logging_io import InspectionLogger
from billetvision.runtime.events import EventBus
from billetvision.runtime.metrics import RuntimeMetrics
from billetvision.runtime.pipeline import ProcessingThread
from billetvision.runtime.sources import SyntheticSource
from billetvision.runtime.state import RuntimeState
from billetvision.runtime.worker import OcrWorkerThread

logging.basicConfig(level=logging.WARNING)


def main():
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    db_logger = InspectionLogger(db_engine=engine)
    
    source = SyntheticSource("station", fps=30)
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
    
    worker.start()
    pipeline.start()
    
    with state.lock:
        state.source.open()
        
    print("Running synthetic pipeline for 15 seconds...")
    start_t = time.monotonic()
    idx = 0
    while time.monotonic() - start_t < 15.0:
        res = state.source.read()
        if res:
            f, ts = res
            idx += 1
            state.update_frame(f, idx, ts)
            metrics.capture_fps.tick()
        time.sleep(1 / 30.0)
        
    pipeline.stop()
    worker.stop_event.set()
    worker.join()
    
    print("\n--- RESULTS (SYNTHETIC SOURCE) ---")
    print(f"Capture FPS: {metrics.capture_fps.fps():.1f}")
    print(f"Process FPS: {metrics.process_fps.fps():.1f}")
    print(f"Process p95 latency: {metrics.get_process_ms_p95():.1f} ms")
    print(f"Dropped jobs: {metrics.dropped_jobs}")
    print(f"Errors: {metrics.errors}")
    print("\nPer-Stage Timings (ms):")
    with state.lock:
        for k, v in state.stage_timings.items():
            print(f"  {k}: {v:.1f}")


if __name__ == "__main__":
    main()
