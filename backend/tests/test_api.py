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
