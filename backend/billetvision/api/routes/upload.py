from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from billetvision.api.deps import StateDep
from billetvision.schemas_upload import (
    TestDatasetImageItem,
    TestInspectResponse,
    UploadResult,
)
from billetvision.vision.upload_inspect import (
    get_cached_image,
    inspect_test_dataset_image,
    list_test_dataset_images,
    process_upload_image,
)

router = APIRouter(tags=["Upload"])

# Semaphore to limit concurrent upload processing to 2
_upload_semaphore = asyncio.Semaphore(2)


@router.post("/inspect/image", response_model=UploadResult)
async def inspect_uploaded_image(
    state: StateDep,
    file: Annotated[UploadFile, File()],
    station_camera: Annotated[bool, Query()] = False,
) -> UploadResult:
    """Inspect an arbitrary uploaded image without storing to DB."""
    # Enforce 15 MB limit while streaming/reading chunks
    chunk_size = 1024 * 64
    total_bytes = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes.extend(chunk)
        if len(total_bytes) > 15 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "Image size exceeds 15 MB limit",
                },
            )
    data = bytes(total_bytes)

    async with _upload_semaphore:
        try:
            # Snapshot state calibration and active spec safely
            station_calib = state.calibration_state()
            active_spec = state.active_spec

            result = await run_in_threadpool(
                process_upload_image,
                data=data,
                station_camera=station_camera,
                station_calibration=station_calib,
                spec=active_spec,
            )
            return result
        except ValueError as e:
            err_msg = str(e)
            if err_msg.startswith("PAYLOAD_TOO_LARGE:"):
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": err_msg.replace("PAYLOAD_TOO_LARGE: ", ""),
                    },
                ) from e
            elif err_msg.startswith("UNSUPPORTED_MEDIA_TYPE:"):
                raise HTTPException(
                    status_code=415,
                    detail={
                        "code": "UNSUPPORTED_MEDIA_TYPE",
                        "message": err_msg.replace("UNSUPPORTED_MEDIA_TYPE: ", ""),
                    },
                ) from e
            elif err_msg.startswith("UNPROCESSABLE_ENTITY:"):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "UNPROCESSABLE_ENTITY",
                        "message": err_msg.replace("UNPROCESSABLE_ENTITY: ", ""),
                    },
                ) from e
            else:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "VALIDATION_ERROR", "message": err_msg},
                ) from e


@router.get("/inspect/image/{image_id}.jpg")
async def get_uploaded_annotated_image(image_id: str) -> Response:
    """Serve the annotated JPEG of an uploaded image."""
    try:
        uuid.UUID(image_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Invalid image UUID"},
        ) from e

    jpeg_bytes = get_cached_image(image_id)
    if jpeg_bytes is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": "Annotated image not found or expired",
            },
        )

    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.get("/inspect/test-dataset", response_model=list[TestDatasetImageItem])
async def get_test_dataset() -> list[TestDatasetImageItem]:
    """List available test dataset images with metadata and ground truth."""
    return await run_in_threadpool(list_test_dataset_images)


@router.post("/inspect/test-dataset/{image_name}", response_model=TestInspectResponse)
async def inspect_test_image(image_name: str) -> TestInspectResponse:
    """Run upload inspection on a test dataset image and return comparison against ground truth."""
    async with _upload_semaphore:
        try:
            return await run_in_threadpool(inspect_test_dataset_image, image_name)
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": str(e)},
            ) from e
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "BAD_REQUEST", "message": str(e)},
            ) from e
