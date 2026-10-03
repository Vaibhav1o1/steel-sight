from __future__ import annotations

import time

import pytest
from sqlalchemy import inspect, select

from billetvision.db import (
    DEFAULT_SPEC_DICT,
    get_active_spec,
    get_engine,
    init_db,
    meta_get,
    meta_set,
    set_active_spec,
    specs_table,
)


@pytest.fixture
def test_engine():
    engine = get_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def test_tables_created(test_engine) -> None:
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    assert "specs" in tables
    assert "inspections" in tables
    assert "alerts" in tables
    assert "meta" in tables

    # Verify inspections indexes
    inspection_indexes = [idx["name"] for idx in inspector.get_indexes("inspections")]
    assert "ix_inspections_ts" in inspection_indexes
    assert "ix_inspections_status" in inspection_indexes
    assert "ix_inspections_billet" in inspection_indexes

    # Verify alerts indexes
    alert_indexes = [idx["name"] for idx in inspector.get_indexes("alerts")]
    assert "ix_alerts_created" in alert_indexes


def test_default_spec_seeded_and_active(test_engine) -> None:
    active = get_active_spec(test_engine)
    assert active is not None
    assert active["id"] == DEFAULT_SPEC_DICT["id"]
    assert active["name"] == DEFAULT_SPEC_DICT["name"]
    assert active["nominal_length_mm"] == 500.0
    assert active["nominal_width_mm"] == 100.0
    assert active["active"] == 1

    # Ensure idempotency: re-running init_db doesn't duplicate specs
    init_db(test_engine)
    with test_engine.connect() as conn:
        count = conn.execute(select(specs_table)).fetchall()
        assert len(count) == 1


def test_activate_spec_enforces_single_active(test_engine) -> None:
    # Insert a second spec
    custom_spec = {
        "id": "CUSTOM-400x80",
        "name": "Custom bar 400 × 80 mm",
        "nominal_length_mm": 400.0,
        "nominal_width_mm": 80.0,
        "nominal_height_mm": None,
        "tol_length_mm": 4.0,
        "tol_width_mm": 1.5,
        "cs_var_warn_pct": 2.5,
        "cs_var_fail_pct": 5.0,
        "notch_min_mm": 2.5,
        "camber_max_mm": 3.0,
        "taper_max_mm": 3.0,
        "id_template": "A99-9999",
        "min_area_factor": 0.4,
        "max_area_factor": 1.6,
        "active": 0,
        "created_at": time.time(),
    }
    with test_engine.begin() as conn:
        conn.execute(specs_table.insert().values(**custom_spec))

    # Activate the custom spec
    set_active_spec("CUSTOM-400x80", test_engine)

    # Verify active spec is now CUSTOM-400x80
    active = get_active_spec(test_engine)
    assert active is not None
    assert active["id"] == "CUSTOM-400x80"

    # Verify exactly one spec in the entire table has active == 1
    with test_engine.connect() as conn:
        active_rows = conn.execute(select(specs_table).where(specs_table.c.active == 1)).fetchall()
        assert len(active_rows) == 1

    # Activating nonexistent spec raises ValueError
    with pytest.raises(ValueError, match="does not exist"):
        set_active_spec("NONEXISTENT", test_engine)


def test_meta_get_and_set(test_engine) -> None:
    # Non-existent key returns default
    assert meta_get("unknown_key", default="fallback", engine=test_engine) == "fallback"

    # Store a dict
    data = {"status": "ok", "drift_mm": 0.15, "count": 42}
    meta_set("calibration", data, engine=test_engine)

    retrieved = meta_get("calibration", engine=test_engine)
    assert retrieved == data

    # Update existing key
    updated_data = {"status": "recalibrated", "drift_mm": 0.0}
    meta_set("calibration", updated_data, engine=test_engine)
    assert meta_get("calibration", engine=test_engine) == updated_data


def test_schema_version_recorded(test_engine) -> None:
    ver = meta_get("schema_version", engine=test_engine)
    assert ver == 1


def _sample_inspection_data(idx: int) -> dict:
    return {
        "ts": f"2026-10-04T12:00:{idx:02d}.000Z",
        "billet_id": f"H24-{1000 + idx}",
        "id_source": "ocr",
        "ocr_text": f"H24-{1000 + idx}",
        "ocr_confidence": 0.95,
        "ocr_agreement": 1.0,
        "qr_text": f"H24-{1000 + idx}",
        "id_mismatch": 0,
        "length_mm": 500.2,
        "width_mm": 100.1,
        "height_mm": None,
        "length_dev_mm": 0.2,
        "width_dev_mm": 0.1,
        "width_variation_pct": 0.8,
        "taper_mm": 0.2,
        "camber_mm": 0.3,
        "min_width_mm": 99.8,
        "max_width_mm": 100.3,
        "width_profile_mm": [100.1] * 21,
        "defects": [],
        "status": "Pass",
        "auto_status": "Pass",
        "reasons": ["Within spec"],
        "spec_id": "FLAT-500x100",
        "n_samples": 7,
        "angle_deg": 0.0,
        "latency_ms": 12.0,
        "snapshot_path": f"evidence/{idx}.jpg",
        "source": "synthetic",
        "track_id": idx,
        "override": None,
        "created_at": time.time(),
    }


def test_concurrent_read_during_write(tmp_path) -> None:
    import threading

    from billetvision.db import insert_inspection, inspections_table

    db_path = tmp_path / "wal_concurrency.db"
    url = f"sqlite:///{db_path}"
    engine = get_engine(url)
    init_db(engine)

    n_records = 30
    write_errors: list[Exception] = []
    read_errors: list[Exception] = []
    reads_done = 0

    def writer():
        for i in range(n_records):
            try:
                insert_inspection(_sample_inspection_data(i), engine=engine)
                time.sleep(0.005)
            except Exception as e:
                write_errors.append(e)

    def reader():
        nonlocal reads_done
        for _ in range(n_records * 2):
            try:
                with engine.connect() as conn:
                    conn.execute(select(inspections_table.c.id)).fetchall()
                reads_done += 1
                time.sleep(0.002)
            except Exception as e:
                read_errors.append(e)

    w_thread = threading.Thread(target=writer)
    r_thread = threading.Thread(target=reader)

    w_thread.start()
    r_thread.start()

    w_thread.join(timeout=10.0)
    r_thread.join(timeout=10.0)

    assert not write_errors, f"Writer encountered errors: {write_errors}"
    assert not read_errors, f"Reader encountered errors: {read_errors}"
    assert reads_done > 0

    with engine.connect() as conn:
        final_count = len(conn.execute(select(inspections_table.c.id)).fetchall())
        assert final_count == n_records


def test_crash_safety(tmp_path) -> None:
    from billetvision.db import insert_inspection, inspections_table

    db_path = tmp_path / "crash_safety.db"
    url = f"sqlite:///{db_path}"

    # Step 1: Initial engine and insert 15 records
    engine1 = get_engine(url)
    init_db(engine1)
    for i in range(15):
        insert_inspection(_sample_inspection_data(i), engine=engine1)

    # Step 2: Abruptly dispose the engine connection pool
    engine1.dispose()

    # Step 3: Reopen database from disk using a fresh engine
    engine2 = get_engine(url)
    init_db(engine2)  # idempotent

    with engine2.connect() as conn:
        rows = conn.execute(select(inspections_table.c.id)).fetchall()
        assert len(rows) == 15

    # Step 4: Continue writing safely
    new_id = insert_inspection(_sample_inspection_data(15), engine=engine2)
    assert new_id == 16
    engine2.dispose()
