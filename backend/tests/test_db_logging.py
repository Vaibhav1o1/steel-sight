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
