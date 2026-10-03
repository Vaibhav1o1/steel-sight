from __future__ import annotations

import io
import queue
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from billetvision.api.main import create_app
from billetvision.db import DEFAULT_SPEC_DICT, get_inspections, init_db
from billetvision.logging_io import InspectionLogger
from billetvision.runtime.events import EventBus
from billetvision.runtime.sources import SyntheticSource
from billetvision.runtime.state import RuntimeState
from billetvision.schemas import CalibrationState, Roi, Spec
from billetvision.vision import rectify
from billetvision.vision.synth import (
    BilletSpec,
    CameraSpec,
    Effects,
    SceneSpec,
    render_scene,
)


@pytest.fixture
def test_app_and_state(tmp_path: Path):
    app = create_app()

    db_path = tmp_path / "test_upload.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    db_logger = InspectionLogger(db_engine=engine, log_dir=tmp_path)

    source = SyntheticSource("station")
    state = RuntimeState(initial_source=source)
    state._active_spec = Spec(**DEFAULT_SPEC_DICT)

    bus = EventBus()
    job_q = queue.Queue()

    app.state.runtime_state = state
    app.state.event_bus = bus
    app.state.db_engine = engine
    app.state.db_logger = db_logger
    app.state.job_queue = job_q

    return app, state, engine


@pytest.fixture
def client(test_app_and_state):
    app, _, _ = test_app_and_state
    return TestClient(app)


def _make_synth_billet_image(with_marker: bool = True, defect: str | None = None, qr: bool = False) -> bytes:
    """Generate a clean synthetic billet image with or without marker."""
    rng = np.random.default_rng(42)
    billet = BilletSpec(
        center_mm=(360.0, 0.0),
        angle_deg=0.0,
        length_mm=500.0,
        width_mm=100.0,
        id_text="A12-3456",
        qr=qr,
        defect=defect,  # type: ignore
        defect_size_mm=6.5 if defect else 0.0,
    )
    scene = SceneSpec(
        billets=(billet,),
        camera=CameraSpec(),
        effects=Effects(),
        with_marker=with_marker,
    )
    img, _ = render_scene(scene, rng)
    _, enc = cv2.imencode(".jpg", img)
    return bytes(enc.tobytes())


def _make_plain_billet_image() -> bytes:
    """Make a simple image of a rectangle without marker."""
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    # White billet in center
    img[200:400, 150:650] = 220
    _, enc = cv2.imencode(".jpg", img)
    return bytes(enc.tobytes())


def test_upload_marker_present_calibrated(client, test_app_and_state):
    _, _, engine = test_app_and_state
    _, count_before = get_inspections(engine)

    img_bytes = _make_synth_billet_image(with_marker=True, qr=False)
    res = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["calibrated"] is True
    assert data["calibration"]["source"] == "marker"
    assert "accuracy assumes the marker lies" in data["calibration"]["warning"]
    assert data["length_mm"] is not None
    assert data["width_mm"] is not None
    assert data["nominal_length_mm"] == 500.0
    assert data["nominal_width_mm"] == 100.0
    assert data["tol_length_mm"] == 5.0
    assert data["tol_width_mm"] == 2.0
    assert data["length_dev_mm"] is not None
    assert data["width_dev_mm"] is not None
    assert data["length_passed"] is not None
    assert data["width_passed"] is not None
    assert data["status"] in ("Pass", "Rework", "Fail", "Review")
    assert data["annotated_url"].startswith("/inspect/image/")

    # Verify no row added to SQLite inspections DB
    _, count_after = get_inspections(engine)
    assert count_after == count_before


def test_upload_marker_invokes_rectification_pipeline(client, test_app_and_state):
    """Verify that marker calibration genuinely invokes build_rectifier and returns mm dimensions."""
    img_bytes = _make_synth_billet_image(with_marker=True)

    with patch(
        "billetvision.vision.upload_inspect.build_rectifier",
        wraps=rectify.build_rectifier,
    ) as mock_rect:
        res = client.post(
            "/inspect/image",
            files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert mock_rect.called
        assert data["calibrated"] is True
        assert data["length_mm"] > 0
        assert data["width_mm"] > 0


def test_upload_no_marker_uncalibrated(client, test_app_and_state):
    _, _, engine = test_app_and_state
    _, count_before = get_inspections(engine)

    img_bytes = _make_plain_billet_image()
    res = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
        params={"station_camera": False},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["calibrated"] is False
    assert data["calibration"]["source"] == "uncalibrated"
    assert data["length_mm"] is None
    assert data["width_mm"] is None
    assert data["length_px"] is not None
    assert data["width_px"] is not None
    assert data["status"] == "Review"

    _, count_after = get_inspections(engine)
    assert count_after == count_before


def test_upload_station_camera_with_and_without_calibration(client, test_app_and_state):
    _, state, _ = test_app_and_state
    img_bytes = _make_plain_billet_image()

    # 1. Without active calibration
    res1 = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
        params={"station_camera": True},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["calibrated"] is False
    assert d1["status"] == "Review"

    # 2. With active calibration
    with state.lock:
        state.calibration_state = lambda: CalibrationState(
            calibrated=True,
            has_background=True,
            has_intrinsics=True,
            marker_mm=80.0,
            image_px_per_mm=2.5,
            rect_px_per_mm=3.0,
            roi=Roi(x0_mm=60.0, y0_mm=-170.0, w_mm=600.0, h_mm=340.0),
            reprojection_error_px=0.5,
            verify=None,
            drift_mm=0.0,
            drift_ok=True,
            created_at=100.0,
        )

    res2 = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
        params={"station_camera": True},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["calibrated"] is True
    assert d2["calibration"]["source"] == "station"
    assert d2["length_mm"] is not None


def test_upload_test_dataset_listing(client):
    res = client.get("/inspect/test-dataset")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    if len(items) > 0:
        assert "filename" in items[0]
        assert "variant" in items[0]
        assert "expected_status" in items[0]


def test_upload_test_dataset_inspect(client, test_app_and_state):
    _, _, engine = test_app_and_state
    _, count_before = get_inspections(engine)

    # List dataset to get a valid image
    list_res = client.get("/inspect/test-dataset")
    assert list_res.status_code == 200
    items = list_res.json()

    if len(items) > 0:
        test_img_name = items[0]["filename"]
        res = client.post(f"/inspect/test-dataset/{test_img_name}")
        assert res.status_code == 200
        data = res.json()

        assert "system_result" in data
        assert "ground_truth" in data
        assert "comparison" in data
        assert data["is_test_dataset"] is True
        assert data["system_result"]["calibrated"] is True

        # Verify no inspection record is written to production DB
        _, count_after = get_inspections(engine)
        assert count_after == count_before


def test_upload_wrong_magic_bytes_415(client):
    res = client.post(
        "/inspect/image",
        files={"file": ("doc.txt", b"Hello world text file", "text/plain")},
    )
    assert res.status_code == 415
    assert res.json()["detail"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_corrupt_bytes_422(client):
    corrupt = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
    res = client.post(
        "/inspect/image",
        files={"file": ("corrupt.jpg", corrupt, "image/jpeg")},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "UNPROCESSABLE_ENTITY"


def test_upload_oversize_413(client):
    large_data = b"\xff\xd8\xff" + b"0" * (15 * 1024 * 1024 + 10)
    res = client.post(
        "/inspect/image",
        files={"file": ("large.jpg", large_data, "image/jpeg")},
    )
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_huge_pixel_image_413(client):
    pil_img = Image.new("RGB", (8000, 7000), color=(100, 100, 100))
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG")
    huge_bytes = buf.getvalue()

    res = client.post(
        "/inspect/image",
        files={"file": ("huge.jpg", huge_bytes, "image/jpeg")},
    )
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"


def test_get_annotated_image_endpoint(client):
    img_bytes = _make_synth_billet_image(with_marker=True)
    res = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
    )
    assert res.status_code == 200
    image_id = res.json()["image_id"]

    # 1. Fetch valid image
    img_res = client.get(f"/inspect/image/{image_id}.jpg")
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/jpeg"
    assert len(img_res.content) > 0

    # 2. Invalid UUID format
    invalid_res = client.get("/inspect/image/not-a-uuid.jpg")
    assert invalid_res.status_code == 404

    # 3. Non-existent UUID
    missing_res = client.get("/inspect/image/00000000-0000-0000-0000-000000000000.jpg")
    assert missing_res.status_code == 404


@pytest.mark.anyio
async def test_upload_concurrency_limit(test_app_and_state):
    import asyncio

    from httpx import ASGITransport, AsyncClient

    app, _, _ = test_app_and_state
    img_bytes = _make_synth_billet_image(with_marker=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        reqs = [
            ac.post(
                "/inspect/image",
                files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
            )
            for _ in range(4)
        ]
        responses = await asyncio.gather(*reqs)

    for res in responses:
        assert res.status_code == 200
        assert res.json()["calibrated"] is True


def test_upload_notch_defect_size_magnitude(client):
    """Verify that a notch defect reports notch depth rather than residual billet width."""
    img_bytes = _make_synth_billet_image(with_marker=True, defect="notch")
    res = client.post(
        "/inspect/image",
        files={"file": ("billet.jpg", img_bytes, "image/jpeg")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["defect_type"] == "notch"
    # Defect size must represent the notch depth (~6.5 mm), NOT the residual billet width (~93.5 mm)
    assert data["defect_size_mm"] is not None
    assert 4.0 <= data["defect_size_mm"] <= 10.0


def test_upload_multi_billet_no_cross_id_assignment(client):
    """Ensure that if the inspected billet has no readable ID, it does NOT steal another billet's ID."""
    rng = np.random.default_rng(123)
    b_upper = BilletSpec(
        center_mm=(340.0, -75.0),
        angle_deg=0.0,
        length_mm=500.0,
        width_mm=100.0,
        id_text="K24-7059",
        qr=False,
        defect=None,
        defect_size_mm=0.0,
    )
    b_lower = BilletSpec(
        center_mm=(340.0, 75.0),
        angle_deg=0.0,
        length_mm=502.0,
        width_mm=100.0,
        id_text="",
        qr=False,
        defect=None,
        defect_size_mm=0.0,
    )
    scene = SceneSpec(
        billets=(b_upper, b_lower),
        camera=CameraSpec(),
        effects=Effects(),
        with_marker=True,
    )
    img, _ = render_scene(scene, rng)
    _, enc = cv2.imencode(".jpg", img)

    res = client.post(
        "/inspect/image",
        files={"file": ("multi_billet.jpg", bytes(enc.tobytes()), "image/jpeg")},
    )
    assert res.status_code == 200
    data = res.json()
    # The inspected lower billet must NOT be assigned K24-7059 from the upper billet
    assert data["billet_id"] != "K24-7059"
