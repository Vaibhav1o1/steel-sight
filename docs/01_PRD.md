# 01 — Product Requirements Document (PRD)

**Product:** BilletVision — non-contact billet inspection station
**Event:** Code Utsava X.0 (NIT Raipur), Problem Statement 1
**Build window:** Sat 3 Oct 2026 09:00 → Sun 4 Oct 2026 ~12:00 IST (judging until 15:30)
**Companion docs:** `02_TECH_STACK_AND_ARCHITECTURE.md`, `03_DATABASE_SCHEMA_AND_CONTRACTS.md`, `GEMINI.md` (agent rules), `05_IMPLEMENTATION_ROADMAP.md`, `SPEC.md` (algorithm reference)

---

## 1. Executive summary

In billet plants, operators still measure billets with tapes and calipers next to hot steel and copy heat numbers into registers by hand. It is slow, unsafe, error-prone, and records go missing, so off-spec billets travel downstream before anyone notices.

BilletVision is a **camera-based inspection station**. A fixed overhead camera watches billets on a conveyor or inspection bed. For every billet it:

1. Measures **length and width in millimetres** after calibration (target error ≤ ±1%).
2. Measures **cross-sectional variation** along the bar and detects **notches, taper, bulges and bends**.
3. Reads the **painted/stamped ID** (heat number) with OCR, and a **QR code** if present.
4. Decides **Pass / Rework / Fail** against the product specification, with reasons.
5. Appends a timestamped record to **SQLite, CSV and an Excel workbook**, without file locks or corruption.
6. Shows everything on a **live operator dashboard** with bounding boxes, measurements and instant alerts.

## 2. Core value proposition

> **Every billet measured, read and logged — without anyone touching hot steel.**

What makes it credible, not just an OpenCV demo:

| Claim | How we prove it on stage |
|---|---|
| ±1% dimensional accuracy | Live **accuracy panel**: every prop's measured value vs its vernier ground truth |
| OCR ≥ 90% | Props carry the painted ID **and** a QR code with the same ID; OCR accuracy = OCR result vs QR, computed live |
| Real-time | FPS and per-billet latency (trigger → logged) shown in the top bar |
| Robust | Lighting switched off/angled during the demo; readings hold |
| Excel without locks | The log workbook is open in Excel during the demo; logging never stops (SQLite + CSV continue, the workbook is rewritten as soon as Excel closes it), and a fresh export always contains every row |

## 3. Users

| Persona | Goal | Primary screen |
|---|---|---|
| **Line operator** | See each billet's result instantly and react to rejects | Live Station |
| **QC engineer** | Calibrate the station, set the spec, check accuracy | Calibration, Accuracy |
| **Shift supervisor / auditor** | Search, correct and export the inspection log | Inspection Log |
| **Hackathon judge** | Watch a bar go under the camera and get a logged result | Live Station |

## 4. Key user flows

### UF-1 Calibrate the station (once per setup)
1. Choose the camera source (USB webcam, phone camera URL, video file, or synthetic test feed).
2. Place the printed ArUco marker on its spacer and click **Detect marker** → the system shows pixels-per-mm and the inspection area.
3. Clear the bed and click **Capture background**.
4. Place a reference bar of known length, enter its length, click **Verify** → error % is shown (must be ≤ 1%).
5. Choose or edit the **active spec** (nominal length/width, tolerances, ID format).

### UF-2 Inspect billets (continuous)
1. A billet slides or is placed under the camera.
2. The live feed shows its outline, live length × width and a track id.
3. When the billet is fully inside the area and steady (or crosses the centre line), the system measures it over several frames, reads the ID and decides the status.
4. Result card appears: ID, L × W (mm), deviations, defects, status. A row is logged.
5. **Fail** → red alert with sound and spoken message. **Rework** → amber alert.

### UF-3 Review and export the log
1. Open **Inspection Log**: filter by status, spec, date; search by billet ID.
2. Open a record: snapshot, width profile chart, OCR vs QR, reasons.
3. Correct a misread ID or override a status (stored as an operator override with a note).
4. Export **Excel / CSV / JSON**.

### UF-4 Check accuracy
1. Open **Accuracy**: per-prop table (ground truth vs measured mean, error %, n), overall within-1% rate, OCR accuracy vs QR, read rate.
2. Synthetic benchmark results and live performance (FPS, latency p50/p95).

## 5. Mandatory capabilities

| ID | Capability | Acceptance |
|---|---|---|
| MC-01 | Camera sources: USB webcam (index), network camera / phone (URL), video file (loop), synthetic generator | Each source streams frames; switchable at runtime |
| MC-02 | Plane calibration with ArUco marker → image-to-bed homography; optional lens intrinsics | Verify step error ≤ 1% on a reference bar |
| MC-03 | Background capture and robust segmentation of billets on the bed | Synthetic tests pass under lighting/noise/dust variants |
| MC-04 | Sub-pixel length & width measurement in mm, aggregated over several frames | Synthetic: mean abs error ≤ 0.5%, max ≤ 1.0% |
| MC-05 | Width profile (21 slices), cross-section variation %, taper, camber, notch/bulge detection | Synthetic defect scenes classified correctly |
| MC-06 | Tracking + trigger (steady-in-area or centre-line crossing); exactly one inspection per billet | Synthetic video: count of inspections = count of billets |
| MC-07 | OCR of painted/stamped ID with format template, confusion fixes and multi-crop voting | Synthetic OCR ≥ 90% (target 95%); real OCR measured vs QR |
| MC-08 | QR decode; ID resolution and OCR/QR mismatch flag | Mismatch produces Rework with reason |
| MC-09 | Spec-based decision Pass / Rework / Fail with human-readable reasons | Unit tests per rule |
| MC-10 | Logging: SQLite (truth) → CSV append → Excel workbook via atomic replace; lock-tolerant | Rows never lost when the workbook is open in Excel |
| MC-11 | Live dashboard: annotated MJPEG feed, latest result, alerts (toast + beep + speech) | Visible < 2 s after trigger |
| MC-12 | Inspection log with filters, detail view, snapshot, operator override, exports (xlsx/csv/json) | Exports open in Excel |
| MC-13 | Accuracy evaluation: real props (vernier ground truth + QR) and synthetic benchmark | Accuracy page shows real computed numbers |
| MC-14 | Performance metrics: capture FPS, processing FPS, per-billet latency p50/p95, throughput | Shown live |
| MC-15 | Fully offline operation on one laptop | Works with Wi-Fi off after setup |

### Non-functional requirements

| Area | Requirement |
|---|---|
| Speed | Processing loop ≥ 15 FPS at 1080p on a laptop CPU; per-billet latency (first sample → logged) < 2 s |
| Accuracy | Length and width error ≤ ±1% after calibration (synthetic proven in tests; real reported honestly) |
| OCR | ≥ 90% on painted/printed IDs (synthetic proven; real reported vs QR) |
| Robustness | Variable lighting, dust specks, mild surface scale, glare spot |
| Data | No lost or corrupted rows; Excel open in parallel does not stop logging |
| Determinism | Synthetic generator and tests are seeded and stable |
| Honesty | No invented numbers. Missing data shows an explicit empty state |
| Display | Usable at 1280 px wide and above; light and dark themes; status shown by colour **and** text |

## 6. Explicit OUT OF SCOPE (do not build)

- Training custom detection models (YOLO etc.) or custom OCR models; GPU usage
- Hot-billet imaging (thermal/IR), real factory integration (PLC, OPC-UA, MES)
- Motorised conveyor control or hardware triggers
- 3D/stereo measurement. Height is optional via a second side camera only (optional task T40)
- Authentication, user accounts, roles, multi-station management
- Cloud deployment, Docker, message brokers
- Email/SMS/WhatsApp notifications
- Barcode formats other than QR
- Mobile layouts below 1280 px
- Any page not listed in UF-1 … UF-4

## 7. Edge cases & error-handling constraints

| # | Edge case | Required behaviour |
|---|---|---|
| E-01 | Camera not connected / source fails to open | `/status` shows `camera_ok=false`, dashboard shows a clear banner; pipeline retries every 2 s; API stays up |
| E-02 | Frames stop arriving mid-run | Detect after 1 s, mark `camera_ok=false`, reconnect automatically |
| E-03 | Not calibrated | Live feed still shows; measurements and logging are disabled; banner "Calibrate first" |
| E-04 | Marker not found during calibration | HTTP 422 `MARKER_NOT_FOUND` with hint (lighting, size, in view) |
| E-05 | Marker moves after calibration (camera bumped) | Periodic check (every 30 s if marker visible); drift > 1 mm → System alert "Recalibrate" |
| E-06 | Billet partly outside the inspection area | Tracked but never measured or logged until fully inside |
| E-07 | Two billets touching | If contour aspect/area is inconsistent with spec (> 1.5× nominal area), mark `merged` and do not log; System alert "Separate billets" |
| E-08 | Billet removed before enough samples | Finalize with available samples if ≥ 3; otherwise discard (no row) |
| E-09 | Same billet stays in view for minutes | Exactly one inspection per track |
| E-10 | OCR finds no valid ID | Try 180° rotation; then QR; else `billet_id = null`, status at least Rework, reason "ID unreadable" |
| E-11 | OCR and QR disagree | `id_mismatch=true`, Rework, reason with both values |
| E-12 | Upside-down text | Second OCR pass at 180° |
| E-13 | Excel file open/locked | SQLite and CSV continue; workbook write retried every 5 s; dashboard shows "Excel locked — retrying"; `/export` always works |
| E-14 | CSV locked (Windows) | Rows buffered in memory and flushed on next success; SQLite is the source of truth |
| E-15 | Sudden lighting change | Segmentation uses background difference + adaptive threshold; operator can re-capture background in one click |
| E-16 | Glare / specular spot on billet | Saturated pixels masked out of edge search |
| E-17 | Very small or huge contours (hands, shadows, cables) | Rejected by area and aspect limits from the active spec |
| E-18 | OCR model files missing | Startup check fails loudly with the exact command to download models; QR path still works |
| E-19 | Division by zero / NaN | Never leave the API; use guards |
| E-20 | Processing slower than capture | Process the latest frame only (drop stale frames); never build an unbounded queue |

## 8. Success criteria for the demo

1. A bar slides under the camera → outline, live L × W, then a logged result card within 2 s.
2. An undersized bar → red Fail alert with sound and spoken reason; a notched bar → Fail "notch".
3. The accuracy panel shows real error % vs vernier ground truth for every prop, and OCR accuracy vs QR.
4. With the log workbook open in Excel, inspections keep being logged without errors; closing Excel lets the workbook update; exports open cleanly.
5. Everything works with Wi-Fi off.
