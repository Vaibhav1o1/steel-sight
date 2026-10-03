from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.engine import Engine

from billetvision import config

logger = logging.getLogger(__name__)

metadata = MetaData()

specs_table = Table(
    "specs",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("nominal_length_mm", Float, nullable=False),
    Column("nominal_width_mm", Float, nullable=False),
    Column("nominal_height_mm", Float, nullable=True),
    Column("tol_length_mm", Float, nullable=False),
    Column("tol_width_mm", Float, nullable=False),
    Column("cs_var_warn_pct", Float, nullable=False),
    Column("cs_var_fail_pct", Float, nullable=False),
    Column("notch_min_mm", Float, nullable=False),
    Column("camber_max_mm", Float, nullable=False),
    Column("taper_max_mm", Float, nullable=False),
    Column("id_template", String, nullable=False),
    Column("min_area_factor", Float, nullable=False, default=0.4),
    Column("max_area_factor", Float, nullable=False, default=1.6),
    Column("active", Integer, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
)

inspections_table = Table(
    "inspections",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String, nullable=False),
    Column("billet_id", String, nullable=True),
    Column("id_source", String, nullable=False),
    Column("ocr_text", String, nullable=True),
    Column("ocr_confidence", Float, nullable=True),
    Column("ocr_agreement", Float, nullable=True),
    Column("qr_text", String, nullable=True),
    Column("id_mismatch", Integer, nullable=False, default=0),
    Column("length_mm", Float, nullable=False),
    Column("width_mm", Float, nullable=False),
    Column("height_mm", Float, nullable=True),
    Column("length_dev_mm", Float, nullable=False),
    Column("width_dev_mm", Float, nullable=False),
    Column("width_variation_pct", Float, nullable=False),
    Column("taper_mm", Float, nullable=False),
    Column("camber_mm", Float, nullable=False),
    Column("min_width_mm", Float, nullable=False),
    Column("max_width_mm", Float, nullable=False),
    Column("width_profile_mm", Text, nullable=False),
    Column("defects", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("auto_status", String, nullable=False),
    Column("reasons", Text, nullable=False),
    Column("spec_id", String, ForeignKey("specs.id"), nullable=False),
    Column("n_samples", Integer, nullable=False),
    Column("angle_deg", Float, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("snapshot_path", String, nullable=False),
    Column("source", String, nullable=False),
    Column("track_id", Integer, nullable=False),
    Column("override", Text, nullable=True),
    Column("created_at", Float, nullable=False),
    Index("ix_inspections_ts", "ts"),
    Index("ix_inspections_status", "status"),
    Index("ix_inspections_billet", "billet_id"),
)

alerts_table = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("inspection_id", Integer, ForeignKey("inspections.id"), nullable=True),
    Column("ts", String, nullable=False),
    Column("level", String, nullable=False),
    Column("message", String, nullable=False),
    Column("acknowledged", Integer, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
    Index("ix_alerts_created", "created_at"),
)

meta_table = Table(
    "meta",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", Text, nullable=False),
)

_global_engine: Engine | None = None

DEFAULT_SPEC_DICT: dict[str, Any] = {
    "id": "FLAT-500x100",
    "name": "Flat bar 500 × 100 mm",
    "nominal_length_mm": 500.0,
    "nominal_width_mm": 100.0,
    "nominal_height_mm": None,
    "tol_length_mm": 5.0,
    "tol_width_mm": 2.0,
    "cs_var_warn_pct": 3.0,
    "cs_var_fail_pct": 6.0,
    "notch_min_mm": 3.0,
    "camber_max_mm": 4.0,
    "taper_max_mm": 4.0,
    "id_template": "A99-9999",
    "min_area_factor": 0.4,
    "max_area_factor": 1.6,
    "active": 1,
}


def _setup_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable WAL mode, NORMAL synchronous, and foreign keys on SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(database_url: str | None = None) -> Engine:
    """Create or return the cached SQLAlchemy Engine with WAL pragmas."""
    global _global_engine
    url = database_url or config.DATABASE_URL
    if _global_engine is not None and database_url is None:
        return _global_engine

    # Ensure parent directory exists for file-based SQLite
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        db_path_str = url.replace("sqlite:///", "")
        db_path = Path(db_path_str).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, future=True)

    if url.startswith("sqlite"):
        event.listen(engine, "connect", _setup_sqlite_pragmas)

    if database_url is None:
        _global_engine = engine

    return engine


def init_db(engine: Engine | None = None) -> None:
    """Initialize database tables and seed default spec if specs table is empty."""
    eng = engine or get_engine()
    metadata.create_all(eng)

    with eng.begin() as conn:
        result = conn.execute(select(specs_table.c.id).limit(1)).fetchone()
        if result is None:
            now = time.time()
            seed_row = dict(DEFAULT_SPEC_DICT)
            seed_row["created_at"] = now
            conn.execute(specs_table.insert().values(**seed_row))
            logger.info("Initialized DB and seeded default spec FLAT-500x100")


def set_active_spec(spec_id: str, engine: Engine | None = None) -> None:
    """Set the active spec atomically; deactivates all other specs."""
    eng = engine or get_engine()
    with eng.begin() as conn:
        # Check target spec exists
        row = conn.execute(select(specs_table.c.id).where(specs_table.c.id == spec_id)).fetchone()
        if row is None:
            raise ValueError(f"Spec '{spec_id}' does not exist")

        # Deactivate all
        conn.execute(specs_table.update().values(active=0))
        # Activate target
        conn.execute(specs_table.update().where(specs_table.c.id == spec_id).values(active=1))


def get_active_spec(engine: Engine | None = None) -> dict[str, Any] | None:
    """Return the currently active spec as a dictionary."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(select(specs_table).where(specs_table.c.active == 1)).mappings().first()
        if row is None:
            return None
        return dict(row)


def meta_get(key: str, default: Any = None, engine: Engine | None = None) -> Any:
    """Retrieve and JSON-decode a metadata value by key."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        row = conn.execute(select(meta_table.c.value).where(meta_table.c.key == key)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return default


def meta_set(key: str, value: Any, engine: Engine | None = None) -> None:
    """Store a JSON-encoded metadata value by key (insert or replace)."""
    eng = engine or get_engine()
    val_json = json.dumps(value)
    with eng.begin() as conn:
        existing = conn.execute(select(meta_table.c.key).where(meta_table.c.key == key)).fetchone()
        if existing is not None:
            conn.execute(meta_table.update().where(meta_table.c.key == key).values(value=val_json))
        else:
            conn.execute(meta_table.insert().values(key=key, value=val_json))
