# SPEC — BilletVision Algorithm & Behaviour Reference

How things work: geometry, synthetic data, vision pipeline, ID reading, decisions, logging, API behaviour, evaluation, tests, UI behaviour. Names and shapes live in `03_DATABASE_SCHEMA_AND_CONTRACTS.md` (it wins on naming conflicts). Section numbers are referenced by the roadmap — do not renumber.

---

## 1. Purpose

Measure billets (length, width, cross-section variation, defects) in mm from a fixed overhead camera, read their ID, decide Pass/Rework/Fail against the active spec, log every result to SQLite/CSV/Excel, and show it live. Everything must be testable **without a camera** using the seeded synthetic generator (§5).

## 2. Processes and threads

One backend process (FastAPI + 4 threads: capture, processing, ocr-worker, excel-writer) and the Next.js dashboard. See `02` §2.

## 3. Constants (`backend/billetvision/config.py`)

All overridable via env var of the same name. Group with comments exactly as below.

**Camera**

| Name | Default | Meaning |
|---|---|---|
| `SEED` | `42` | Master seed |
| `SOURCE_TYPE`, `SOURCE_VALUE` | `synthetic`, `""` | Startup source |
| `FRAME_WIDTH`, `FRAME_HEIGHT` | `1920`, `1080` | Requested capture size |
| `CAPTURE_FPS` | `30` | Requested / synthetic & file playback rate |
| `RECONNECT_S` | `2.0` | Retry interval when a source fails |
| `STALE_FRAME_S` | `1.0` | No new frame for this long → `camera_ok=false` |

**Calibration & geometry**

| Name | Default | Meaning |
|---|---|---|
| `ARUCO_DICT` | `DICT_4X4_50` | Marker dictionary |
| `MARKER_ID` | `0` | |
| `MARKER_MM` | `80.0` | Printed marker side (black square), mm |
| `RECT_PX_PER_MM` | `3.0` | Rectified image resolution |
| `ROI_DEFAULT` | `{x0_mm: 60, y0_mm: -170, w_mm: 600, h_mm: 340}` | Inspection area in bed mm (marker sits left of it) |
| `MIN_IMAGE_PX_PER_MM` | `2.5` | Below → calibration warning "camera too far / resolution too low" |
| `BACKGROUND_FRAMES` | `15` | Median of N frames for the background |
| `DRIFT_CHECK_S` | `30` | Marker drift check interval |
| `DRIFT_MAX_MM` | `1.0` | Above → System alert "Recalibrate" |

**Segmentation**

| Name | Default |
|---|---|
| `SEG_BLUR_SIGMA` | `1.5` |
| `DIFF_MIN` | `25` (grey levels; floor for the Otsu threshold on the difference image) |
| `CLOSE_KERNEL_MM`, `OPEN_KERNEL_MM` | `4.0`, `2.0` |
| `EDGE_MARGIN_MM` | `5.0` |
| `MIN_ASPECT` | `1.5` |
| `SATURATION_LEVEL` | `250` (glare mask) |

**Measurement & defects**

| Name | Default |
|---|---|
| `N_SLICES` | `21` |
| `SLICE_SPAN` | `0.9` (fraction of length covered by slices) |
| `SAMPLE_STEP_PX` | `0.25` |
| `SEARCH_MARGIN_MM` | `8.0` |
| `MEASURE_BLUR_SIGMA` | `1.0` |
| `END_EXCLUDE_MM` | `10.0` (ignored at each end for dense-profile defects) |
| `DEFECT_MIN_SPAN_MM` | `3.0` |

**Tracking & triggers**

| Name | Default |
|---|---|
| `TRIGGER_MODE` | `auto` |
| `TRACK_MATCH_MM` | `60.0` |
| `TRACK_MAX_MISSING` | `8` frames |
| `STABLE_FRAMES`, `STABLE_MM` | `6`, `2.0` |
| `SAMPLES_TARGET`, `SAMPLES_MIN` | `7`, `3` |
| `LINE_WINDOW_MM` | `40.0` (half-width of the centre-line window) |
| `SAMPLE_TIMEOUT_S` | `3.0` |
| `OCR_CROPS` | `3` |
| `CROP_PAD_MM` | `4.0` |

**OCR**

| Name | Default |
|---|---|
| `OCR_MIN_SCORE` | `0.5` |
| `OCR_UPSCALE` | `1.5` |

**Runtime & logging**

| Name | Default |
|---|---|
| `STREAM_FPS` | `15` |
| `JPEG_QUALITY` | `80` |
| `JOB_QUEUE_SIZE` | `8` |
| `EXCEL_DEBOUNCE_S`, `EXCEL_RETRY_S` | `2.0`, `5.0` |
| `EXCEL_MAX_ROWS` | `20000` |
| `STATS_INTERVAL_S` | `1.0` |
| `DATABASE_URL` | `sqlite:///./data/billetvision.db` |
| `LOG_DIR`, `SNAPSHOT_DIR`, `CALIB_DIR`, `REPORT_DIR` | `logs`, `snapshots`, `calibration`, `reports` (relative to `backend/`) |
| `PROPS_CSV` | `../data/props.csv` |
| `TTS_ENABLED` | `false` |

## 4. Geometry and calibration (`vision/calibration.py`, `vision/rectify.py`)

### 4.1 Frames
- **Image**: camera pixels (after optional undistortion).
- **Bed**: mm on the plane of the billet tops. Origin = marker centre; +x along the marker top edge (corner 0 → 1); +y along corner 0 → 3.
- **Rect**: rectified image of the ROI. `u = (x − roi.x0_mm) · RECT_PX_PER_MM`, `v = (y − roi.y0_mm) · RECT_PX_PER_MM`. Size `ceil(w_mm·r) × ceil(h_mm·r)`.

### 4.2 Marker → homography
`detect_marker(gray) -> np.ndarray | None` uses `cv2.aruco.ArucoDetector(getPredefinedDictionary(DICT_4X4_50), DetectorParameters())`; refine corners with `cv2.cornerSubPix` (win 5×5). Bed coordinates of the corners: `(−m/2,−m/2), (m/2,−m/2), (m/2,m/2), (−m/2,m/2)` with `m = MARKER_MM`. `h_img_to_bed = cv2.getPerspectiveTransform(corners_px, corners_mm)`.
- `image_px_per_mm` = mean marker side length in px / `MARKER_MM`.
- `reprojection_error_px` = mean distance between detected corners and corners re-projected with the inverse homography (≈ 0 for 4 points; also report the corner refinement shift).
- Because only 4 points are used, accuracy depends on marker size and flatness; `MIN_IMAGE_PX_PER_MM` warning protects resolution.
- **Parallax rule:** the marker must sit at billet-top height (on a spacer). Documented in `docs/hardware_setup.md`; not corrected in software.

### 4.3 Intrinsics (optional)
`tools/calibrate_intrinsics.py` with a 9×6 inner-corner checkerboard (square 25 mm) from `data/calib/*.jpg` → `calibration/intrinsics.json` (`camera_matrix`, `dist_coeffs`, `rms`). If present, frames are undistorted before marker detection and rectification. If absent, assume zero distortion and set `has_intrinsics=false`.

### 4.4 Rectification
`build_rectifier(cal) -> Rectifier` precomputes:
- Without intrinsics: `M = S · T · H` (3×3) and uses `cv2.warpPerspective(frame, M, size, flags=INTER_LINEAR)`.
- With intrinsics: one pair of float32 `remap` maps from rect px → distorted image px (rect → bed → undistorted image via `H⁻¹` → distorted via `cv2.projectPoints`-equivalent maths), used with `cv2.remap`. One remap per frame.
- `rect_to_image(points_px) -> np.ndarray` for drawing overlays on the raw frame.

### 4.5 Background
`capture_background(frames) -> np.ndarray` = per-pixel median of `BACKGROUND_FRAMES` rectified greyscale frames, saved to `calibration/background.png`. Background is invalidated when calibration or ROI changes.

### 4.6 Verify
Measure the single largest detection with §9 over 7 frames (median). `error_pct = (measured − known)/known·100`. `ok = |length_error_pct| ≤ 1 and (width not given or |width_error_pct| ≤ 1)`.

### 4.7 Drift
Every `DRIFT_CHECK_S`, if the marker is detected: `drift_mm` = mean corner distance (current vs calibration) / `image_px_per_mm`. `drift_ok = drift_mm ≤ DRIFT_MAX_MM`. On transition to not ok → one System alert.

### 4.8 Persistence
`calibration/calibration.json` (homography, roi, marker info, verify result, created_at) + `meta.calibration` JSON. Loaded at startup.

## 5. Synthetic generator (`vision/synth.py`, pure, seeded)

Purpose: deterministic images and videos with exact ground truth so every vision component is tested without a camera.

### 5.1 Scene model
```python
@dataclass(frozen=True)
class BilletSpec:
    center_mm: tuple[float, float]; angle_deg: float
    length_mm: float; width_mm: float
    id_text: str | None; qr: bool
    defect: Literal["notch", "taper", "bulge", "camber"] | None
    defect_size_mm: float          # notch depth / taper delta / bulge height / camber offset

@dataclass(frozen=True)
class Effects:
    brightness: float = 1.0        # global gain
    gradient: float = 0.0          # 0..0.4 left→right illumination fall-off
    noise_sigma: float = 2.0
    blur_sigma: float = 0.0
    dust: int = 0                  # bright/dark specks
    scale: int = 0                 # dark blotches on billet tops
    glare: bool = False            # saturated ellipse on one billet
    jpeg_quality: int = 90

@dataclass(frozen=True)
class CameraSpec:
    image_size: tuple[int, int] = (1920, 1080)
    fov_mm: float = 650.0          # bed width visible across the image
    yaw_deg: float = 0.0           # rotation about the optical axis
    keystone: float = 0.0          # 0..0.04 perspective
    center_mm: tuple[float, float] = (330.0, 0.0)

@dataclass(frozen=True)
class SceneSpec:
    billets: tuple[BilletSpec, ...]; camera: CameraSpec; effects: Effects; with_marker: bool = True
```

### 5.2 Rendering (`render_scene(spec, rng) -> tuple[np.ndarray, GroundTruth]`)
1. Bed canvas at `SYN_PX_PER_MM = 6` covering x ∈ [−100, 760], y ∈ [−250, 250] mm: matte dark (grey 28, texture σ 4, slightly smoothed).
2. Marker: `cv2.aruco.generateImageMarker(dict, 0, side_px)` centred at bed origin, white 10 mm border.
3. Each billet drawn in its own local canvas (length × width + defect), then placed with an affine transform: top surface grey 150–185 with low-frequency texture; defects: notch = rectangular bite `defect_size × 15 mm` from one long edge at 40–60% length; taper = trapezoid (width changes by `defect_size` end to end); bulge = local +`defect_size` over 30 mm; camber = centre-line bowed by `defect_size` (polygon of 40 segments).
4. ID text: `cv2.putText` `FONT_HERSHEY_DUPLEX`, char height ≈ 0.28 × width, thickness ∝ height, colour white or yellow paint, centred at 35% of length. QR (if `qr`): `cv2.QRCodeEncoder.create().encode(id)`, 35 mm square with white quiet zone, at 80% of length.
5. Warp bed canvas to the camera image with `H_bed_to_img` built from `CameraSpec` (scale = image width / fov, yaw, keystone, centre).
6. Effects in order: brightness, gradient, scale blotches (applied before warp), dust, glare, Gaussian noise, Gaussian blur, JPEG round-trip.
7. `GroundTruth`: `h_bed_to_img`, marker corners px, list of billets with true length/width/angle/id/defect, `image_px_per_mm`.

### 5.3 Random scenes
`random_scene(rng, variant: str) -> SceneSpec`; variants: `clean, dim (0.6), bright (1.35), gradient (0.35), noise (σ 7), blur (σ 1.2), dust (60), scale (8 blotches), glare`. 1–2 billets, L ∈ U(300, 550), W ∈ U(80, 120), angle ∈ U(−25, 25), fully inside the default ROI with ≥ 20 mm clearance, IDs random from template `A99-9999`, QR 50%, defect 30% (size: notch 6–10, taper 6–10, bulge 6–10, camber 6–10 mm).

### 5.4 Videos
`render_video(rng, mode: Literal["conveyor","station"], n_billets, fps=30) -> Iterator[tuple[np.ndarray, list[GroundTruthBillet]]]`:
- conveyor: billets enter from the left at 150 mm/s with 200 mm gaps, constant angle U(−5, 5).
- station: each billet appears, rests 1.5 s, disappears; 0.5 s empty between.
`tools/gen_synth_video.py` writes MP4 (`mp4v`) + a JSON sidecar with ground truth.

## 6. Sources and capture (`runtime/sources.py`)

`FrameSource` protocol: `open() -> bool`, `read() -> np.ndarray | None`, `close()`, `info() -> SourceInfo`.
- **webcam**: `cv2.VideoCapture(int(value), cv2.CAP_DSHOW` on Windows else default), set `FOURCC MJPG`, width/height, fps.
- **url**: `cv2.VideoCapture(value)` (MJPEG/RTSP, e.g. phone IP Webcam `http://<ip>:8080/video`).
- **file**: loops at `CAPTURE_FPS` (sleep-paced); end → rewind.
- **synthetic**: `render_video(..., mode="station")` looped forever, paced at `CAPTURE_FPS`. It also exposes `empty_frame()` (same camera, no billets). When the synthetic source starts and no calibration exists, the pipeline auto-calibrates from the marker in `empty_frame()` and auto-captures the background from it, so the whole system runs out of the box without a camera. Calibration made this way is flagged `synthetic` in `meta.calibration` and discarded when a real source is selected.
Capture thread writes into `LatestFrame` (frame, index, t_monotonic). Failure → close, wait `RECONNECT_S`, reopen; never raises out of the thread. Switching source (`POST /source`) opens the new source first; on failure keeps the old one and returns 503.

## 7. Rectify (`vision/rectify.py`)
Per frame: `rect_bgr = rectifier.apply(frame)`; `rect_gray` = grey of it. Glare mask: `rect_gray ≥ SATURATION_LEVEL` dilated by 3 px.

## 8. Segmentation (`vision/segment.py`)
`segment(rect_gray, background | None, spec, cfg) -> list[Detection]`:
1. Blur `rect_gray` with `SEG_BLUR_SIGMA`.
2. With background: `diff = |gray − background|`; threshold `t = max(otsu(diff), DIFF_MIN)`. Without background: Otsu on CLAHE(gray) assuming billets brighter than the bed (auto-invert if the mean border intensity is brighter than the centre).
3. Morphology: close (`CLOSE_KERNEL_MM`), open (`OPEN_KERNEL_MM`), fill holes (contour fill).
4. External contours; for each: `minAreaRect` in rect px → mm. Keep if `area_mm2 ∈ [min_area_factor, max_area_factor·1.5] × nominal area` and aspect ≥ `MIN_ASPECT`. `merged = area_mm2 > max_area_factor × nominal area`.
5. `full_inside` = all contour points ≥ `EDGE_MARGIN_MM` from every ROI border.
6. `angle_deg` normalised so the long axis angle ∈ (−90, 90].

## 9. Measurement (`vision/measure.py`) — sub-pixel profiles

Input: `rect_gray` (blurred with `MEASURE_BLUR_SIGMA`), the detection, glare mask.
1. From `minAreaRect`: centre `c`, long-axis unit `u`, short-axis unit `v`, rough `L`, `W` (px).
2. Intensities: `I_fg` = median inside the (eroded) mask; `I_bg` = median in a ring 3–8 mm outside. Level `ℓ = (I_fg + I_bg)/2`. Polarity from the sign of `I_fg − I_bg`.
3. **Width slices:** for k = 0…`N_SLICES`−1 at `s_k = (−SLICE_SPAN/2 + k·SLICE_SPAN/(N−1))·L` along `u`, sample the line `c + s_k·u + t·v`, `t ∈ [−(W/2 + m), W/2 + m]` (`m = SEARCH_MARGIN_MM·r`) at `SAMPLE_STEP_PX` with bilinear sampling (`cv2.remap` on all slices at once). Find the outermost crossings of `ℓ` on each side, nearest to the rough edges, with linear interpolation between samples → `t_left`, `t_right`. Skip samples inside the glare mask. `width_k = (t_right − t_left)/r` mm. Failed slices → NaN, then linearly interpolated; `valid_slices` = count of non-failed.
4. **Length:** same crossing search along three lines parallel to `u` at offsets `0, ±W/4` across `t ∈ [−(L/2 + m), L/2 + m]`; `length = median` of the three.
5. `width_mm` = median of `width_profile_mm`.
6. **Dense profile (for defects):** rotate the mask crop so `u` is horizontal (`cv2.warpAffine`, nearest), then for every column inside the billet find the first/last foreground row → `dense_top_mm`, `dense_bottom_mm` (signed offsets from the axis), `dense_pos_mm`.
7. `sharpness` = variance of Laplacian of the upright grey crop.
8. Upright BGR crop for OCR: rotate `rect_bgr` so the long axis is horizontal, crop `L × W` + `CROP_PAD_MM` each side.
Use `@dataclass(frozen=True, eq=False)` for types holding arrays.

## 10. Defects (`vision/defects.py`)
On the dense profile, ignoring `END_EXCLUDE_MM` at each end; `w(x) = top − bottom` (abs), `med = median(w)`:
- **notch**: a run of `w < med − notch_min_mm` spanning ≥ `DEFECT_MIN_SPAN_MM` → `notch`; `notch_depth_mm = med − min(w)`.
- **bulge**: a run of `w > med + notch_min_mm` spanning ≥ `DEFECT_MIN_SPAN_MM` → `bulge`.
- **taper**: least-squares line of `w` vs `x`; `taper_mm = |slope| × span`; `> taper_max_mm` → `taper`.
- **camber**: centre line `c(x) = (top + bottom)/2`; fit a straight line; `camber_mm = max |c − fit|`; `> camber_max_mm` → `camber`.
- `cs_var_pct = (max − min)/median × 100` of the 21-slice `width_profile_mm`; `min_width_mm`, `max_width_mm` from the same profile.
Aggregation over samples (§11): numeric fields = median; each defect present if detected in > 50% of samples.

## 11. Tracking, triggers, aggregation (`vision/track.py`)

`Tracker.update(detections, t) -> list[FinalizeJob-ready tracks]`:
- Greedy nearest-centre matching within `TRACK_MATCH_MM`; unmatched detections start tracks; unmatched tracks `missing += 1`, dropped after `TRACK_MAX_MISSING`.
- **stable** condition: `full_inside` and centre moved < `STABLE_MM` over the last `STABLE_FRAMES` frames.
- **line** condition: `full_inside` and `|center_x − roi_center_x| ≤ LINE_WINDOW_MM`.
- `auto` = stable OR line. Sampling starts when the mode's condition first holds; each later frame with `full_inside and not merged` adds a `Measurement` sample and an upright crop (keep the `OCR_CROPS` sharpest).
- **Finalize** when: samples ≥ `SAMPLES_TARGET`; or (mode line) the track leaves the window; or the track is lost / leaves full_inside; or `SAMPLE_TIMEOUT_S` since the first sample. Require ≥ `SAMPLES_MIN` samples, else discard (E-08). A track is finalized **at most once** (E-09).
- `merged` detections never sample; a System alert "Separate billets" is raised once per track.
- Aggregate: `length_mm`, `width_mm`, and each slice width = median over samples.

## 12. ID reading (`vision/idparse.py` pure, `vision/ocr.py`, `vision/qr.py`)

### 12.1 Template normalisation (`normalize(text, template) -> str | None`)
Template chars: `A` = letter, `9` = digit, anything else = literal.
1. Uppercase; remove spaces; map `_ . — – ~` to `-` when the template literal at that position is `-`.
2. If `len == len(template) − n_literals`, insert the literals at their positions.
3. If length ≠ `len(template)` → `None`.
4. Position-wise fixes — digit positions: `O,D,Q→0`, `I,L,|→1`, `Z→2`, `S→5`, `G→6`, `B→8`, `T→7`; letter positions: `0→O`, `1→I`, `2→Z`, `5→S`, `6→G`, `8→B`, `7→T`.
5. Validate every position; invalid → `None`.

### 12.2 OCR (`ocr.py`)
`OcrEngine` wraps `rapidocr.RapidOCR` (lazy singleton, loaded in the worker thread). `read(crop_bgr) -> list[tuple[str, float]]` returns (text, score) per line with score ≥ `OCR_MIN_SCORE`. Pre-processing: grey → CLAHE (clip 2.0, 8×8) → upscale `OCR_UPSCALE` → back to 3 channels. Adapt to the installed rapidocr result format (attributes `txts`, `scores`, or legacy tuples) inside this module only. `ocr_ready` = model loaded and a 1-line smoke test passed at startup.

### 12.3 Voting
For each crop: candidates = normalised valid strings from all lines. If no crop yields a valid candidate, repeat on crops rotated 180°. Winner = most frequent valid candidate; tie → higher mean score. `ocr_agreement = count(winner)/crops_with_any_text`; `ocr_confidence` = mean score of winner lines. If no valid candidate: `ocr_text` = best raw uppercase text (or null), not valid.

### 12.4 QR (`qr.py`)
`cv2.QRCodeDetector().detectAndDecode` on each crop (grey, upscaled ×2); first non-empty text wins.

### 12.5 Resolution
`billet_id` = valid OCR winner, else QR text, else `None`. `id_source` = `ocr | qr | none`. `id_mismatch` = valid OCR and QR both present and different.

## 13. Decision (`vision/decide.py`)

Evaluate every rule and collect reasons (numbers to 1 dp). Status = worst level triggered (Fail > Rework > Pass).

| Level | Rule | Reason template |
|---|---|---|
| Fail | `length < nom_L − tol_L` | `Length {L} mm is {d} mm below minimum {min} mm` |
| Fail | `width < nom_W − tol_W` | `Width {W} mm is {d} mm below minimum {min} mm` |
| Fail | `notch` in defects | `Notch {depth} mm deep detected` |
| Fail | `cs_var_pct ≥ cs_var_fail_pct` | `Cross-section variation {v}% ≥ {fail}%` |
| Rework | `length > nom_L + tol_L` | `Length {L} mm is {d} mm over maximum {max} mm (trim)` |
| Rework | `width > nom_W + tol_W` | `Width {W} mm is {d} mm over maximum {max} mm` |
| Rework | `cs_var_pct ≥ cs_var_warn_pct` | `Cross-section variation {v}% ≥ {warn}%` |
| Rework | `taper` / `bulge` / `camber` | `Taper {t} mm` / `Bulge detected` / `Camber {c} mm` |
| Rework | `billet_id is None` | `ID unreadable — tag manually` |
| Rework | `id_mismatch` | `OCR '{ocr}' does not match QR '{qr}'` |
| Pass | none of the above | `Within spec` |

## 14. Logging and exports (`logging_io.py`, `repository.py`)

Per finalized inspection (ocr-worker thread):
1. Write snapshot `snapshots/YYYYMMDD/HHMMSSmmm_t{track}.jpg` (annotated frame at finalize time).
2. Insert the row into SQLite (single transaction), get `id`.
3. Append to `logs/inspections.csv` (open-append-close, `flush` + `os.fsync`; header if new). `PermissionError` → keep the row in an in-memory pending list, retry before the next append; set `log_status=locked` while pending.
4. Mark the workbook dirty.
5. If status is Fail or Rework → insert an alert.
6. Emit `inspection` (+ `alert`) events.

Excel writer thread: when dirty and `EXCEL_DEBOUNCE_S` passed since the last change → build the workbook (03 §5 format; last `EXCEL_MAX_ROWS` rows) → save to `logs/.inspections.tmp.xlsx` → `os.replace` to `logs/inspections.xlsx`. `PermissionError` → `log_status=locked`, retry every `EXCEL_RETRY_S`; success → `ok`. Emit a `status` event on every log_status change. Exports (`/export`) are built in memory and never touch the log files.

Operator override (`PATCH`): stores `Override` JSON, updates `billet_id`/`status` (keeps `auto_status`), marks workbook dirty, appends a CSV line with `override_note` (CSV is an append-only audit trail; the workbook shows current values).

## 15. Pipeline orchestration (`runtime/pipeline.py`, `runtime/worker.py`, `runtime/events.py`, `runtime/metrics.py`)

Processing loop (per new frame index only; otherwise sleep 2 ms):
1. Not calibrated → annotate "CALIBRATE FIRST", publish JPEG, continue.
2. Rectify → glare mask → segment → tracker update → for sampling tracks: measure + defects → sample.
3. Finalize → build `FinalizeJob` → `queue.put_nowait`; if full, drop the oldest job and raise a System alert "Processing overloaded".
4. Overlay (`vision/overlay.py`) on the raw frame: ROI polygon, centre line (line/auto mode), each detection outline in its track colour, live `L × W` label, track id; sampling progress ring; last result label (ID + status colour) near the track for 2 s; HUD (FPS, mode, spec). Rectified view: same drawings in rect space.
5. Encode JPEG for the annotated view at ≤ `STREAM_FPS` (and rectified/raw only while a client requests them).
6. Metrics: capture fps, process fps, process_ms per frame; latency per inspection = logged time − `first_sample_t`.
Stats event every `STATS_INTERVAL_S`. Drift check every `DRIFT_CHECK_S`.

Shutdown: set a stop event, join threads (timeout 3 s), close the source, flush pending CSV rows and a final workbook write.

## 16. API behaviour (`api/`)

- Lifespan: create dirs, DB + seed default spec, load calibration/background/intrinsics, start the event bus, start threads with the configured source, warm up OCR in the worker (log a clear error with the download command if models are missing; `ocr_ready=false`, QR still works).
- `/stream.mjpg`: async generator yielding the latest JPEG for the requested view at ≤ `STREAM_FPS`, only when the frame changed; ends cleanly on client disconnect.
- Calibration routes run detection on the latest frame inside `run_in_threadpool`; they swap the rectifier atomically under the state lock and broadcast `calibration`.
- `/source`, `/control/*`, spec activation → broadcast `status`.
- Routes never touch OpenCV objects owned by threads without the state lock.

## 17. Evaluation

### 17.1 Real props (`/eval → real`)
Load `PROPS_CSV`. Ground-truth key per inspection = `qr_text` if present, else `billet_id`. Over inspections whose key is a known prop and whose status was not overridden: errors `(measured − gt)/gt × 100` for length and width; MAE, p95 (of absolute), `within_1pct_rate`; OCR accuracy = share of inspections with QR where the valid OCR winner equals QR; read rate = share with any id. Per-prop rows (03 `PropAccuracy`). No props file or no matches → `real = null`.

### 17.2 Synthetic benchmark (`tools/bench_synthetic.py`)
`--n` scenes split evenly over the 9 variants (seeded). Run the full per-image path (calibrate from the rendered marker → rectify → segment → measure → defects → OCR → QR). Write `reports/bench_synthetic.json` (`SyntheticBench`). `/eval → synthetic` reads it (null if missing).

## 18. Tests (all in `backend/tests/`, no camera, no network)

| File | Must prove |
|---|---|
| `test_synth.py` | Same seed → identical image; ground truth corners match the drawn marker (< 0.5 px) |
| `test_calibration.py` | Homography from a synthetic marker maps known bed points to within 0.3 mm; `image_px_per_mm` within 2% of truth; drift detects a 3 mm shift |
| `test_segment_measure.py` | One detection per billet; full_inside false when touching the ROI edge; merged flag on touching billets |
| `test_accuracy_synthetic.py` | Over 60 seeded scenes across all variants: length and width **MAE ≤ 0.5%** and **max error ≤ 1.0%** |
| `test_defects_decide.py` | Notch/taper/bulge/camber scenes detected; clean scenes have no defects in ≥ 95% of cases; every decision rule hit by a crafted input |
| `test_idparse.py` | Template normalisation and confusion fixes table-driven (≥ 20 cases); voting tie-break |
| `test_ocr_qr.py` | On 40 seeded synthetic crops: OCR read accuracy ≥ 0.90 (log the actual value); QR decodes ≥ 0.95; 180° text read via second pass. Skipped with a clear message if OCR models are missing |
| `test_track.py` | Synthetic station video and conveyor video: inspections == billets; no duplicates; measurements within 1% |
| `test_db_logging.py` | Insert + CSV + workbook; workbook write survives a simulated `PermissionError` (monkeypatched `os.replace`) and succeeds later; CSV pending buffer flushes; exports have the exact column order |
| `test_pipeline.py` | Pipeline on the synthetic source for ~6 s: ≥ 1 inspection logged with latency < 2000 ms; process fps ≥ 15 at 1920×1080 (perf assertion uses 0.8× margin and is marked `@pytest.mark.perf`) |
| `test_api.py` | TestClient: health, status, specs CRUD/activate, calibration marker on synthetic source, inspections list/patch, export formats, error bodies |

## 19. Frontend behaviour (`web/`)

- **LiveProvider** (`lib/live.tsx`): WebSocket with reconnect (1 s → 5 s), holds latest `StatsMessage`, `StationStatus`, last 30 inspections, alerts, calibration; refetches `/status`, `/inspections?limit=30`, `/calibration` on (re)connect.
- **TopBar**: BilletVision, nav (Live, Log, Calibration, Accuracy), chips: camera (ok/down), calibrated, FPS, latency p95, Excel log status, theme toggle, mute toggle.
- **SystemBanner**: camera down / not calibrated (link to Calibration) / Excel locked — retrying / drift not ok.
- **AlertCenter**: on `inspection` with Fail → red toast + two 880 Hz beeps (Web Audio) + speech (`speechSynthesis`, en-IN voice if available): "Billet {ID spelled with spaces} rejected. {first reason}." Rework → amber toast + one beep. System → neutral toast. Mute state in `localStorage` (try/catch).
- **Live (`/`)**: left 2/3 `LiveFeed` (`<img src={API}/stream.mjpg?view=…>`, reload on reconnect, view toggle annotated/rectified/raw); right: `LatestResultCard` (big status, ID + source icon, L × W with signed deviations coloured vs tolerance, defects chips, reasons, latency), `StationControls` (source select + value input, pause/resume, trigger mode, capture background); bottom `RecentStrip` (last 12 snapshots with status borders, click → log detail).
- **Log (`/log`)**: filters (status, ID search, spec, since), table (time, ID, source, L, W, ΔL, ΔW, CS var, defects, status, latency), pagination, row → dialog `InspectionDetail` (snapshot, `WidthProfileChart` with nominal ± tolerance band, OCR vs QR, reasons, `OverrideForm`), export buttons xlsx/csv/json.
- **Calibration (`/calibration`)**: 5 steps — Source, Marker (button + result: px/mm, warning if < 2.5, reprojection), Background, Verify (known length/width inputs → result with pass/fail at 1%), Spec (form for `SpecUpsert`, list + activate). Live raw snapshot refreshed every second and the rectified view.
- **Accuracy (`/accuracy`)**: `PropAccuracyTable`, `OcrAccuracyCard`, `SyntheticBenchCard` (per-variant table), `PerformanceCard` (from `/metrics`). Empty states: "Inspect the props listed in data/props.csv" / "Run make bench".
- Status colours (`lib/status.ts`): Pass `emerald-600`, Rework `amber-500`, Fail `red-600`, System `slate-500`; always with text.

## 20. Demo (60 s)

1. Live page, real camera, calibrated; top bar shows FPS and Excel ok.
2. Slide prop H24-1187 under the camera → outline + live L × W → result card **Pass** within 2 s; row appears in the recent strip.
3. Slide an undersized prop → **Fail**, red toast, beeps, spoken reason.
4. Slide the notched prop → **Fail — notch**.
5. Switch a lamp off → measurements stay within tolerance.
6. Accuracy page: per-prop error % vs vernier, OCR accuracy vs QR; open the Excel export.

## 21. Non-negotiables
Measure only fully-inside billets · one inspection per billet · never block the processing thread on OCR/disk · SQLite is the source of truth · no invented numbers · seeded synthetic tests · offline · no scope creep (full list in `GEMINI.md` §3).
