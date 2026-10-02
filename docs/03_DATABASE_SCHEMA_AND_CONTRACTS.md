# 03 — Database Schema & Data Contracts

**Single source of truth for every name, field, type, unit and enum value.** If another doc disagrees on a name or shape, this file wins. Field names are `snake_case` everywhere (DB, Python, JSON, TypeScript). Units are part of the name: `_mm`, `_px`, `_pct`, `_ms`, `_s`, `_deg`.

Conventions:
- **Timestamps:** `ts` is local ISO-8601 with milliseconds, no timezone, e.g. `"2026-10-03T14:05:09.231"`. Wall-clock floats (`created_at`) are Unix seconds.
- **Percentages** named `_pct` are **percent values** (`0.8` means 0.8%). Rates named `_rate` or `accuracy` are fractions 0–1.
- **Bed coordinates:** millimetres in the plane of the billet tops. Origin = centre of the ArUco marker; +x along the marker's top edge (left → right), +y downwards (marker top → bottom), as seen in the image.
- No `NaN`/`Infinity` leaves the API; use `null` only where the type allows.

---

## 1. Enums (exact string values)

| Enum | Values |
|---|---|
| `InspectionStatus` | `"Pass"`, `"Rework"`, `"Fail"` |
| `IdSource` | `"ocr"`, `"qr"`, `"none"` |
| `DefectType` | `"notch"`, `"taper"`, `"bulge"`, `"camber"` |
| `SourceType` | `"webcam"`, `"url"`, `"file"`, `"synthetic"` |
| `TriggerMode` | `"auto"`, `"stable"`, `"line"` |
| `AlertLevel` | `"Fail"`, `"Rework"`, `"System"` |
| `LogFileStatus` | `"ok"`, `"locked"`, `"error"` |
| `StreamView` | `"annotated"`, `"rectified"`, `"raw"` |

---

## 2. Database schema (SQLite via SQLAlchemy Core)

Defined as SQLAlchemy Core `Table` objects in `backend/billetvision/db.py`; the DDL below is the exact reference (save as `backend/billetvision/schema_reference.sql`, never executed by the app). Enable `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` on connect. JSON columns are TEXT holding JSON.

```sql
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
```

Default spec seeded on first start (and in tests):

| field | value |
|---|---|
| id / name | `FLAT-500x100` / `Flat bar 500 × 100 mm` |
| nominal L / W / H | 500.0 / 100.0 / null |
| tol L / W | 5.0 / 2.0 |
| cs_var warn / fail | 3.0 / 6.0 |
| notch_min / camber_max / taper_max | 3.0 / 4.0 / 4.0 |
| id_template | `A99-9999` |
| active | 1 |

---

## 3. Python API contracts (`backend/billetvision/schemas.py`)

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .enums import InspectionStatus, IdSource, DefectType, SourceType, TriggerMode, AlertLevel, LogFileStatus

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

# ── Specs ───────────────────────────────────────────
class Spec(Contract):
    id: str
    name: str
    nominal_length_mm: float = Field(gt=0)
    nominal_width_mm: float = Field(gt=0)
    nominal_height_mm: float | None = None
    tol_length_mm: float = Field(gt=0)
    tol_width_mm: float = Field(gt=0)
    cs_var_warn_pct: float = Field(gt=0)
    cs_var_fail_pct: float = Field(gt=0)
    notch_min_mm: float = Field(gt=0)
    camber_max_mm: float = Field(gt=0)
    taper_max_mm: float = Field(gt=0)
    id_template: str = Field(min_length=1, max_length=20)
    min_area_factor: float = 0.4
    max_area_factor: float = 1.6
    active: bool = False

class SpecUpsert(Contract):              # body for POST /specs and PUT /specs/{id}; same fields minus `active`
    id: str
    name: str
    nominal_length_mm: float = Field(gt=0)
    nominal_width_mm: float = Field(gt=0)
    nominal_height_mm: float | None = None
    tol_length_mm: float = Field(gt=0)
    tol_width_mm: float = Field(gt=0)
    cs_var_warn_pct: float = Field(gt=0)
    cs_var_fail_pct: float = Field(gt=0)
    notch_min_mm: float = Field(gt=0)
    camber_max_mm: float = Field(gt=0)
    taper_max_mm: float = Field(gt=0)
    id_template: str = Field(min_length=1, max_length=20)
    min_area_factor: float = 0.4
    max_area_factor: float = 1.6

# ── Inspections ─────────────────────────────────────
class Override(Contract):
    billet_id: str | None = None
    status: InspectionStatus | None = None
    note: str = Field(min_length=1, max_length=500)
    at: float

class Inspection(Contract):
    id: int
    ts: str
    billet_id: str | None
    id_source: IdSource
    ocr_text: str | None
    ocr_confidence: float | None
    ocr_agreement: float | None
    qr_text: str | None
    id_mismatch: bool
    length_mm: float
    width_mm: float
    height_mm: float | None
    length_dev_mm: float
    width_dev_mm: float
    cs_var_pct: float
    taper_mm: float
    camber_mm: float
    min_width_mm: float
    max_width_mm: float
    width_profile_mm: list[float]
    defects: list[DefectType]
    status: InspectionStatus
    auto_status: InspectionStatus
    reasons: list[str]
    spec_id: str
    n_samples: int
    angle_deg: float
    latency_ms: float
    snapshot_url: str                    # "/inspections/{id}/snapshot.jpg"
    source: SourceType
    track_id: int
    override: Override | None
    created_at: float

class InspectionPatch(Contract):
    billet_id: str | None = None
    status: InspectionStatus | None = None
    note: str = Field(min_length=1, max_length=500)

class InspectionList(Contract):
    items: list[Inspection]
    total: int

class Alert(Contract):
    id: int
    inspection_id: int | None
    ts: str
    level: AlertLevel
    message: str
    acknowledged: bool
    created_at: float

# ── Calibration ─────────────────────────────────────
class Roi(Contract):
    x0_mm: float
    y0_mm: float
    w_mm: float = Field(gt=0)
    h_mm: float = Field(gt=0)

class VerifyRequest(Contract):
    known_length_mm: float = Field(gt=0)
    known_width_mm: float | None = Field(default=None, gt=0)

class VerifyResult(Contract):
    known_length_mm: float
    measured_length_mm: float
    length_error_pct: float              # signed
    known_width_mm: float | None
    measured_width_mm: float | None
    width_error_pct: float | None
    ok: bool                             # |errors| ≤ 1.0
    at: float

class CalibrationState(Contract):
    calibrated: bool                     # homography present
    has_background: bool
    has_intrinsics: bool
    marker_mm: float
    image_px_per_mm: float | None        # camera resolution on the bed plane
    rect_px_per_mm: float
    roi: Roi
    reprojection_error_px: float | None
    verify: VerifyResult | None
    drift_mm: float | None
    drift_ok: bool
    created_at: float | None

class MarkerResult(Contract):
    found: bool
    marker_id: int
    corners_px: list[list[float]]        # 4 × [x, y], clockwise from top-left
    image_px_per_mm: float
    reprojection_error_px: float
    calibration: CalibrationState

# ── Station control / status ────────────────────────
class SourceRequest(Contract):
    type: SourceType
    value: str = ""                      # index, URL or path; ignored for synthetic

class SourceInfo(Contract):
    type: SourceType
    value: str
    frame_width: int | None
    frame_height: int | None

class TriggerModeRequest(Contract):
    mode: TriggerMode

class StationStatus(Contract):
    source: SourceInfo
    camera_ok: bool
    calibrated: bool
    has_background: bool
    paused: bool
    trigger_mode: TriggerMode
    active_spec: Spec
    fps_capture: float
    fps_process: float
    log_status: LogFileStatus
    ocr_ready: bool

class Health(Contract):
    ok: bool
    db: bool
    camera_ok: bool
    calibrated: bool
    ocr_ready: bool

# ── Metrics & evaluation ────────────────────────────
class Metrics(Contract):
    fps_capture: float
    fps_process: float
    process_ms_p50: float
    process_ms_p95: float
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    inspections_total: int
    by_status: dict[str, int]            # all three statuses present
    throughput_per_min: float            # last 5 minutes
    ocr_read_rate: float | None          # share with valid OCR id, 0..1
    queue_depth: int
    dropped_jobs: int
    uptime_s: float

class PropAccuracy(Contract):
    prop_id: str
    gt_length_mm: float
    gt_width_mm: float
    n: int
    mean_length_mm: float
    mean_width_mm: float
    length_error_pct: float              # signed, mean
    width_error_pct: float
    max_abs_error_pct: float
    ocr_correct_rate: float | None

class EvalReal(Contract):
    n_inspections: int
    n_props_seen: int
    length_mae_pct: float
    length_p95_pct: float
    width_mae_pct: float
    width_p95_pct: float
    within_1pct_rate: float              # share of inspections with both errors ≤ 1%
    ocr_accuracy: float | None           # OCR == QR, over inspections with QR
    ocr_n: int
    read_rate: float                     # share with any id
    props: list[PropAccuracy]

class SyntheticVariant(Contract):
    n: int
    length_mae_pct: float
    length_max_pct: float
    width_mae_pct: float
    width_max_pct: float
    ocr_accuracy: float | None

class SyntheticBench(Contract):
    n: int
    generated_at: float
    overall: SyntheticVariant
    variants: dict[str, SyntheticVariant]   # "clean", "dim", "bright", "gradient", "noise", "blur", "dust", "scale", "glare"
    defect_accuracy: float
    mean_process_ms: float

class EvalResponse(Contract):
    real: EvalReal | None
    synthetic: SyntheticBench | None

class ApiErrorBody(Contract):
    code: Literal["NOT_FOUND", "BAD_REQUEST", "MARKER_NOT_FOUND", "NO_OBJECT", "NOT_CALIBRATED",
                  "CAMERA_UNAVAILABLE", "INTERNAL"]
    message: str
    hint: str | None = None
```

Errors: every non-2xx (except FastAPI 422 validation errors) returns `{"detail": ApiErrorBody}`.

---

## 4. TypeScript contracts (`web/lib/types.ts`)

Mirror of §3. **All frontend types come from this file only.**

```typescript
export const STATUSES = ["Pass", "Rework", "Fail"] as const;
export type InspectionStatus = (typeof STATUSES)[number];
export type IdSource = "ocr" | "qr" | "none";
export type DefectType = "notch" | "taper" | "bulge" | "camber";
export type SourceType = "webcam" | "url" | "file" | "synthetic";
export type TriggerMode = "auto" | "stable" | "line";
export type AlertLevel = "Fail" | "Rework" | "System";
export type LogFileStatus = "ok" | "locked" | "error";
export type StreamView = "annotated" | "rectified" | "raw";
export type UnixSeconds = number;

export interface Spec {
  id: string; name: string;
  nominal_length_mm: number; nominal_width_mm: number; nominal_height_mm: number | null;
  tol_length_mm: number; tol_width_mm: number;
  cs_var_warn_pct: number; cs_var_fail_pct: number;
  notch_min_mm: number; camber_max_mm: number; taper_max_mm: number;
  id_template: string; min_area_factor: number; max_area_factor: number;
  active: boolean;
}
export type SpecUpsert = Omit<Spec, "active">;

export interface Override { billet_id: string | null; status: InspectionStatus | null; note: string; at: UnixSeconds; }

export interface Inspection {
  id: number; ts: string;
  billet_id: string | null; id_source: IdSource;
  ocr_text: string | null; ocr_confidence: number | null; ocr_agreement: number | null;
  qr_text: string | null; id_mismatch: boolean;
  length_mm: number; width_mm: number; height_mm: number | null;
  length_dev_mm: number; width_dev_mm: number;
  cs_var_pct: number; taper_mm: number; camber_mm: number;
  min_width_mm: number; max_width_mm: number; width_profile_mm: number[];
  defects: DefectType[];
  status: InspectionStatus; auto_status: InspectionStatus; reasons: string[];
  spec_id: string; n_samples: number; angle_deg: number; latency_ms: number;
  snapshot_url: string; source: SourceType; track_id: number;
  override: Override | null; created_at: UnixSeconds;
}
export interface InspectionPatch { billet_id?: string | null; status?: InspectionStatus | null; note: string; }
export interface InspectionList { items: Inspection[]; total: number; }
export interface InspectionFilters { status?: InspectionStatus; billet_id?: string; spec_id?: string; since?: string; limit?: number; offset?: number; }

export interface Alert {
  id: number; inspection_id: number | null; ts: string; level: AlertLevel;
  message: string; acknowledged: boolean; created_at: UnixSeconds;
}

export interface Roi { x0_mm: number; y0_mm: number; w_mm: number; h_mm: number; }
export interface VerifyRequest { known_length_mm: number; known_width_mm?: number; }
export interface VerifyResult {
  known_length_mm: number; measured_length_mm: number; length_error_pct: number;
  known_width_mm: number | null; measured_width_mm: number | null; width_error_pct: number | null;
  ok: boolean; at: UnixSeconds;
}
export interface CalibrationState {
  calibrated: boolean; has_background: boolean; has_intrinsics: boolean;
  marker_mm: number; image_px_per_mm: number | null; rect_px_per_mm: number;
  roi: Roi; reprojection_error_px: number | null; verify: VerifyResult | null;
  drift_mm: number | null; drift_ok: boolean; created_at: UnixSeconds | null;
}
export interface MarkerResult {
  found: boolean; marker_id: number; corners_px: number[][];
  image_px_per_mm: number; reprojection_error_px: number; calibration: CalibrationState;
}

export interface SourceRequest { type: SourceType; value: string; }
export interface SourceInfo { type: SourceType; value: string; frame_width: number | null; frame_height: number | null; }
export interface StationStatus {
  source: SourceInfo; camera_ok: boolean; calibrated: boolean; has_background: boolean;
  paused: boolean; trigger_mode: TriggerMode; active_spec: Spec;
  fps_capture: number; fps_process: number; log_status: LogFileStatus; ocr_ready: boolean;
}
export interface Health { ok: boolean; db: boolean; camera_ok: boolean; calibrated: boolean; ocr_ready: boolean; }

export interface Metrics {
  fps_capture: number; fps_process: number; process_ms_p50: number; process_ms_p95: number;
  latency_ms_p50: number | null; latency_ms_p95: number | null;
  inspections_total: number; by_status: Record<InspectionStatus, number>;
  throughput_per_min: number; ocr_read_rate: number | null;
  queue_depth: number; dropped_jobs: number; uptime_s: number;
}
export interface PropAccuracy {
  prop_id: string; gt_length_mm: number; gt_width_mm: number; n: number;
  mean_length_mm: number; mean_width_mm: number;
  length_error_pct: number; width_error_pct: number; max_abs_error_pct: number;
  ocr_correct_rate: number | null;
}
export interface EvalReal {
  n_inspections: number; n_props_seen: number;
  length_mae_pct: number; length_p95_pct: number; width_mae_pct: number; width_p95_pct: number;
  within_1pct_rate: number; ocr_accuracy: number | null; ocr_n: number; read_rate: number;
  props: PropAccuracy[];
}
export interface SyntheticVariant {
  n: number; length_mae_pct: number; length_max_pct: number;
  width_mae_pct: number; width_max_pct: number; ocr_accuracy: number | null;
}
export interface SyntheticBench {
  n: number; generated_at: UnixSeconds; overall: SyntheticVariant;
  variants: Record<string, SyntheticVariant>; defect_accuracy: number; mean_process_ms: number;
}
export interface EvalResponse { real: EvalReal | null; synthetic: SyntheticBench | null; }

export interface ApiErrorBody {
  code: "NOT_FOUND" | "BAD_REQUEST" | "MARKER_NOT_FOUND" | "NO_OBJECT" | "NOT_CALIBRATED" | "CAMERA_UNAVAILABLE" | "INTERNAL";
  message: string; hint: string | null;
}

// ── WebSocket messages (server → client) ─────────────
export interface StatsMessage {
  type: "stats"; fps_capture: number; fps_process: number; process_ms_p95: number;
  tracks: number; camera_ok: boolean; calibrated: boolean; paused: boolean;
  log_status: LogFileStatus; server_time: UnixSeconds;
}
export type WsMessage =
  | StatsMessage
  | { type: "inspection"; inspection: Inspection }
  | { type: "alert"; alert: Alert }
  | { type: "calibration"; calibration: CalibrationState }
  | { type: "status"; status: StationStatus };
```

`web/lib/types.ts` also exports `isWsMessage(x: unknown): x is WsMessage`. Unknown messages are ignored.

---

## 5. REST endpoints

Base `http://localhost:8000`. JSON unless noted.

| # | Method & path | Request | Response | Errors |
|---|---|---|---|---|
| 1 | `GET /health` | — | `Health` | — |
| 2 | `GET /status` | — | `StationStatus` | — |
| 3 | `GET /stream.mjpg` | `?view=annotated\|rectified\|raw` (default annotated) | `multipart/x-mixed-replace; boundary=frame`, ≤ 15 fps | — |
| 4 | `GET /snapshot.jpg` | `?view=` | `image/jpeg` | 503 `CAMERA_UNAVAILABLE` |
| 5 | `POST /source` | `SourceRequest` | `StationStatus` | 503 `CAMERA_UNAVAILABLE` (source could not open; previous source kept) |
| 6 | `POST /control/pause` · `POST /control/resume` | — | `StationStatus` | — |
| 7 | `POST /control/trigger-mode` | `TriggerModeRequest` | `StationStatus` | 422 |
| 8 | `GET /calibration` | — | `CalibrationState` | — |
| 9 | `POST /calibration/marker` | — | `MarkerResult` | 422 `MARKER_NOT_FOUND`, 503 |
| 10 | `POST /calibration/background` | — | `CalibrationState` | 409 `NOT_CALIBRATED` |
| 11 | `POST /calibration/verify` | `VerifyRequest` | `VerifyResult` | 409 `NOT_CALIBRATED`, 422 `NO_OBJECT` |
| 12 | `PUT /calibration/roi` | `Roi` | `CalibrationState` | 409, 422 |
| 13 | `DELETE /calibration` | — | `CalibrationState` (reset) | — |
| 14 | `GET /specs` · `POST /specs` · `PUT /specs/{id}` · `POST /specs/{id}/activate` | `SpecUpsert` for POST/PUT | `Spec[]` / `Spec` | 404, 409 duplicate id |
| 15 | `GET /inspections` | `status, billet_id, spec_id, since, limit (≤500, default 100), offset` | `InspectionList` (newest first) | — |
| 16 | `GET /inspections/{id}` | — | `Inspection` | 404 |
| 17 | `GET /inspections/{id}/snapshot.jpg` | — | `image/jpeg` | 404 |
| 18 | `PATCH /inspections/{id}` | `InspectionPatch` | `Inspection` | 404, 422 |
| 19 | `GET /alerts?limit=50` · `POST /alerts/{id}/ack` | — | `Alert[]` / `Alert` | 404 |
| 20 | `GET /export` | `format=xlsx\|csv\|json`, optional `status`, `since` | file download (`inspections_<yyyymmdd_hhmm>.<ext>`) | 422 |
| 21 | `GET /metrics` | — | `Metrics` | — |
| 22 | `GET /eval` | — | `EvalResponse` | — |
| 23 | `WS /ws` | — | `WsMessage` stream (stats at 1 Hz) | — |
| 24 | `GET /tts` (optional, T41) | `?inspection_id=` | `audio/mpeg` | 404 if disabled |

**CSV / Excel columns (in order):** `id, timestamp, billet_id, id_source, ocr_text, ocr_confidence, qr_text, id_mismatch, length_mm, width_mm, height_mm, length_dev_mm, width_dev_mm, cs_var_pct, taper_mm, camber_mm, defects, status, auto_status, reasons, spec_id, n_samples, latency_ms, override_note, snapshot`. Lists are joined with `"; "`. Numbers rounded to 2 dp.

**Excel workbook:** sheet `Inspections` (header bold, frozen first row, auto-filter, column widths set, `status` cell fill: Pass green `C6EFCE`, Rework amber `FFEB9C`, Fail red `FFC7CE`), sheet `Summary` (counts by status, active spec, time range, generated at).

---

## 6. Internal vision types (`backend/billetvision/vision/types.py`)

Frozen dataclasses unless noted. Arrays are `numpy.ndarray`.

```python
@dataclass(frozen=True)
class Calibration:
    h_img_to_bed: np.ndarray            # 3×3, image px (undistorted) → bed mm
    roi: Roi                            # pydantic Roi reused
    rect_px_per_mm: float
    image_px_per_mm: float
    camera_matrix: np.ndarray | None
    dist_coeffs: np.ndarray | None
    marker_corners_px: np.ndarray       # 4×2
    marker_mm: float
    image_size: tuple[int, int]         # (w, h)
    reprojection_error_px: float
    created_at: float

@dataclass(frozen=True)
class Detection:
    contour_px: np.ndarray              # rectified-image px, N×2
    center_mm: tuple[float, float]      # bed mm
    angle_deg: float                    # long axis vs +x, in (−90, 90]
    rough_length_mm: float
    rough_width_mm: float
    area_mm2: float
    full_inside: bool                   # ≥ EDGE_MARGIN_MM from every ROI border
    merged: bool                        # area > max_area_factor × nominal area

@dataclass(frozen=True)
class Measurement:
    length_mm: float
    width_mm: float
    width_profile_mm: tuple[float, ...] # 21 sub-pixel slice widths, NaN-free (failed slices interpolated)
    valid_slices: int
    dense_pos_mm: np.ndarray            # positions along the long axis (mask-based dense profile, SPEC §9.3)
    dense_top_mm: np.ndarray            # signed edge offsets from the long axis at each position
    dense_bottom_mm: np.ndarray
    sharpness: float                    # variance of Laplacian on the billet crop
    angle_deg: float

@dataclass(frozen=True)
class DefectResult:
    cs_var_pct: float
    taper_mm: float
    camber_mm: float
    min_width_mm: float
    max_width_mm: float
    defects: tuple[str, ...]            # DefectType values
    notch_depth_mm: float

@dataclass
class Track:                            # mutable, owned by the processing thread
    id: int
    center_mm: tuple[float, float]
    history: deque[tuple[float, tuple[float, float]]]   # (t_monotonic, center)
    missing: int
    samples: list[Measurement]
    crops: list[tuple[float, np.ndarray]]               # (sharpness, upright BGR crop)
    first_sample_t: float | None
    crossed_line: bool
    finalized: bool

@dataclass(frozen=True)
class FinalizeJob:
    track_id: int
    samples: tuple[Measurement, ...]
    crops: tuple[np.ndarray, ...]       # ≤ 3 sharpest upright crops (BGR)
    snapshot_jpeg: bytes                # annotated full frame at finalize time
    first_sample_t: float               # time.monotonic()
    source: str
    spec: Spec

@dataclass(frozen=True)
class IdResult:
    billet_id: str | None
    id_source: str                      # IdSource
    ocr_text: str | None
    ocr_confidence: float | None
    ocr_agreement: float | None
    qr_text: str | None
    id_mismatch: bool

@dataclass(frozen=True)
class Decision:
    status: str                         # InspectionStatus
    reasons: tuple[str, ...]
```

`data/props.csv` columns: `prop_id,length_mm,width_mm,thickness_mm,notes` (prop_id = the ID painted and encoded in its QR).
