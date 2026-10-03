# Limitations

The current BilletVision prototype is built for a 28-hour hackathon environment. It carries the following explicit limitations and constraints:

- **Cold Physical Stand-ins Only**: The system has been validated on cold, scaled-down physical props (e.g. wooden blocks, 3D printed objects). It has NOT been tested with hot billets. Thermal emissions, heat haze, and the intense IR radiation from hot steel (800°C–1200°C) will require physical IR filtration, specialized cameras, and likely algorithmic tuning that are beyond the scope of this prototype.
- **Printed/Painted Labels Only**: OCR validation has been performed on high-contrast printed labels and clear marker markings. Real-world stamped, dot-peened, or chalk-written IDs directly on hot steel are explicitly out of scope for this version (Tier 3 requirement).
- **Single Overhead Camera**: The current setup uses exactly one overhead 1080p camera. Consequently, there is **no height measurement**. We assume billets are flat and we extrapolate length/width via 2D homography calibrated at a fixed bed height. We cannot detect height defects or perform precise 3D volume estimation.
- **Simulated Conveyor**: Tracking assumes a uniform translation model consistent with a simulated conveyor belt. 
- **Fixed Illumination Assumption**: Glare removal and thresholding assume controlled ambient lighting or uniform diffuse overhead lighting. Extreme lighting gradients may cause segmentation failures.
