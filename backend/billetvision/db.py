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
    func,
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
    """Initialize database tables, record schema version in meta, and seed default spec if empty."""
    eng = engine or get_engine()
    metadata.create_all(eng)

    with eng.begin() as conn:
        # Schema versioning in meta
        ver_row = conn.execute(
            select(meta_table.c.value).where(meta_table.c.key == "schema_version")
        ).fetchone()
        if ver_row is None:
            conn.execute(meta_table.insert().values(key="schema_version", value=json.dumps(1)))

        result = conn.execute(select(specs_table.c.id).limit(1)).fetchone()
        if result is None:
            now = time.time()
            seed_row = dict(DEFAULT_SPEC_DICT)
            seed_row["created_at"] = now
            conn.execute(specs_table.insert().values(**seed_row))
            logger.info("Initialized DB and seeded default spec FLAT-500x100")


def insert_inspection(record: dict[str, Any], engine: Engine | None = None) -> int:
    """Insert a single inspection record in its own transaction, returning the inserted id."""
    eng = engine or get_engine()
    # Normalize record fields: ensure JSON fields are serialized if passed as lists/dicts
    rec = dict(record)
    if isinstance(rec.get("width_profile_mm"), (list, tuple)):
        rec["width_profile_mm"] = json.dumps(rec["width_profile_mm"])
    if isinstance(rec.get("defects"), (list, tuple)):
        rec["defects"] = json.dumps(rec["defects"])
    if isinstance(rec.get("reasons"), (list, tuple)):
        rec["reasons"] = json.dumps(rec["reasons"])
    if isinstance(rec.get("override"), dict):
        rec["override"] = json.dumps(rec["override"])

    # Alias handling: support cs_var_pct if width_variation_pct is not given
    if "width_variation_pct" not in rec and "cs_var_pct" in rec:
        rec["width_variation_pct"] = rec.pop("cs_var_pct")
    elif "cs_var_pct" in rec:
        rec.pop("cs_var_pct")
        
    if "snapshot_url" in rec and "snapshot_path" not in rec:
        rec["snapshot_path"] = rec.pop("snapshot_url")
    elif "snapshot_url" in rec:
        rec.pop("snapshot_url")

    with eng.begin() as conn:
        res = conn.execute(inspections_table.insert().values(**rec))
        return int(res.inserted_primary_key[0])


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


def get_inspections(
    engine: Engine | None = None,
    status: str | None = None,
    billet_id: str | None = None,
    spec_id: str | None = None,
    since: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Any], int]:
    eng = engine or get_engine()
    from billetvision.schemas import Inspection
    with eng.connect() as conn:
        q = select(inspections_table)
        count_q = select(func.count(inspections_table.c.id))
        
        if status:
            q = q.where(inspections_table.c.status == status)
            count_q = count_q.where(inspections_table.c.status == status)
        if billet_id:
            q = q.where(inspections_table.c.billet_id == billet_id)
            count_q = count_q.where(inspections_table.c.billet_id == billet_id)
        if spec_id:
            q = q.where(inspections_table.c.spec_id == spec_id)
            count_q = count_q.where(inspections_table.c.spec_id == spec_id)
        if since is not None:
            q = q.where(inspections_table.c.created_at >= since)
            count_q = count_q.where(inspections_table.c.created_at >= since)
            
        total = conn.execute(count_q).scalar() or 0
        
        q = q.order_by(inspections_table.c.id.desc()).limit(limit).offset(offset)
        rows = conn.execute(q).mappings().all()
        
        items = []
        for row in rows:
            d = dict(row)
            if isinstance(d.get("width_profile_mm"), str):
                d["width_profile_mm"] = json.loads(d["width_profile_mm"])
            if isinstance(d.get("defects"), str):
                d["defects"] = json.loads(d["defects"])
            if isinstance(d.get("reasons"), str):
                d["reasons"] = json.loads(d["reasons"])
            if isinstance(d.get("override"), str):
                d["override"] = json.loads(d["override"])
            d["snapshot_url"] = f"/inspections/{d['id']}/snapshot.jpg"
            if "snapshot_path" in d:
                del d["snapshot_path"]
                
            items.append(Inspection(**d))
            
        return items, total

def get_alerts(engine: Engine | None = None, limit: int = 50) -> list[Any]:
    eng = engine or get_engine()
    from billetvision.schemas import Alert
    with eng.connect() as conn:
        q = select(alerts_table).order_by(alerts_table.c.id.desc()).limit(limit)
        rows = conn.execute(q).mappings().all()
        return [Alert(**dict(r)) for r in rows]

def ack_alert(alert_id: int, engine: Engine | None = None) -> Any:
    eng = engine or get_engine()
    from billetvision.schemas import Alert
    with eng.begin() as conn:
        conn.execute(
            alerts_table.update().where(alerts_table.c.id == alert_id).values(acknowledged=1)
        )
        row = conn.execute(
            select(alerts_table).where(alerts_table.c.id == alert_id)
        ).mappings().first()
        if not row:
            raise ValueError(f"Alert {alert_id} not found")
        return Alert(**dict(row))
