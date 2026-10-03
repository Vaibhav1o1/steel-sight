from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from billetvision.api.main import create_app
from billetvision.db import init_db, inspections_table


@pytest.fixture
def analytics_test_env(tmp_path: Path):
    app = create_app()

    db_path = tmp_path / "test_analytics.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)

    app.state.db_engine = engine
    return app, engine


@pytest.fixture
def client(analytics_test_env):
    app, _ = analytics_test_env
    return TestClient(app)


def _seed_inspections(engine, records: list[dict]):
    with engine.begin() as conn:
        for idx, r in enumerate(records):
            conn.execute(
                inspections_table.insert().values(
                    id=idx + 1,
                    ts=r.get("ts", f"2026-10-03T14:0{idx:02d}:00.000"),
                    billet_id=r.get("billet_id", f"B{idx:03d}"),
                    id_source="ocr",
                    ocr_text="B001",
                    ocr_confidence=0.95,
                    ocr_agreement=1.0,
                    qr_text=None,
                    id_mismatch=0,
                    length_mm=500.0,
                    width_mm=100.0,
                    height_mm=None,
                    length_dev_mm=0.0,
                    width_dev_mm=0.0,
                    width_variation_pct=0.5,
                    taper_mm=0.0,
                    camber_mm=0.0,
                    min_width_mm=100.0,
                    max_width_mm=100.0,
                    width_profile_mm=json.dumps([100.0] * 21),
                    defects=json.dumps([]),
                    status=r.get("status", "Pass"),
                    auto_status=r.get("auto_status", r.get("status", "Pass")),
                    reasons=json.dumps([]),
                    spec_id="FLAT-500x100",
                    n_samples=5,
                    angle_deg=0.0,
                    latency_ms=45.0,
                    snapshot_path="snapshots/test.jpg",
                    source=r.get("source", "synthetic"),
                    track_id=idx + 1,
                    override=json.dumps(r.get("override")) if r.get("override") else None,
                    created_at=1000.0 + idx * 60,
                )
            )


def test_status_series_empty_db(client):
    res = client.get("/analytics/status-series")
    assert res.status_code == 200
    data = res.json()
    assert data["total_inspections"] == 0
    assert data["total_evaluated"] == 0
    assert data["total_nonconforming"] == 0
    assert data["overall_p_bar"] is None
    assert len(data["buckets"]) == 0


def test_status_series_count_mode_and_p_chart(client, analytics_test_env):
    _, engine = analytics_test_env

    # 30 items: 20 in bucket 1 (16 Pass, 3 Rework, 1 Fail), 10 in bucket 2 (8 Pass, 2 Review)
    records = []
    # Bucket 1: 16 Pass, 3 Rework, 1 Fail
    for _ in range(16):
        records.append({"status": "Pass", "source": "synthetic"})
    for _ in range(3):
        records.append({"status": "Rework", "source": "synthetic"})
    for _ in range(1):
        records.append({"status": "Fail", "source": "synthetic"})
    # Bucket 2: 8 Pass, 2 Review
    for _ in range(8):
        records.append({"status": "Pass", "source": "synthetic"})
    for _ in range(2):
        records.append({"status": "Review", "source": "synthetic"})

    _seed_inspections(engine, records)

    res = client.get("/analytics/status-series?mode=count&bucket_size=20")
    assert res.status_code == 200
    data = res.json()

    assert data["total_inspections"] == 30
    assert data["review_count"] == 2
    # Review is excluded: total evaluated = 16+3+1 + 8 = 28
    assert data["total_evaluated"] == 28
    # Total nonconforming = 3 Rework + 1 Fail = 4
    assert data["total_nonconforming"] == 4
    assert data["overall_p_bar"] == round(4 / 28, 4)
    assert data["has_synthetic"] is True

    buckets = data["buckets"]
    assert len(buckets) == 2

    # Bucket 1: 20 samples evaluated -> reliable is True
    b1 = buckets[0]
    assert b1["pass_count"] == 16
    assert b1["rework_count"] == 3
    assert b1["fail_count"] == 1
    assert b1["review_count"] == 0
    assert b1["evaluated_count"] == 20
    assert b1["nonconforming_count"] == 4
    assert b1["p_rate"] == 4 / 20  # 0.20
    assert b1["reliable"] is True
    assert b1["ucl"] is not None
    assert b1["lcl"] is not None

    # Bucket 2: 8 evaluated, 2 review -> reliable is False (< 20 evaluated)
    b2 = buckets[1]
    assert b2["pass_count"] == 8
    assert b2["review_count"] == 2
    assert b2["evaluated_count"] == 8
    assert b2["nonconforming_count"] == 0
    assert b2["p_rate"] == 0.0
    assert b2["reliable"] is False


def test_status_series_final_vs_auto_basis(client, analytics_test_env):
    _, engine = analytics_test_env

    # 1 item: auto_status="Fail", but status="Pass" (overridden)
    _seed_inspections(
        engine,
        [
            {
                "status": "Pass",
                "auto_status": "Fail",
                "source": "webcam",
                "override": {"user": "qa", "reason": "false positive"},
            }
        ],
    )

    # 1. Final basis
    res_final = client.get("/analytics/status-series?basis=final")
    d_final = res_final.json()
    assert d_final["pass_count"] == 1
    assert d_final["fail_count"] == 0
    assert d_final["total_nonconforming"] == 0

    # 2. Auto basis
    res_auto = client.get("/analytics/status-series?basis=auto")
    d_auto = res_auto.json()
    assert d_auto["pass_count"] == 0
    assert d_auto["fail_count"] == 1
    assert d_auto["total_nonconforming"] == 1


def test_status_series_source_filter(client, analytics_test_env):
    _, engine = analytics_test_env

    # 3 records: 1 synthetic, 1 webcam, 1 file
    _seed_inspections(
        engine,
        [
            {"status": "Pass", "source": "synthetic"},
            {"status": "Fail", "source": "webcam"},
            {"status": "Rework", "source": "file"},
        ],
    )

    # 1. Source = synthetic
    res_syn = client.get("/analytics/status-series?source=synthetic")
    d_syn = res_syn.json()
    assert d_syn["total_inspections"] == 1
    assert d_syn["pass_count"] == 1
    assert d_syn["has_synthetic"] is True

    # 2. Source = real (should include webcam + file)
    res_real = client.get("/analytics/status-series?source=real")
    d_real = res_real.json()
    assert d_real["total_inspections"] == 2
    assert d_real["fail_count"] == 1
    assert d_real["rework_count"] == 1
    assert d_real["has_synthetic"] is False

    # 3. Source = all
    res_all = client.get("/analytics/status-series?source=all")
    d_all = res_all.json()
    assert d_all["total_inspections"] == 3
    assert d_all["has_synthetic"] is True


def test_status_series_time_mode(client, analytics_test_env):
    _, engine = analytics_test_env

    records = [
        {"ts": "2026-10-03T14:00:10.000", "status": "Pass"},
        {"ts": "2026-10-03T14:00:40.000", "status": "Fail"},
        {"ts": "2026-10-03T14:06:10.000", "status": "Pass"},
    ]
    _seed_inspections(engine, records)

    res = client.get("/analytics/status-series?mode=time&interval=5m")
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "time"
    assert len(data["buckets"]) == 2
