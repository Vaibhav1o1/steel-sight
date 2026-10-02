# 05 — Atomic Implementation Roadmap

41 tasks. Feed them to Antigravity **one at a time** ("Do T07."). 👤 marks tasks that need a human at the camera.

## How to use

- Wait for **RESULT: PASS** before sending the next task.
- 3 failures on one task → read the agent's hypothesis, then send: `Investigate the failure in T07 only. Do not change tests, thresholds or contracts.`
- Every ~10 tasks start a **fresh Antigravity chat**: `Read GEMINI.md and the "How to use" section of docs/05_IMPLEMENTATION_ROADMAP.md. Same rules as before. Last completed task: T16. Do T17.`

## Tracks, checkpoints and the minimum viable stopping point

| Track | Tasks | Who / when |
|---|---|---|
| Backend vision | T01–T03, T06–T27 | Antigravity window 1, from 09:00 |
| Frontend | T04–T05 (after T01), T28–T33 (after T23) | Antigravity window 2 (separate git branch; merge after T27 and T33) |
| Physical rig | props, labels, marker, stand, lights | Human, from 09:00 (see `00_START_HERE.md`) |
| Real-world | T19 camera check 👤, T34–T37 👤 | Both, Saturday evening onwards |

| Checkpoint | After | Target (Sat 09:00 start) | Must work |
|---|---|---|---|
| CP1 | T12 | Sat ~14:30 | **Synthetic accuracy tests pass (≤ 1%)** |
| CP2 | T15 | Sat ~17:00 | OCR + tracking on synthetic video |
| CP3 | T27 | Sat ~22:00 | Backend end-to-end on the synthetic source: stream, inspections, Excel, WS |
| **MVSP** | T30 | **Sun ~00:30** | **Live page shows the annotated feed, result cards, alerts — on synthetic and on the real camera** |
| CP4 | T35 | Sun ~05:00 | Real props measured with reported accuracy |
| Freeze | T39 | **Sun 08:00** | Nothing new after this — rehearse |

After the MVSP, if short on time: T34 → T35 → T37 → T38, skip the rest.

---

# Phase A — Setup

### T01 — Repository scaffold
**Read:** `02` §3, §4.
**Do:** `git init`; create every directory of the `02` §3 tree plus `print/`; empty `__init__.py` where packages are shown; `.gitkeep` in `data/videos`, `data/calib`, `backend/data`, `backend/calibration`, `backend/logs`, `backend/snapshots`, `backend/reports`, `print/`. `.gitignore`: `.venv/`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `node_modules/`, `.next/`, `.env`, `backend/data/*`, `backend/calibration/*`, `backend/logs/*`, `backend/snapshots/*`, `backend/reports/*`, `data/videos/*`, `data/calib/*`, `print/*` (keep `.gitkeep`). `.env.example` per `02` §4. `data/props.csv` with header only (`prop_id,length_mm,width_mm,thickness_mm,notes`). `docs/decisions.md` with table header `| Date | Task | Decision | Reason |`; empty headed `assumptions.md`, `limitations.md`, `hardware_setup.md`, `demo_runbook.md`. Stub `README.md`.
**Done when:** `git status` lists the files; `find . -name "__init__.py" | wc -l` ≥ 8.

### T02 — Backend environment, config, enums
**Read:** `02` §1 (backend); `SPEC` §3; `03` §1.
**Do:** `backend/requirements.txt` (backend libraries in `02` §1, version floors as listed); `backend/pyproject.toml` (ruff: line 110, py311, select E,F,I,B,UP,NPY; pytest: `testpaths=["tests"]`, `pythonpath=["."]`, marker `perf`). Create `backend/.venv`, install. `billetvision/config.py` with every constant from `SPEC` §3 (typed, env overrides via python-dotenv, grouped, JSON for `ROI_DEFAULT`). `billetvision/enums.py` (`StrEnum`s from `03` §1). `tests/test_config.py`.
**Done when:** `make`-less check: `cd backend && .venv/bin/pytest -q && .venv/bin/ruff check .` pass; `.venv/bin/python -c "import cv2; print(cv2.__version__, hasattr(cv2.aruco,'ArucoDetector'))"` prints a version ≥ 4.8 and `True`.

### T03 — Makefile, OCR models, OCR smoke test
**Read:** `02` §4 (Makefile); `SPEC` §12.2.
**Do:** Root `Makefile` with all targets in `02` §4 plus `help`. `tools/ocr_smoke.py`: renders "H24-1187" with `cv2.putText` on a grey image, runs RapidOCR, prints text + score + elapsed ms (triggers the model download on first run). Run it now (online) so models are cached.
**Done when:** `make help` lists targets; `make ocr-smoke` prints `H24-1187` (or a string that normalises to it) with score; `make test` passes.

### T04 — Next.js scaffold
**Read:** `02` §1 (frontend); `GEMINI.md` §6.
**Do:** `npx create-next-app@latest web --ts --tailwind --eslint --app --src-dir=false --import-alias "@/*" --use-npm`; tighten `tsconfig.json`; `npx shadcn@latest init` + add the components listed in `02` §1; `npm i recharts lucide-react next-themes`; `.env.local.example` → `.env.local`; replace demo page with a "BilletVision" heading.
**Done when:** `cd web && npm run lint && npx tsc --noEmit && npm run build` pass.

### T05 — Frontend foundations
**Read:** `03` §4, §5; `GEMINI.md` §6; `SPEC` §19 (colours, TopBar).
**Do:** `lib/types.ts` (verbatim `03` §4 + `isWsMessage`); `lib/api.ts` (`ApiError` with `code`/`hint`; one typed function per endpoint in `03` §5 rows 1–2, 4–22; `streamUrl(view)`, `snapshotUrl(view)`, `exportUrl(format, filters)`, `inspectionSnapshotUrl(id)`); `lib/format.ts`; `lib/status.ts`; `app/layout.tsx` with ThemeProvider, placeholder `TopBar` (nav: Live, Log, Calibration, Accuracy) and sonner `Toaster`; `components/common/*`.
**Done when:** lint/tsc/build pass; `grep -rn ": any\|as any" web/lib web/components web/app` is empty.

---

# Phase B — Vision core (pure, synthetic-tested)

### T06 — Contracts and vision types
**Read:** `03` §3, §6.
**Do:** `billetvision/schemas.py` exactly as `03` §3; `vision/types.py` exactly as `03` §6. `tests/test_schemas.py`: round-trip `Inspection` JSON; extra fields rejected; `Spec` validation rejects non-positive values.
**Done when:** `make test` + ruff pass.

### T07 — Synthetic scene generator
**Read:** `SPEC` §5.1–§5.3.
**Do:** `vision/synth.py`: dataclasses, `render_scene`, `random_scene`, `GroundTruth`. `tests/test_synth.py`: determinism; marker corners in ground truth match a fresh `ArucoDetector` detection on the image within 0.5 px; each variant renders; images are 1920×1080 BGR uint8.
**Done when:** `make test` passes; save 3 sample images to `backend/reports/synth_samples/` (git-ignored) and list their paths.

### T08 — Calibration maths + printables
**Read:** `SPEC` §4.1–§4.3, §4.7, §4.8.
**Do:** `vision/calibration.py` (`detect_marker`, `calibrate_from_marker`, `load_intrinsics`, `drift_mm`, (de)serialisation). `tools/make_marker.py` (PNG at 300 DPI with exact `--mm` side + 10 mm white border + a 100 mm scale bar and printed text "Print at 100% — measure the bar"); `tools/make_labels.py` (for each prop id: a label PNG with the ID in large bold text and a QR code, sized for the prop width); `tools/make_checkerboard.py`; `tools/calibrate_intrinsics.py`. `tests/test_calibration.py` per `SPEC` §18.
**Done when:** `make test` passes; `make marker` and `make labels` (with 2 sample rows temporarily in a test CSV) produce files in `print/`.

### T09 — Rectification + segmentation
**Read:** `SPEC` §4.4, §7, §8.
**Do:** `vision/rectify.py` (`Rectifier`, `build_rectifier`, `apply`, `rect_to_image`, `glare_mask`), `vision/segment.py`. Tests in `test_segment_measure.py`: one detection per billet across all variants (with and without background); `full_inside` false for a billet crossing the ROI edge; `merged` true for two touching billets; hands-sized blobs rejected.
**Done when:** `make test` passes.

### T10 — Sub-pixel measurement
**Read:** `SPEC` §9.
**Do:** `vision/measure.py` (`measure(detection, rect_gray, rect_bgr, glare, cfg) -> Measurement` + upright crop). Tests: on clean scenes, length and width within 0.5% of truth; profile has 21 values; failed-slice interpolation works when a glare spot covers one slice.
**Done when:** `make test` passes.

### T11 — Defects + decision
**Read:** `SPEC` §10, §13.
**Do:** `vision/defects.py`, `vision/decide.py`. `tests/test_defects_decide.py` per `SPEC` §18 (defect scenes from `random_scene` with forced defects; every decision rule with crafted inputs; reasons contain numbers).
**Done when:** `make test` passes.

### T12 — Synthetic accuracy suite (core proof)
**Read:** `SPEC` §18 (`test_accuracy_synthetic.py`), §5.3.
**Do:** `tests/test_accuracy_synthetic.py`: 60 seeded scenes across all 9 variants → calibrate from the rendered marker → rectify → background from the same scene without billets → segment → measure; assert MAE ≤ 0.5% and max ≤ 1.0% for length and width; print a per-variant table. If it fails, tune **only** `config.py` constants (log in `decisions.md`).
**Done when:** passes 3 runs in a row; paste the per-variant table. **Checkpoint CP1.**

### T13 — ID template parsing and voting
**Read:** `SPEC` §12.1, §12.3, §12.5.
**Do:** `vision/idparse.py` (`normalize`, `vote`, `resolve_id`). `tests/test_idparse.py` (≥ 20 table cases incl. `H24 1187`, `H2A-1I87`→`H24-1187`, `0`↔`O` by position, missing hyphen, wrong length → None; vote tie-break; mismatch flag).
**Done when:** `make test` passes.

### T14 — OCR adapter + QR
**Read:** `SPEC` §12.2, §12.4; `03` §6 (`IdResult`).
**Do:** `vision/ocr.py` (`OcrEngine` lazy singleton, preprocessing, result-format adapter, `ready()`), `vision/qr.py`, a pure `read_id(crops, ocr_fn, qr_fn, template) -> IdResult` in `idparse.py`. `tests/test_ocr_qr.py` per `SPEC` §18 (skip with message if models missing).
**Done when:** `make test` passes; paste the measured OCR accuracy and QR rate.

### T15 — Tracker, triggers, aggregation
**Read:** `SPEC` §5.4, §11.
**Do:** `render_video` in `synth.py`; `vision/track.py` (`Tracker`, trigger modes, finalize rules, aggregation). `tools/gen_synth_video.py`. `tests/test_track.py` (station + conveyor videos: inspections == billets, no duplicates, dims within 1%; all three trigger modes).
**Done when:** `make test` passes; `make synth-video` writes `data/videos/synth_demo.mp4` + JSON. **Checkpoint CP2.**

---

# Phase C — Data and logging

### T16 — Database
**Read:** `03` §2.
**Do:** `billetvision/db.py` (engine with WAL pragmas, Table objects, indexes, `init_db` + seed default spec, `meta_get/meta_set`), `schema_reference.sql`. Tests in `test_db_logging.py`: tables created; default spec active; exactly one active spec after activating another.
**Done when:** `make test` passes.

### T17 — Logging (SQLite → CSV → Excel) with lock tolerance
**Read:** `SPEC` §14; `03` §5 (columns, workbook format).
**Do:** `billetvision/logging_io.py`: `log_inspection(...)`, CSV appender with pending buffer, `ExcelWriter` (debounce, temp + `os.replace`, retry, status callback), `build_workbook(rows) -> bytes`, `build_csv`, `build_json`. `repository.py`: `list_inspections(filters)`, `get_inspection`, `insert_inspection`, `apply_override`, alerts insert/list/ack. Tests per `SPEC` §18 (`test_db_logging.py`), including simulated `PermissionError`.
**Done when:** `make test` passes; open a generated `logs/inspections.xlsx` from a test run and confirm formatting (describe it).

### T18 — Evaluation computations
**Read:** `SPEC` §17; `03` §3 (`EvalReal`, `SyntheticBench`).
**Do:** `billetvision/evaluation.py` (pure functions over inspection rows + props table → `EvalReal`); `tools/bench_synthetic.py` → `reports/bench_synthetic.json`. Tests: crafted rows produce the expected MAE/p95/within-1% and OCR accuracy; missing props → `None`.
**Done when:** `make test` passes; `make bench` writes the JSON; paste the overall line.

---

# Phase D — Runtime

### T19 — Sources + capture thread 👤
**Read:** `SPEC` §6; `02` §2 (threads).
**Do:** `runtime/sources.py` (four sources, capture thread, reconnect), `runtime/state.py` (`LatestFrame`, `LatestJpeg`, locks). `tools/record_video.py`. Tests for synthetic and file sources (frame size, pacing ±20%, rewind).
**Human check:** connect the webcam or phone camera; run `python -m tools.record_video --seconds 5 --out ../data/videos/check.mp4` with the chosen source; report the printed resolution and fps.
**Done when:** `make test` passes; the human confirms ≥ 1080p at ≥ 20 fps (or reports what they got → log in `decisions.md`).

### T20 — Processing pipeline + OCR worker + events + metrics
**Read:** `SPEC` §15; `02` §2.
**Do:** `runtime/pipeline.py`, `runtime/worker.py`, `runtime/events.py`, `runtime/metrics.py`, synthetic auto-calibration (`SPEC` §6). `tests/test_pipeline.py` per `SPEC` §18 (run without the API: start threads on the synthetic source, collect events for ~6 s, assert inspections logged, latency < 2000 ms, perf).
**Done when:** `make test` passes; paste fps, process_ms p95 and latencies.

### T21 — Overlay renderer
**Read:** `SPEC` §15 step 4.
**Do:** `vision/overlay.py` (pure drawing functions on copies). Wire into the pipeline. Test: overlay output has the same shape as input and differs in the ROI area. Save one annotated frame to `reports/overlay_sample.jpg`.
**Done when:** `make test` passes; describe the sample image (what is drawn where).

---

# Phase E — API

### T22 — API skeleton, lifespan, status, WebSocket
**Read:** `SPEC` §16; `03` §3 (`Health`, `StationStatus`, `ApiErrorBody`), §5 rows 1, 2, 23.
**Do:** `api/main.py` (lifespan starts/stops runtime), `api/errors.py`, `api/ws.py`, `api/deps.py`, `routes/status.py` (`/health`, `/status`, `/ws` with 1 Hz stats). `scripts/ws_probe.py`.
**Done when:** `make api` starts on the synthetic source; `curl localhost:8000/health` → ok; `make probe` prints `stats` every second and `inspection` messages within 10 s.

### T23 — MJPEG stream and snapshots
**Read:** `SPEC` §16 (stream); `03` §5 rows 3–4.
**Do:** `routes/stream.py`.
**Done when:** `http://localhost:8000/stream.mjpg` plays in a browser with overlays (describe), `?view=rectified` works, `curl -o s.jpg localhost:8000/snapshot.jpg` gives a valid JPEG; CPU does not spike when no client is connected.

### T24 — Calibration endpoints
**Read:** `SPEC` §4.5–§4.8, §16; `03` §5 rows 8–13.
**Do:** `routes/calibration.py`. API tests on the synthetic source: marker → calibrated; background → has_background; verify with the synthetic billet's true length → ok; ROI update invalidates background; delete resets.
**Done when:** `make test` passes.

### T25 — Source, control and spec endpoints
**Read:** `03` §5 rows 5–7, 14.
**Do:** `routes/control.py`, `routes/specs.py`; broadcast `status` on changes. API tests: switch to a missing file → 503 and old source kept; pause/resume; trigger mode; spec create/update/activate; duplicate id → 409.
**Done when:** `make test` passes.

### T26 — Inspections, alerts, override, export
**Read:** `03` §5 rows 15–20; `SPEC` §14 (override).
**Do:** `routes/inspections.py`, `routes/export.py`. API tests: list with filters/pagination; snapshot served; PATCH override keeps `auto_status`; exports in 3 formats with correct headers and column order.
**Done when:** `make test` passes; downloaded xlsx opens in Excel/LibreOffice (describe).

### T27 — Metrics, evaluation endpoint, end-to-end check
**Read:** `03` §5 rows 21–22; `SPEC` §17.
**Do:** `routes/status.py` (`/metrics`), `routes/evaluation.py`. Then run the full backend on the synthetic source for 2 minutes.
**Done when:** `make test` passes; paste `/metrics` and `/eval` JSON; `logs/inspections.xlsx` and `.csv` contain the same row count as `/inspections` total. **Checkpoint CP3.**

---

# Phase F — Dashboard

### T28 — Live provider, top bar, banners, alert center
**Read:** `SPEC` §19 (LiveProvider, TopBar, SystemBanner, AlertCenter); `03` §4 (WS).
**Do:** `lib/live.tsx`, `components/layout/*`, wire into `layout.tsx`.
**Done when:** lint/tsc/build pass; with `make dev` on the synthetic source: chips update every second; Fail inspections produce red toasts + beeps + speech; mute works.

### T29 — Live feed + latest result card
**Read:** `SPEC` §19 (Live).
**Do:** `LiveFeed`, `LatestResultCard`, `components/views/LiveView.tsx`, `app/page.tsx`.
**Done when:** lint/tsc/build pass; feed plays; each new inspection updates the card within 1 s of the WS message.

### T30 — Recent strip + station controls 👤
**Read:** `SPEC` §19 (Live); `03` §5 rows 5–7, 10.
**Do:** `RecentStrip`, `StationControls`; add to `LiveView`.
**Human check:** switch the source to the real camera from the UI; see the live feed (not calibrated banner shown).
**Done when:** lint/tsc/build pass; synthetic flow fully works from the UI; real camera feed visible. **MVSP.**

### T31 — Calibration wizard 👤
**Read:** `SPEC` §4, §19 (Calibration); `03` §5 rows 8–14.
**Do:** `components/calibration/*`, `CalibrationView`, `app/calibration/page.tsx`.
**Human check:** with the real camera: detect marker (report px/mm), capture background, verify with a reference prop (report error %).
**Done when:** lint/tsc/build pass; human reports the numbers; logged in `decisions.md`.

### T32 — Inspection log page
**Read:** `SPEC` §19 (Log); `03` §5 rows 15–20.
**Do:** `components/log/*`, `LogView`, `app/log/page.tsx`.
**Done when:** lint/tsc/build pass; filters, pagination, detail dialog with width-profile chart, override and exports work.

### T33 — Accuracy page
**Read:** `SPEC` §17, §19 (Accuracy); `03` §4 (eval types).
**Do:** `components/accuracy/*`, `AccuracyView`, `app/accuracy/page.tsx`.
**Done when:** lint/tsc/build pass; synthetic bench card shows real JSON numbers; real section shows the empty state until props are inspected.

---

# Phase G — Real world

### T34 — Real camera bring-up and tuning 👤
**Read:** `02` §5; `SPEC` §3, §4, §8; PRD E-15, E-16.
**Do:** Write `docs/hardware_setup.md` (stand height, FOV, lighting, marker on spacer, background cloth, phone camera URL tips, Windows DirectShow note). Guide the human through: mount → calibrate → background → place each prop. Tune only `config.py` segmentation constants if detections fail (log every change). Record a 60 s real video with `make record` for regression and as backup.
**Done when:** every prop is detected as one full_inside detection; verify error ≤ 1% on the reference prop; `data/videos/real_demo.mp4` exists.

### T35 — Real accuracy run 👤
**Read:** `SPEC` §17.1.
**Do:** Human fills `data/props.csv` from vernier measurements and runs each prop under the camera 5 times. Agent checks `/eval` and the Accuracy page; investigates any prop with error > 1% (lighting, label edge, segmentation) and fixes within the rules.
**Done when:** paste `/eval.real` summary (MAE, p95, within-1% rate, OCR accuracy vs QR). **Checkpoint CP4.**

### T36 — Robustness pass 👤
**Read:** PRD E-01, E-02, E-05, E-13, E-15, E-16, E-20.
**Do:** Exercise each: unplug camera → banner + auto-reconnect; bump marker → drift alert; open `logs/inspections.xlsx` in Excel → "Excel locked" then recovers; lamp off → readings hold (or re-capture background); glare → no false edges. Fix only what breaks.
**Done when:** a table of the 6 checks with pass/fail and notes in `decisions.md`.

### T37 — Demo dry run + runbook 👤
**Read:** `SPEC` §20; PRD §8.
**Do:** Run the 60-second demo 3 times. Fix only bugs. Write `docs/demo_runbook.md`: physical setup checklist, startup commands, exact demo steps, what to say, fallback (switch source to `data/videos/real_demo.mp4` if the camera fails).
**Done when:** 3 clean runs; runbook written.

---

# Phase H — Polish (feature freeze Sun 08:00)

### T38 — Documentation
**Do:** `README.md` (overview, architecture mermaid from `02` §2, setup ≤ 6 commands, hardware summary, demo steps, accuracy tables filled from `/eval` and `reports/bench_synthetic.json` — real numbers only), `docs/assumptions.md`, `docs/limitations.md` (top-down camera → no height without side camera; painted/printed labels not hot stamped; cold props not hot billets; ±1% depends on rigid mount and marker at top-face height; OCR model is general-purpose), sample exports in `docs/samples/`.
**Done when:** a teammate follows the README on a fresh clone and reaches the Live page.

### T39 — Reliability soak
**Do:** Run on the recorded real video (file source) for 30 minutes plus 5 minutes on the live camera. Check: no thread deaths, memory stable, queue never saturates, inspections == billets passed, Excel and CSV row counts match the DB. Fix only what breaks.
**Done when:** results noted in `decisions.md`. **Feature freeze.**

---

# Phase I — Optional (only if T01–T39 pass)

### T40 — Height via side camera
Second source + its own marker on a vertical plane; measure height from the side silhouette; fill `height_mm`; add to decision if `nominal_height_mm` set. Must not change any existing contract except filling `height_mm`.

### T41 — ElevenLabs voice alerts
`billetvision/tts.py` + `GET /tts?inspection_id=` (cached MP3 per message, 5 s timeout, 404 when disabled). AlertCenter uses it when `TTS_ENABLED`, else browser speech.
