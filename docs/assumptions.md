# Assumptions

This document lists the core domain and physical assumptions made by the BilletVision system during the hackathon prototype phase. If any of these assumptions are violated in the real environment, the system's accuracy or behavior may degrade.

## 1. Environment & Setup
1. **Fixed Overhead Geometry:** The camera is strictly overhead and looking straight down at the inspection bed. If the camera is tilted, the 2D homography will induce perspective errors.
2. **Uniform Billet Height:** The system uses exactly one camera. Because we calibrate to a specific Z-plane (using the ArUco marker mounted on a spacer of billet height), we assume all billets have the exact same thickness/height. If a billet is thicker or thinner, parallax will cause its length and width measurements to be incorrect.
3. **Controlled Lighting:** Illumination is uniform and diffuse. Extreme point-light sources may cause specular highlights (glare) that fragment the segmentation mask.

## 2. Objects & Presentation
1. **Separation:** Billets travel on the conveyor with physical separation. If billets touch, they will be merged into a single detection, which the system will flag and refuse to measure.
2. **Cold Steel Stand-ins:** The vision processing (blurring, thresholding, morphology) is tuned for cold objects (e.g., wooden blocks or cold steel) against a dark background. Red-hot billets emitting intense infrared light will completely saturate standard optical cameras without heavy IR filters.
3. **Label Contrast:** OCR relies on high-contrast, upright labels (e.g., white paint on dark steel or printed paper labels). It does not use deep learning specifically trained on low-contrast stamped or dot-peened characters.

## 3. Operations
1. **Conveyor Speed limit:** The camera framerate and processing latency impose a speed limit on the conveyor. At 15 fps, a billet moving at 150 mm/s moves 10 mm per frame. Too fast, and motion blur will ruin edge detection and OCR.
2. **Marker Stability:** The ArUco marker is permanently affixed to the inspection bed. If it moves during operation, a `CALIB_DRIFT` alert is raised and measurements become unreliable until recalibration.
3. **Local Network:** The dashboard requires low-latency websocket connections. It is designed to run on the local machine (or a tightly coupled local network) alongside the backend.
