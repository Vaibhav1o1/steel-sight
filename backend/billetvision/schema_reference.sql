-- Exact reference DDL for BilletVision database (03 §2).
-- This file is for documentation reference only; SQLite tables are created
-- via SQLAlchemy Core Table objects in backend/billetvision/db.py.

CREATE TABLE specs (
  id                  TEXT PRIMARY KEY,          -- 'FLAT-500x100'
  name                TEXT NOT NULL,
  nominal_length_mm   REAL NOT NULL,
  nominal_width_mm    REAL NOT NULL,
  nominal_height_mm   REAL NULL,
  tol_length_mm       REAL NOT NULL,             -- ± tolerance
  tol_width_mm        REAL NOT NULL,
  cs_var_warn_pct     REAL NOT NULL,             -- cross-section variation → Rework
  cs_var_fail_pct     REAL NOT NULL,             -- → Fail
  notch_min_mm        REAL NOT NULL,             -- width dip that counts as a notch
  camber_max_mm       REAL NOT NULL,             -- edge bow above this → Rework
  taper_max_mm        REAL NOT NULL,             -- end-to-end width change above this → Rework
  id_template         TEXT NOT NULL,             -- 'A99-9999' (A=letter, 9=digit, others literal)
  min_area_factor     REAL NOT NULL DEFAULT 0.4, -- contour area filter vs nominal area
  max_area_factor     REAL NOT NULL DEFAULT 1.6,
  active              INTEGER NOT NULL DEFAULT 0,-- exactly one row = 1
  created_at          REAL NOT NULL
);

CREATE TABLE inspections (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                  TEXT NOT NULL,
  billet_id           TEXT NULL,
  id_source           TEXT NOT NULL,             -- IdSource
  ocr_text            TEXT NULL,                 -- normalised winning OCR candidate (may be invalid)
  ocr_confidence      REAL NULL,                 -- 0..1
  ocr_agreement       REAL NULL,                 -- share of crops agreeing with the winner, 0..1
  qr_text             TEXT NULL,
  id_mismatch         INTEGER NOT NULL DEFAULT 0,
  length_mm           REAL NOT NULL,
  width_mm            REAL NOT NULL,
  height_mm           REAL NULL,                 -- only with optional side camera
  length_dev_mm       REAL NOT NULL,             -- measured − nominal
  width_dev_mm        REAL NOT NULL,
  cs_var_pct          REAL NOT NULL,
  taper_mm            REAL NOT NULL,
  camber_mm           REAL NOT NULL,
  min_width_mm        REAL NOT NULL,
  max_width_mm        REAL NOT NULL,
  width_profile_mm    TEXT NOT NULL,             -- JSON float[21]
  defects             TEXT NOT NULL,             -- JSON DefectType[]
  status              TEXT NOT NULL,             -- InspectionStatus (after override if any)
  auto_status         TEXT NOT NULL,             -- status the system decided
  reasons             TEXT NOT NULL,             -- JSON string[]
  spec_id             TEXT NOT NULL REFERENCES specs(id),
  n_samples           INTEGER NOT NULL,
  angle_deg           REAL NOT NULL,
  latency_ms          REAL NOT NULL,             -- first sample → logged
  snapshot_path       TEXT NOT NULL,             -- relative to backend/
  source              TEXT NOT NULL,             -- SourceType
  track_id            INTEGER NOT NULL,
  override            TEXT NULL,                 -- JSON Override
  created_at          REAL NOT NULL
);
CREATE INDEX ix_inspections_ts ON inspections(ts);
CREATE INDEX ix_inspections_status ON inspections(status);
CREATE INDEX ix_inspections_billet ON inspections(billet_id);

CREATE TABLE alerts (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  inspection_id  INTEGER NULL REFERENCES inspections(id),  -- NULL for System alerts
  ts             TEXT NOT NULL,
  level          TEXT NOT NULL,                  -- AlertLevel
  message        TEXT NOT NULL,
  acknowledged   INTEGER NOT NULL DEFAULT 0,
  created_at     REAL NOT NULL
);
CREATE INDEX ix_alerts_created ON alerts(created_at);

CREATE TABLE meta (
  key    TEXT PRIMARY KEY,                       -- 'calibration' | 'session_start' | 'source'
  value  TEXT NOT NULL                           -- JSON
);
