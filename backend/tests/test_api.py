from __future__ import annotations

import queue
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from billetvision.api.main import create_app
from billetvision.db import DEFAULT_SPEC_DICT, init_db
from billetvision.logging_io import InspectionLogger
from billetvision.runtime.events import EventBus
from billetvision.runtime.sources import SyntheticSource
from billetvision.runtime.state import RuntimeState
from billetvision.schemas import Spec


@pytest.fixture
def app_and_state(tmp_path: Path):
    app = create_app()
    
    # Mock dependencies
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    init_db(engine)
    db_logger = InspectionLogger(db_engine=engine, log_dir=tmp_path)
    
    source = SyntheticSource("test")
    state = RuntimeState(initial_source=source)
    state._active_spec = Spec(**DEFAULT_SPEC_DICT)
    
    bus = EventBus()
    job_q = queue.Queue()
    
    app.state.runtime_state = state
    app.state.event_bus = bus
    app.state.db_engine = engine
    app.state.db_logger = db_logger
    app.state.job_queue = job_q
    
    return app, state, db_logger


@pytest.fixture
def client(app_and_state):
    app, state, _ = app_and_state
    return TestClient(app)


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_status(client):
    res = client.get("/status")
    assert res.status_code == 200
    data = res.json()
    assert data["source"]["type"] == "synthetic"
    assert data["calibrated"] is False


def test_control_pause(client):
    res = client.post("/control/pause")
    assert res.status_code == 200
    assert res.json()["paused"] is True


def test_control_resume(client):
    res = client.post("/control/resume")
    assert res.status_code == 200
    assert res.json()["paused"] is False


def test_specs(client):
    res = client.get("/specs")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_inspections_empty(client):
    res = client.get("/inspections")
    assert res.status_code == 200
    assert res.json()["total"] == 0


def test_websocket(client, app_and_state):
    app, state, _ = app_and_state
    bus = app.state.event_bus
    
    # We send a message so the q.get() yields immediately
    # We can connect, then publish
    with client.websocket_connect("/ws") as websocket:
        bus.publish({"type": "test_event"})
        data = websocket.receive_json()
        assert "type" in data


def test_snapshot_503_when_no_frame(client):
    res = client.get("/snapshot.jpg")
    assert res.status_code == 503
    data = res.json()
    assert data["detail"]["code"] == "CAMERA_UNAVAILABLE"


def test_snapshot_200_when_frame_exists(client, app_and_state):
    _, state, _ = app_and_state
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb"
    state.publish_jpeg("annotated", fake_jpeg)
    res = client.get("/snapshot.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content == fake_jpeg

