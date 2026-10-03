# Decisions Log

| Date | Task | Decision | Reason |
|---|---|---|---|
| 2026-10-03 | T05 | Used React 19 `useSyncExternalStore` for client hydration and localStorage sync | Prevent cascading renders and satisfy `react-hooks/set-state-in-effect` without `as` casts |
| 2026-10-03 | T07 | Set `CameraSpec` defaults to `fov_mm=760.0`, `center_mm=(290.0, 0.0)` | Ensures both the ArUco marker at (0, 0) and the entire ROI [60, 660] mm are fully visible in the 1920×1080 frame |
| 2026-10-03 | T10 | In `_find_crossing`, restrict candidates to the expected half-plane (`side < 0` vs `side > 0`) within `search_margin_mm` | Prevents glare-corrupted edge searches from erroneously selecting the opposite edge's crossing; correctly marks slice failed for linear interpolation |
| 2026-10-03 | T12 | Conformed `_apply_effects` glare rendering to SPEC §5.1 ("saturated ellipse on one billet") by projecting billet center via `h_bed_to_img` and omitting glare on empty scenes (background capture) | Prevents arbitrary glare ellipses from falling on the dark matte bed which corrupted background-subtraction segmentation; aligns with physical reality that specular reflection occurs on billet top surfaces |
| 2026-10-03 | T13 | Included `A↔4` in digit/letter position fixes and mapped delimiters `_ . — – ~ / :` to `-` | Supports industrial OCR confusions like `H2A-1I87` → `H24-1187` specified in roadmap while keeping strict length and character-set checks |
| 2026-10-03 | T14 | rapidocr v2 returns `RapidOCROutput` with `.txts` and `.scores` tuple attributes (not iterable). Adapter in `ocr.py` checks `hasattr(result, "txts")` first, then falls back to legacy list-of-triples format. Logged per GEMINI.md §7. | Installed `rapidocr-onnxruntime` exposes new API; wrapping inside `ocr.py` only keeps all other modules unaware of the format. OCR accuracy=100%, QR=100% on 40/20 seeded crops. |
| 2026-10-03 | T15 | Nearest-centre tracker matches all tracks (active and finalized) to prevent duplicate tracks for resting billets (E-09); finalized tracks are purged immediately once missing > 0 so subsequent billets start a fresh track | Ensures exactly one inspection per billet while allowing consecutive billets to be placed at the same inspection station position without false track merging |
| 2026-10-03 | Adj A | Standardized canonical field name to `width_variation_pct` across all contracts, DB DDL, API, and UI, while retaining `cs_var_pct` as an accepted input alias | Guarantees strict contract conformance and backward compatibility across existing tests and schema definitions |
| 2026-10-03 | Adj B | Added joint multi-marker ($N \ge 4$) calibration with RMS residual and per-marker residuals, enforced measured marker side requirement, and restricted saving to residual $\le 1.5$ mm; single-marker mode flagged as `reduced-baseline` with warning | Extends calibration over full inspection baseline and guarantees physical caliper verification before saving |
| 2026-10-03 | Adj C | Added `Review` status to `InspectionStatus` and wired `calib_drift` to force `Review` status with reason and flag `CALIB_DRIFT` | Implements fail-safe directive: measurements taken during active calibration drift are never marked PASS |

## T19 - Camera Source
- Human check confirmed webcam capture at 1920x1080 @ 30.0 FPS (driver locks: auto_exposure=False, autofocus=False, auto_wb=False).


## T20 — Processing Pipeline (Resolved)

- **drift_mm signature**: Real API is `drift_mm(corners_current, corners_calib, image_px_per_mm)`, not `drift_mm(cal, corners)`. Adapted pipeline to unpack and pass all three args.
- **calibrate_from_marker**: Takes explicit kwargs (`marker_mm`, `rect_px_per_mm`, etc.), not a `cfg` object. Pipeline passes config constants directly.
- **build_rectifier import**: Lives in `vision.rectify`, not `vision.calibration`. Fixed import.
- **Tracker kwarg**: Uses `trigger_mode=`, not `mode=`.
- **detect_marker return**: Returns `(corners, refine_shift)` tuple; pipeline unpacks as `corners, _shift`.
- **PipelineSnapshot**: Added frozen dataclass to `state.py` for consistent per-frame reads under lock.
- **StatusSnapshot**: Added for stats publishing with real `camera_ok`, `calibrated`, `paused`, `log_status`.
- **RuntimeMetrics**: Added thread-safe `inc_dropped_jobs()`, `inc_errors()`, `dropped_jobs`, `errors`.
- **Worker system_alerts**: Added `system_alerts` queue drain to OcrWorkerThread; pipeline never touches DB.
- **Alert rate-limiting**: `_AlertGate` with 30s cooldown per key prevents alert spam.
- **glare_mask**: Returns `uint8` (0/255), not `bool_` — compatible with `measure()`'s optional glare param.
