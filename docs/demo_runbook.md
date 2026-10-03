# BilletVision Demo Runbook

This runbook outlines the 5-minute interactive demo script, fallback procedures, calibration guide, troubleshooting, and setup checklist for the hackathon presentation.

## 5-Minute Demo Script

1. **Setup (0:00 - 0:30)**
   - Open the Live page on the dashboard.
   - Verify camera is connected and calibrated (Top bar indicates "Camera OK", "Calibrated", Excel "OK").
   - Mention the system is running fully offline (no internet) and the frontend is statically exported.

2. **Good Bar (0:30 - 1:00)**
   - Place a **nominal prop** on the belt.
   - Observe tracking box and live dimensions on HUD.
   - Wait for auto-finalize.
   - **Result:** Dashboard shows green **PASS**. 

3. **Oversize Bar (1:00 - 1:30)**
   - Place an **oversize prop**.
   - **Result:** Dashboard shows amber **REWORK**.
   - Point out the deviation numbers and tolerance in the details card.

4. **Notched or Undersize Bar (1:30 - 2:00)**
   - Place the **notched prop**.
   - **Result:** Dashboard shows red **FAIL**.
   - Listen for the audio beep and text-to-speech announcement.
   
5. **Unreadable ID (2:00 - 2:30)**
   - Place a prop with a scrambled or covered label.
   - **Result:** The OCR will fail to read it. Status shows **REWORK** ("ID unreadable — tag manually").

6. **Marker Nudge (2:30 - 3:00)**
   - Physically push the ArUco marker > 1mm from its original spot.
   - Wait for the next drift check.
   - **Result:** System alerts about `CALIB_DRIFT` (Calibration Drift). New inspections will default to `REVIEW`/`REWORK`.

7. **Excel Lock Handling (3:00 - 4:00)**
   - While scanning a new bar, **open the Excel workbook** (`logs/inspections.xlsx`) on the machine to lock it.
   - **Result:** The dashboard Top Bar shows "Excel Locked". The system gracefully buffers the logs in memory.
   - Close Excel. The Top Bar reverts to "Excel OK" and buffers are flushed.

8. **Results & Limitations (4:00 - 5:00)**
   - Navigate to the **Log** tab: Show the data table, click a row to view the snapshot and width profile chart.
   - Navigate to the **Accuracy** tab: Show real-time empirical measurements.
   - Briefly summarize limitations: **Cold physical stand-ins only**, **printed/painted labels only** (no stamped steel), **single overhead camera** (no height measurement), **conveyor simulated**, **hot billets untested**.

## Replay-Mode Fallback

If the live camera fails completely:
1. Open `.env` (or set the environment variable) and change `SOURCE_TYPE` to `synthetic`.
2. Restart the backend: `uvicorn main:app`
3. The system will auto-calibrate from the synthetic frames and generate synthetic passing/failing billets on loop.

## Recalibration Procedure (< 10 minutes)

1. Clear the belt of any billets.
2. Place the ArUco marker block accurately at the specified physical origin on the belt, ensuring it sits at the billet-top height to prevent parallax errors.
3. Open the **Calibration** tab in the dashboard.
4. Click **Detect Marker**. Verify px/mm and re-projection error.
5. Click **Capture Background**.
6. Place a nominal prop on the belt and use the **Verify** form to test.
7. Return to the Live tab.

## Troubleshooting

- **Camera Not Found:** Ensure no other app (like OBS or Zoom) is using the camera. Check `SOURCE_VALUE` in config (typically `0` or `1`).
- **Excel File Locked Constantly:** Check if any background cloud sync (OneDrive/Google Drive) is locking the file.
- **Calibration "Reduced Baseline":** Ensure you are using a flat, high-quality print for the ArUco marker. Avoid glare on the marker.
- **OCR Failing Consistently:** Check focus on the camera and ensure lighting is adequate.

## Setup Checklist (Fresh Clone)

- [ ] Connect the camera to the laptop.
- [ ] Run `npm install` and `npm run build` in the `web/` folder.
- [ ] Set up Python virtual environment in `backend/` and `pip install -r requirements.txt`.
- [ ] Execute `make test` to verify all components work.
- [ ] Position the camera overhead, place the ArUco marker on the belt, and run the recalibration procedure (above).
- [ ] Run `tools/collect_ground_truth.py` if real-world measurements are needed for the Accuracy page.
- [ ] Start the backend with `cd backend && source .venv/bin/activate && uvicorn main:app`.
