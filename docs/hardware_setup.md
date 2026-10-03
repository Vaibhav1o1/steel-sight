# Hardware Setup Guide — BilletVision

This guide covers physical rig assembly, marker preparation, optical mounting, and camera settings for BilletVision.

---

## 1. Marker Preparation & Verification

1. **Print Scale:**
   - Print markers at **100% scale** (do not scale to fit or shrink).
   - Use heavy matte cardstock or photo paper to prevent curling, specular glare, or warping.
2. **Caliper Verification:**
   - Use a calibrated digital caliper to measure the outer black square of the printed ArUco marker.
   - Record the measured dimension to 0.1 mm (e.g. 79.8 mm instead of the nominal 80.0 mm).
   - Input the measured dimension into the calibration setup (`marker_side_measured_mm`). The system refuses to save calibrations without a verified measurement.
3. **Multi-Marker Layout ($N \ge 4$ Recommended):**
   - For wide-field inspection, use 4 markers placed at known physical offsets around the inspection bed.
   - Default arrangement: 4 corner markers framing the field of view outside the conveyor belt path.
   - Single-marker calibration operates in `reduced-baseline` mode with an operational warning.

---

## 2. Marker Plane Elevation & Alignment

1. **Top-Face Elevation:**
   - Billets have physical thickness (e.g. 50 mm).
   - Mount markers on rigid elevation blocks or a mounting plate such that the marker face is **coplanar with the top surface of the billets** (`marker_plane_height_mm`).
   - *Why:* Overhead cameras exhibit perspective parallax. Placing markers on the floor/belt while billets are 50 mm higher causes severe magnification scaling errors.
2. **Conveyor Clearance:**
   - Mount marker blocks firmly outside the conveyor belt path so moving billets cannot bump, occlude, or dislodge the markers.

---

## 3. Camera Mounting & Rig Stability

1. **Rigid Overhead Mounting:**
   - Mount the camera directly overhead (nadir view) perpendicular to the conveyor plane.
   - Ensure the field of view covers the marker(s) and the entire inspection ROI (minimum 600 mm length span).
2. **Mechanical Stabilization:**
   - Secure the camera arm to a rigid structure or stand.
   - Secure all clamp screws and **tape the mount** to eliminate mechanical vibration or drift during conveyor operation.
   - Ensure USB cables are strain-relieved and taped down so cable drag does not tilt the camera.

---

## 4. Optical & Sensor Configuration

1. **Lock Exposure:**
   - Disable Auto-Exposure (AE). Set a fixed exposure time (e.g. $1/100\text{ s}$ or $10\text{ ms}$) to eliminate frame-to-frame intensity fluctuation.
2. **Lock White Balance:**
   - Disable Auto White Balance (AWB). Set a manual color temperature (e.g. 4500 K or 5000 K).
3. **Lock Focus:**
   - Set manual focus precisely on the billet top face plane. Disable continuous autofocus hunting.
4. **Diffuse Lighting:**
   - Position dual LED light bars obliquely to provide uniform illumination without specular hotspots or reflections on metal billet surfaces.

---

## 5. Calibration & Drift Watcher Protocol

1. **Zeroing:**
   - Run calibration (`POST /calibration/marker`). Verify that RMS residual is $\le 1.5\text{ mm}$.
2. **Verification Step:**
   - Place a known physical reference gauge bar in the ROI and run verification (`POST /calibration/verify`).
   - Verify length and width errors are within $\pm 1\%$.
3. **Continuous Drift Monitoring:**
   - The background drift watcher checks marker positions periodically (default every 30 s).
   - If marker drift exceeds `DRIFT_MAX_MM` (1.0 mm default), the system triggers a persistent `CALIB_DRIFT` alert and forces all subsequent inspections to `Review` status until re-zeroed or acknowledged.
