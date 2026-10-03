# Hardware Setup & Tuning Guide

This document describes the physical setup of the BilletVision inspection station. Proper hardware configuration is critical, as BilletVision relies on fixed overhead geometry and a 2D homography to compute physical dimensions.

## 1. Physical Mount and Camera
- **Camera Position:** Mount the camera vertically facing directly down at the inspection bed. The optical axis must be as perpendicular to the belt as possible.
- **Stand Height:** Adjust the height so the entire inspection bed width is visible. A typical height is 600 mm – 800 mm depending on the camera FOV.
- **Background:** Use a matte, dark, and uniform background (e.g., black felt or dark conveyor belt material). Avoid shiny surfaces that cause specular reflections.
- **Lighting:** Provide diffuse overhead lighting. Avoid harsh directional lights that cast strong shadows or cause glare on the props.

## 2. ArUco Marker Calibration
- **Marker Preparation:** Print the ArUco marker (generated via `make marker`) on rigid, flat cardstock. Ensure the printed dimensions are exactly 80.0 mm x 80.0 mm (or update `MARKER_MM` in `config.py` if different).
- **Marker Spacer (Crucial for Parallax):** Place the marker on a spacer block so that its top surface is at exactly the same height as the top surface of the billets being inspected. If the marker is on the belt surface, the billets will appear larger due to parallax.
- **Placement:** Place the marker clearly in the camera view (typically to the left or right of the active inspection ROI). It must remain stationary during operation.

## 3. Connecting the Camera
- **USB Webcam:** Plug in the camera. Set `SOURCE_TYPE=webcam` and `SOURCE_VALUE=0` (or `1`) in the `.env` file.
- **Windows DirectShow:** On Windows, OpenCV uses DirectShow (`cv2.CAP_DSHOW`) by default to enable fast resolution switching. Ensure no other applications are using the camera.
- **Phone IP Camera:** If using a phone as a camera (e.g., IP Webcam app), set `SOURCE_TYPE=url` and `SOURCE_VALUE=http://<ip>:8080/video`.

## 4. Bring-up Steps
1. **Mount:** Fix the camera and place the marker.
2. **Start Backend:** Run `uvicorn main:app` and open the frontend Live dashboard.
3. **Calibrate:** Go to the **Calibration** tab and click **Detect Marker**. Ensure px/mm is computed.
4. **Capture Background:** Clear the belt of all billets, then click **Capture Background**.
5. **Verify:** Place a reference billet with known dimensions, enter its length in the Verify form, and confirm the error is < 1%.

## 5. Tuning (Segmentation Constants)
If detections are noisy or billets are merged, you may need to tune the constants in `backend/billetvision/config.py` and log the changes in `docs/decisions.md`:
- `SEG_BLUR_SIGMA`: Increase if noise causes jagged edges.
- `DIFF_MIN`: Increase if background noise (shadows) is detected as foreground.
- `CLOSE_KERNEL_MM` / `OPEN_KERNEL_MM`: Adjust morphology to close holes or remove small noise.
- `SATURATION_LEVEL`: Adjust the threshold for glare masking if reflections cause segmentation splits.
