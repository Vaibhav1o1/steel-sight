# BilletVision Prototype: Calibration, Inspection Pipeline & Vision Architecture Guide

This document is an engineering overview for the team explaining **how our prototype works, how it is calibrated, how inspection outputs are calculated, and what models we use.**

---

## 1. System Overview & Core Philosophy

BilletVision is an automated vision-based inspection station designed for steel billets. As billets move down the conveyor, the overhead camera captures frames at 30 FPS, measures physical dimensions, detects surface/edge defects, reads the heat/lot identifier, and issues an immediate **PASS / REWORK / REJECT** decision.

```
       [ Overhead Industrial Camera (1920x1080 @ 30fps) ]
                              │
                              ▼
    ┌──────────────────────────────────────────────────┐
    │  Conveyor Bed (Physical Plane in mm)             │
    │                                                  │
    │   [ArUco Marker]       ======> Conveyor Flow     │
    │   (0,0 Origin)         ┌─────────────────────┐   │
    │   80x80 mm             │  Billet Under Test  │   │
    │                        │  ID: H24-1187       │   │
    │                        └─────────────────────┘   │
    │   ◄────────────── ROI [60mm to 660mm] ────────►  │
    └──────────────────────────────────────────────────┘
```

### Key Engineering Decisions
1. **Sub-millimeter Determinism**: Metrological measurements (length, width, camber, notches) rely on **sub-pixel geometric computer vision**, not generative AI or black-box neural networks. This guarantees zero hallucinations, explainable rejection reasons, and sub-millimeter repeatable precision.
2. **AI Where It Belongs**: Deep learning (lightweight ONNX neural networks) is deployed specifically for **Optical Character Recognition (OCR)** to read stamped/printed IDs in challenging factory conditions (glare, scale, dust).
3. **Offline & Real-Time**: Runs fully on-premise without cloud latency or internet dependencies at >30 FPS on standard edge CPUs.

---

## 2. How the Prototype is Calibrated

Calibration establishes the mathematical link between **camera image pixels $(u, v)$** and **real-world conveyor coordinates $(X, Y)$ in millimeters**.

```
Image Frame (pixels)                                Physical Bed (millimeters)
 (0,0) ──────► u                                     (0,0) ──────► X (Longitudinal, mm)
  │                                                   │
  │     [Marker]                                      │     [Marker Origin]
  ▼     ┌───┐            3x3 Homography (H)           ▼     ┌───┐ (80x80 mm)
  v     └───┘         ───────────────────────►        Y     └───┘
                                                            (Transverse, mm)
```

The system uses a **two-tier calibration strategy**:

### Tier A: Camera Intrinsics (Lens Correction)
* **Goal**: Correct barrel or pincushion distortion caused by the camera lens.
* **Method**: A 9×6 printed checkerboard (25.0 mm squares) is placed under the camera at varying angles. OpenCV's pinhole camera model computes:
  - **Camera Matrix $K$**: Focal lengths $(f_x, f_y)$ and optical center $(c_x, c_y)$.
  - **Distortion Coefficients $D$**: Radial $(k_1, k_2, k_3)$ and tangential $(p_1, p_2)$ distortion.
* **Output**: Undistorts raw camera frames before metric processing.

### Tier B: Planar Homography & Extrinsics (Station Setup)
* **Goal**: Map 2D pixel coordinates on the conveyor bed directly to millimeters $(X, Y)$.
* **Method**: A single high-contrast **ArUco fiducial marker** (`DICT_4X4_50`, Marker ID `0`, exactly $80 \times 80\text{ mm}$) is permanently placed at the bed origin $(0, 0)$.
* **Sub-pixel Corner Refinement**: 
  When the ArUco detector finds marker corners, standard pixel coordinates are rounded. We apply `cv2.cornerSubPix` with a Gaussian window to locate corners with **sub-pixel accuracy (< 0.2 px)**.
* **Homography Matrix ($H$)**:
  Given the 4 known marker physical coordinates:
  - Top-Left: $(0, 0)\text{ mm}$
  - Top-Right: $(80, 0)\text{ mm}$
  - Bottom-Right: $(80, 80)\text{ mm}$
  - Bottom-Left: $(0, 80)\text{ mm}$
  
  And their measured pixel locations $(u_i, v_i)$, OpenCV solves the perspective transform:
  $$\begin{bmatrix} X \\ Y \\ 1 \end{bmatrix} \sim H \begin{bmatrix} u \\ v \\ 1 \end{bmatrix}$$
* **Pixel Resolution**: 
  Calculated across the marker edges in px/mm (typically $\approx 2.4\text{ to }3.0\text{ px/mm}$).

### Continuous Drift Monitoring (Fail-Safe)
During live operation, the system monitors the ArUco marker every frame:
* If mechanical vibration, camera nudge, or conveyor settling shifts the marker position by **$> 3.0\text{ mm}$**, the system immediately flags a `CALIB_DRIFT` warning and halts automatic PASS/FAIL approvals until re-zeroed.

---

## 3. On What Basis Outputs Are Generated

Every frame captured by the camera passes through an automated synchronous vision pipeline:

```mermaid
graph TD
    A[Raw Frame 1920x1080] --> B[Undistort & Crop to ROI]
    B --> C[Otsu Segmentation & Morphology]
    C --> D[Contour Extraction & Billet Tracking]
    D --> E{Is Billet Fully Inside & Non-Merged?}
    E -- No --> F[Update Tracker / Wait for Next Frame]
    E -- Yes --> G[Trigger Inspection: Exactly Once]
    G --> H[Physical Dimension Metrology]
    G --> I[Defect & Geometry Analysis]
    G --> J[OCR Text Extraction via ONNX]
    H & I & J --> K[Rule-Based Decision Engine]
    K --> L[Save SQLite / Emit WebSocket Event]
```

### Step 1: Segmentation & Billet Isolation
* Frames are converted to grayscale and segmented using an adaptive/Otsu threshold.
* Morphological opening/closing removes conveyor belt streaks, mill dust, and specular reflections.
* Valid billet contours are extracted based on minimum area and aspect ratio filters.

### Step 2: Tracking & The Single-Inspection Rule
* As billets travel along the conveyor, a multi-object centroid tracker maintains continuous IDs across frames.
* **Critical Rule**: **A billet is measured only when it is fully inside the Region of Interest (ROI: $60\text{ mm} \le X \le 660\text{ mm}$) and not touching another billet.**
* **Exactly one inspection record is produced per physical billet track.**

### Step 3: Dimensional Metrology (How Dimensions Are Calculated)
All pixel measurements are projected through the inverse homography $H^{-1}$ into physical millimeters:

| Measurement | Method | Unit / Accuracy |
|---|---|---|
| **Length ($L$)** | Longitudinal caliper distance along the primary billet axis | $\text{mm} \ (\pm 1.0\text{ mm})$ |
| **Width ($W$)** | Median width evaluated across 10–20 equidistant perpendicular cross-sections | $\text{mm} \ (\pm 0.5\text{ mm})$ |
| **Cross-Section Variation** | $\frac{W_{\max} - W_{\min}}{W_{\text{nominal}}} \times 100\%$ across all slices | $\%$ |
| **Camber (Straightness)** | Maximum lateral deviation of the longitudinal centerline from an ideal line | $\text{mm}$ |
| **Taper** | Absolute difference between the average width of the leading 15% and trailing 15% | $\text{mm}$ |
| **Notches / Surface Bite-ins** | Convex hull defect analysis; detects indentations where edge deviates inwards $\ge 5\text{ mm}$ | $\text{mm}$ depth |

### Step 4: Decision Engine (PASS / REWORK / REJECT)
Decisions are deterministic and compared strictly against the product recipe (configured in the database):

```
                       ┌─────────────────────────────┐
                       │   Calculated Measurements   │
                       └──────────────┬──────────────┘
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
     Within Tolerances?                             Out of Tolerances?
  - Length: Nominal ± 5.0 mm                      - Undersize length/width
  - Width:  Nominal ± 2.0 mm                      - Large notch (≥ 5 mm)
  - Camber: ≤ 3.0 mm                              - Camber > 3.0 mm
  - CS Var: ≤ 3.0 %                               - Severe taper
               │                                             │
               ▼                                             ▼
          ┌─────────┐                         Is it Oversize / Fixable?
          │  PASS   │                                    │
          └─────────┘                         ┌──────────┴──────────┐
                                              ▼                     ▼
                                         ┌──────────┐          ┌──────────┐
                                         │  REWORK  │          │  REJECT  │
                                         │(Oversize)│          │(Undersize│
                                         └──────────┘          │or Voids) │
                                                               └──────────┘
```

* **PASS**: All dimensions within tolerance, no notches, camber $\le 3\text{ mm}$, cross-section variation $\le 3\%$.
* **REWORK**: Length or width is *oversize* (billet can be trimmed or planed), or moderate taper that can be re-squared.
* **REJECT**: Billet is *undersize* (material cannot be added back), has deep edge notches ($\ge 5\text{ mm}$), or camber exceeds reworkable limits.

---

## 4. The "Model": AI vs Classical Vision

Teammates often ask: *"Where is the neural network / AI model?"* Here is how our architecture divides responsibilities:

### Why We Do NOT Use YOLO / Deep Learning for Measurement
1. **Sub-pixel Accuracy**: Deep learning object detectors predict bounding boxes with $\pm 5\text{ to }10\text{ pixel}$ jitter. In our optical setup, 10 pixels is $\approx 3.5\text{ mm}$, which would fail industrial tolerance requirements. Classical contour geometry achieves sub-pixel edge localization ($< 0.3\text{ mm}$).
2. **Deterministic Certification**: Plant managers require transparent pass/fail justification. If a billet fails, we provide the exact coordinates and depth of the notch ($X=245.2\text{ mm}, \text{depth}=6.4\text{ mm}$), which a black-box model cannot guarantee.
3. **Speed & Latency**: Edge CPUs can run contour and homography maths in $< 8\text{ ms}$, leaving the remaining frame budget for UI streaming and logging.

### Where Neural Networks ARE Used: Lightweight Edge OCR
For reading stamped or printed heat/lot IDs (e.g., `H24-1187`):
* **Architecture**: **RapidOCR / PaddleOCR** ported to **ONNX Runtime**:
  1. **Text Detector (DBNet)**: Convolutional neural network that detects text bounding polygons on rotated/glared surfaces.
  2. **Text Recognizer (SVTR / CRNN)**: Sequence-to-sequence neural network converting cropped text patches to alphanumeric strings.
* **Execution**: Runs locally via ONNX Runtime using CPU SIMD/NEON instructions; no GPU required.
* **Post-Processing Verification**:
  - Regular expression schema verification (e.g., `^[A-Z]\d{2}-\d{4}$`).
  - Levenshtein distance matching against the day's active heat lot database.

### The Synthetic Scene Generator (Digital Twin)
To validate our system before physical steel billets arrive on the test rig:
* We built an optical simulation engine (`synth.py`) that generates high-fidelity photorealistic synthetic camera frames.
* It simulates realistic factory optical phenomena:
  - Surface mill scale, dust, water droplets, and directional shadows.
  - Specular glare spots and conveyor motion blur.
  - Precise programmatic defects (notches, camber, taper, dimensional variance) with exact known millimeter ground truth.
* This allows us to run regression benchmarks proving our algorithms achieve $< 0.3\text{ mm}$ accuracy across hundreds of edge-case scenarios.

---

## 5. Summary Cheat Sheet for Teammates

| Question | Short Answer |
|---|---|
| **How is it calibrated?** | An 80 mm ArUco marker at $(0,0)$ provides homography $H$ with sub-pixel refinement, converting pixels to physical mm. Continuous drift monitoring detects any physical movement $> 3\text{ mm}$. |
| **How does it measure billets?** | Contours are isolated via Otsu segmentation, tracked across frames, and converted to real mm via homography. Length is caliper distance; width is sampled across multiple cross-sections; notches are detected via convex hull defects. |
| **When does it inspect?** | Exactly once per billet, precisely when the billet is fully within the ROI ($60$ to $660\text{ mm}$) and non-overlapping. |
| **What does the ML model do?** | An ONNX text detection & recognition model (RapidOCR) reads the heat/lot ID. Geometric measurements are performed using precision sub-pixel computer vision for maximum accuracy and zero hallucination. |
| **What decisions are made?** | **PASS** (all specs met), **REWORK** (oversize/fixable), or **REJECT** (undersize/notched/bent), accompanied by specific defect reason codes. |
