from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from billetvision.api.deps import BusDep, DbLoggerDep, JobQueueDep, StateDep

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    state: StateDep,
    bus: BusDep,
    db_logger: DbLoggerDep,
    job_queue: JobQueueDep,
):
    await websocket.accept()
    q = bus.subscribe()
    
    # We will spawn a background task to emit stats at 1Hz
    async def stats_emitter():
        while True:
            try:
                await asyncio.sleep(1.0)
                snap = state.status_snapshot()

                with state.lock:
                    fps_c = state.fps_capture
                    fps_p = state.fps_process
                    p95 = state.process_ms_p95
                    timings = state.stage_timings.copy()
                    tracks = state.active_tracks_count

                # Contract-shape stats (types.ts StatsMessage)
                stats_msg = {
                    "type": "stats",
                    "fps_capture": fps_c,
                    "fps_process": fps_p,
                    "process_ms_p95": p95,
                    "tracks": tracks,
                    "camera_ok": snap.camera_ok,
                    "calibrated": snap.calibrated,
                    "paused": snap.paused,
                    "log_status": snap.log_status,
                    "server_time": time.time(),
                    # Extra fields for health strip
                    "stage_timings": timings,
                    "queue_length": job_queue.qsize(),
                    "drift_mm": snap.drift_mm,
                }

                writer_msg = {
                    "type": "writer",
                    "last_write_time": db_logger.last_successful_write_time,
                    "pending_count": db_logger.pending_count,
                    "blocked": db_logger.blocked,
                }
                
                await websocket.send_json(stats_msg)
                await websocket.send_json(writer_msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Stats emitter error: %s", e)
                break

    emitter_task = asyncio.create_task(stats_emitter())
    
    try:
        while True:
            event = await q.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        emitter_task.cancel()
        bus.unsubscribe(q)
