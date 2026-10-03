from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from billetvision import config
from billetvision.api.deps import StateDep

router = APIRouter(tags=["Stream"])


async def mjpeg_generator(state: StateDep, view: str) -> AsyncGenerator[bytes, None]:
    """Yield MJPEG frames from the requested stream view."""
    fps = config.STREAM_FPS
    sleep_t = 1.0 / fps
    boundary = b"frame"
    
    while True:
        state.request_view(view)
        frame_bytes = state.get_jpeg(view)
        
        if frame_bytes:
            yield (
                b"--" + boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n"
                + frame_bytes + b"\r\n"
            )
        else:
            # Send a 1x1 empty jpeg or just wait
            # We just wait if no frame is ready yet.
            pass
            
        await asyncio.sleep(sleep_t)


@router.get("/stream.mjpg")
async def get_stream(state: StateDep, view: str = Query("annotated")) -> StreamingResponse:
    """Stream MJPEG video."""
    return StreamingResponse(
        mjpeg_generator(state, view),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/snapshot.jpg")
def get_snapshot(state: StateDep, view: str = Query("annotated")) -> Response:
    """Return latest snapshot frame as JPEG."""
    state.request_view(view)
    frame_bytes = state.get_jpeg(view)
    if not frame_bytes:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CAMERA_UNAVAILABLE",
                "message": "Camera frame not available",
                "hint": "Ensure camera is connected and streaming",
            },
        )
    return Response(content=frame_bytes, media_type="image/jpeg")

