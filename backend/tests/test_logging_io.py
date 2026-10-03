from __future__ import annotations

import csv
import io
import time
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from sqlalchemy import select

from billetvision.db import get_engine, init_db, inspections_table
from billetvision.logging_io import (
    LOG_COLUMNS,
    InspectionLogger,
    build_csv,
    build_json,
    build_workbook,
    row_to_export_dict,
)


def _make_dummy_record(idx: int, status: str = "Pass") -> dict[str, Any]:
    return {
        "ts": f"2026-10-04T12:00:{idx % 60:02d}.000Z",
        "billet_id": f"H24-{1000 + idx}",
        "id_source": "ocr",
        "ocr_text": f"H24-{1000 + idx}",
        "ocr_confidence": 0.95,
        "ocr_agreement": 1.0,
        "qr_text": f"H24-{1000 + idx}",
        "id_mismatch": 0,
        "length_mm": 500.0 + idx * 0.1,
        "width_mm": 100.0 + (idx % 3) * 0.1,
        "height_mm": None,
        "length_dev_mm": idx * 0.1,
        "width_dev_mm": (idx % 3) * 0.1,
        "width_variation_pct": 0.5,
        "taper_mm": 0.1,
        "camber_mm": 0.2,
        "min_width_mm": 99.8,
        "max_width_mm": 100.2,
        "width_profile_mm": [100.0] * 21,
        "defects": ["notch"] if status == "Fail" else [],
        "status": status,
        "auto_status": status,
        "reasons": ["Within spec"] if status == "Pass" else ["Defect detected"],
        "spec_id": "FLAT-500x100",
        "n_samples": 7,
        "angle_deg": 0.0,
        "latency_ms": 14.5,
        "snapshot_path": f"snapshots/evidence_{idx}.jpg",
        "source": "synthetic",
        "track_id": idx,
        "override": None,
        "created_at": time.time(),
    }


def test_row_to_export_dict_and_formats() -> None:
    rec = _make_dummy_record(1, status="Pass")
    exp = row_to_export_dict(rec)

    for col in LOG_COLUMNS:
        assert col in exp

    assert exp["billet_id"] == "H24-1001"
    assert exp["status"] == "Pass"
    assert exp["width_variation_pct"] == 0.5

    # CSV builder
    csv_str = build_csv([rec])
    reader = csv.reader(io.StringIO(csv_str))
    lines = list(reader)
    assert len(lines) == 2
    assert lines[0] == list(LOG_COLUMNS)
    assert lines[1][2] == "H24-1001"

    # JSON builder
    json_str = build_json([rec])
    assert "H24-1001" in json_str

    # Workbook builder
    wb_bytes = build_workbook([rec])
    wb = openpyxl.load_workbook(io.BytesIO(wb_bytes))
    assert "Inspections" in wb.sheetnames
    assert "Summary" in wb.sheetnames

    ws_ins = wb["Inspections"]
    assert ws_ins.max_row == 2
    # Verify Pass fill is green
    cell = ws_ins.cell(row=2, column=LOG_COLUMNS.index("status") + 1)
    assert cell.fill.start_color.rgb == "00C6EFCE" or cell.fill.start_color.rgb == "C6EFCE"


def test_200_records_count_equality(tmp_path: Path) -> None:
    db_path = tmp_path / "test_200.db"
    log_dir = tmp_path / "logs_200"
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    logger = InspectionLogger(
        log_dir=log_dir,
        db_engine=engine,
        queue_size=300,
        xlsx_sync_interval=10,
    )

    n_records = 205
    for i in range(n_records):
        st = "Pass" if i % 4 == 0 else ("Rework" if i % 4 == 1 else "Fail")
        logger.log_inspection(_make_dummy_record(i, status=st))

    logger.flush_sync(timeout=10.0)
    logger.stop(timeout=5.0)

    # 1. Assert SQLite count
    with engine.connect() as conn:
        sqlite_count = len(conn.execute(select(inspections_table.c.id)).fetchall())
    assert sqlite_count == n_records

    # 2. Assert CSV row count
    csv_file = log_dir / "inspections.csv"
    assert csv_file.exists()
    with open(csv_file, encoding="utf-8") as f:
        csv_rows = list(csv.reader(f))
    # Exclude header
    assert len(csv_rows) - 1 == n_records

    # 3. Assert XLSX row count
    xlsx_file = log_dir / "inspections.xlsx"
    assert xlsx_file.exists()
    wb = openpyxl.load_workbook(xlsx_file)
    ws = wb["Inspections"]
    assert ws.max_row - 1 == n_records

    # Check Summary sheet count
    ws_sum = wb["Summary"]
    assert ws_sum["B5"].value == n_records


def test_simulated_lock_csv_and_xlsx_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "lock_test.db"
    log_dir = tmp_path / "logs_lock"
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    logger = InspectionLogger(
        log_dir=log_dir,
        db_engine=engine,
        queue_size=50,
        xlsx_sync_interval=2,
    )

    # Simulate CSV write lock
    real_open = open
    lock_csv = True

    def mock_open(file, *args, **kwargs):
        if lock_csv and "inspections.csv" in str(file) and "a" in args:
            raise PermissionError("Simulated CSV file lock")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    # Send 5 records while CSV is locked
    for i in range(5):
        logger.log_inspection(_make_dummy_record(i))

    time.sleep(0.5)
    assert logger.pending_count > 0 or logger.blocked

    # Now unlock CSV and wait for recovery
    lock_csv = False
    time.sleep(1.5)  # logger retries every 1 second
    logger.flush_sync(timeout=5.0)

    assert logger.pending_count == 0
    assert not logger.blocked
    csv_file = log_dir / "inspections.csv"
    with real_open(csv_file, encoding="utf-8") as f:
        assert len(list(csv.reader(f))) - 1 == 5

    # Simulate XLSX replace lock
    import os

    real_replace = os.replace

    def mock_replace(src, dst):
        if "inspections.xlsx" in str(dst):
            raise PermissionError("Simulated Excel file lock")
        return real_replace(src, dst)

    monkeypatch.setattr("os.replace", mock_replace)

    # Enqueue 3 more records
    for i in range(5, 8):
        logger.log_inspection(_make_dummy_record(i))

    logger.flush_sync(timeout=5.0)

    # Verify fallback timestamped xlsx was generated
    fallbacks = list(log_dir.glob("billet_log_*.xlsx"))
    assert len(fallbacks) >= 1, "Timestamped fallback Excel file must be written when main file is locked"

    # Restore os.replace and verify recovery
    monkeypatch.setattr("os.replace", real_replace)
    logger.flush_sync(timeout=5.0)
    logger.stop(timeout=3.0)

    wb = openpyxl.load_workbook(log_dir / "inspections.xlsx")
    assert wb["Inspections"].max_row - 1 == 8


def test_vision_loop_non_blocking_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "non_blocking.db"
    log_dir = tmp_path / "logs_nb"
    engine = get_engine(f"sqlite:///{db_path}")
    init_db(engine)

    logger = InspectionLogger(
        log_dir=log_dir,
        db_engine=engine,
        queue_size=100,
    )

    # Inject 2 second delay into CSV append
    real_append = logger._append_to_csv

    def slow_append(records):
        time.sleep(2.0)
        real_append(records)

    monkeypatch.setattr(logger, "_append_to_csv", slow_append)

    # Producer thread should push 30 items instantaneously without waiting for the 2 s write delay
    t_start = time.perf_counter()
    for i in range(30):
        ok = logger.log_inspection(_make_dummy_record(i), block=False)
        assert ok is True
    t_elapsed = time.perf_counter() - t_start

    # Must complete well under 100 ms (typically < 5 ms)
    assert t_elapsed < 0.15, f"Producer was blocked: took {t_elapsed:.4f} s for 30 puts"

    # Cleanup
    monkeypatch.setattr(logger, "_append_to_csv", real_append)
    logger.stop(timeout=5.0)
