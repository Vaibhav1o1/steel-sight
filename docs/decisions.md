# Decisions Log

| Date | Task | Decision | Reason |
|---|---|---|---|
| 2026-10-03 | T05 | Used React 19 `useSyncExternalStore` for client hydration and localStorage sync | Prevent cascading renders and satisfy `react-hooks/set-state-in-effect` without `as` casts |
| 2026-10-03 | T07 | Set `CameraSpec` defaults to `fov_mm=760.0`, `center_mm=(290.0, 0.0)` | Ensures both the ArUco marker at (0, 0) and the entire ROI [60, 660] mm are fully visible in the 1920×1080 frame |
| 2026-10-03 | T10 | In `_find_crossing`, restrict candidates to the expected half-plane (`side < 0` vs `side > 0`) within `search_margin_mm` | Prevents glare-corrupted edge searches from erroneously selecting the opposite edge's crossing; correctly marks slice failed for linear interpolation |
