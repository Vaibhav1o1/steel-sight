from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Sequence

import numpy as np
from numpy.typing import NDArray

from billetvision import config
from billetvision.schemas import Roi
from billetvision.vision.types import DefectResult, Detection, Measurement, Track

logger = logging.getLogger(__name__)


def aggregate_measurements(samples: Sequence[Measurement]) -> Measurement:
    """Aggregate multiple measurement samples into a single Measurement per SPEC §11.

    Length, width, and each slice width are the median over samples.
    """
    if not samples:
        raise ValueError("Cannot aggregate empty samples sequence")
    if len(samples) == 1:
        return samples[0]

    length_mm = float(np.median([s.length_mm for s in samples]))
    width_mm = float(np.median([s.width_mm for s in samples]))

    n_slices = len(samples[0].width_profile_mm)
    slice_medians = tuple(float(np.median([s.width_profile_mm[k] for s in samples])) for k in range(n_slices))
    valid_slices = int(round(float(np.median([s.valid_slices for s in samples]))))
    sharpness = float(np.max([s.sharpness for s in samples]))
    angle_deg = float(np.median([s.angle_deg for s in samples]))

    # Select dense profiles from the sample closest to the median length
    best_idx = int(np.argmin([abs(s.length_mm - length_mm) for s in samples]))
    best_sample = samples[best_idx]

    return Measurement(
        length_mm=length_mm,
        width_mm=width_mm,
        width_profile_mm=slice_medians,
        valid_slices=valid_slices,
        dense_pos_mm=best_sample.dense_pos_mm,
        dense_top_mm=best_sample.dense_top_mm,
        dense_bottom_mm=best_sample.dense_bottom_mm,
        sharpness=sharpness,
        angle_deg=angle_deg,
    )


def aggregate_defects(defect_results: Sequence[DefectResult]) -> DefectResult:
    """Aggregate defect results over samples per SPEC §10.

    Numeric fields are median; each defect is present if detected in > 50% of samples.
    """
    if not defect_results:
        raise ValueError("Cannot aggregate empty defect results")
    if len(defect_results) == 1:
        return defect_results[0]

    cs_var_pct = float(np.median([d.cs_var_pct for d in defect_results]))
    taper_mm = float(np.median([d.taper_mm for d in defect_results]))
    camber_mm = float(np.median([d.camber_mm for d in defect_results]))
    min_width_mm = float(np.median([d.min_width_mm for d in defect_results]))
    max_width_mm = float(np.median([d.max_width_mm for d in defect_results]))
    notch_depth_mm = float(np.median([d.notch_depth_mm for d in defect_results]))

    all_defects = {d for res in defect_results for d in res.defects}
    n_total = len(defect_results)
    confirmed_defects = tuple(
        sorted(
            [d for d in all_defects if (sum(1 for res in defect_results if d in res.defects) / n_total) > 0.5]
        )
    )

    return DefectResult(
        width_variation_pct=cs_var_pct,
        taper_mm=taper_mm,
        camber_mm=camber_mm,
        min_width_mm=min_width_mm,
        max_width_mm=max_width_mm,
        defects=confirmed_defects,
        notch_depth_mm=notch_depth_mm,
    )


class Tracker:
    """Centroid tracker, sampling controller, and finalizer per SPEC §11."""

    def __init__(
        self,
        roi: Roi | None = None,
        trigger_mode: str | None = None,
        track_match_mm: float | None = None,
        track_max_missing: int | None = None,
        stable_frames: int | None = None,
        stable_mm: float | None = None,
        samples_target: int | None = None,
        samples_min: int | None = None,
        line_window_mm: float | None = None,
        sample_timeout_s: float | None = None,
        ocr_crops: int | None = None,
    ) -> None:
        self.roi: Roi = roi if roi is not None else Roi(**config.ROI_DEFAULT)
        self.trigger_mode: str = trigger_mode or config.TRIGGER_MODE
        self.track_match_mm: float = track_match_mm if track_match_mm is not None else config.TRACK_MATCH_MM
        self.track_max_missing: int = (
            track_max_missing if track_max_missing is not None else config.TRACK_MAX_MISSING
        )
        self.stable_frames: int = stable_frames if stable_frames is not None else config.STABLE_FRAMES
        self.stable_mm: float = stable_mm if stable_mm is not None else config.STABLE_MM
        self.samples_target: int = samples_target if samples_target is not None else config.SAMPLES_TARGET
        self.samples_min: int = samples_min if samples_min is not None else config.SAMPLES_MIN
        self.line_window_mm: float = line_window_mm if line_window_mm is not None else config.LINE_WINDOW_MM
        self.sample_timeout_s: float = (
            sample_timeout_s if sample_timeout_s is not None else config.SAMPLE_TIMEOUT_S
        )
        self.ocr_crops: int = ocr_crops if ocr_crops is not None else config.OCR_CROPS

        self._next_id: int = 1
        self._tracks: dict[int, Track] = {}
        self._alerted_merged_tracks: set[int] = set()
        self._pending_alerts: list[str] = []

    @property
    def roi_center_x(self) -> float:
        return self.roi.x0_mm + self.roi.w_mm / 2.0

    @property
    def tracks(self) -> dict[int, Track]:
        return self._tracks

    def pop_alerts(self) -> list[str]:
        alerts = list(self._pending_alerts)
        self._pending_alerts.clear()
        return alerts

    def _is_stable(self, track: Track, current_center: tuple[float, float]) -> bool:
        if len(track.history) < self.stable_frames:
            return False
        pts = [c for _, c in list(track.history)[-self.stable_frames :]]
        max_dist = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                if d > max_dist:
                    max_dist = d
        return max_dist < self.stable_mm

    def _is_line(self, center_mm: tuple[float, float]) -> bool:
        return abs(center_mm[0] - self.roi_center_x) <= self.line_window_mm

    def _check_trigger_condition(self, track: Track, det: Detection) -> bool:
        if not det.full_inside:
            return False

        stable = self._is_stable(track, det.center_mm)
        line = self._is_line(det.center_mm)

        if line:
            track.crossed_line = True

        if self.trigger_mode == "stable":
            return stable
        if self.trigger_mode == "line":
            return line
        if self.trigger_mode == "auto":
            return stable or line
        return False

    def add_sample(
        self,
        track_id: int,
        measurement: Measurement,
        upright_crop: NDArray[np.uint8],
    ) -> None:
        """Add a measurement sample and upright crop to a track."""
        track = self._tracks.get(track_id)
        if track is None or track.finalized:
            return

        track.samples.append(measurement)
        track.crops.append((float(measurement.sharpness), upright_crop))
        # Keep top ocr_crops sharpest crops
        track.crops.sort(key=lambda x: x[0], reverse=True)
        if len(track.crops) > self.ocr_crops:
            track.crops = track.crops[: self.ocr_crops]

    def update(
        self,
        detections: Sequence[Detection],
        t: float,
        measure_fn: Callable[[Detection], tuple[Measurement, NDArray[np.uint8]]] | None = None,
    ) -> list[Track]:
        """Update tracker state with new detections at time t.

        Optionally accepts measure_fn to automatically sample qualifying tracks.
        Returns a list of FinalizeJob-ready tracks finalized in this frame.
        """
        # Greedy nearest-centre matching within track_match_mm across all tracks (E-09)
        active_track_ids = list(self._tracks.keys())
        pairs: list[tuple[float, int, int]] = []
        for tid in active_track_ids:
            trk = self._tracks[tid]
            for d_idx, det in enumerate(detections):
                dist = float(
                    np.hypot(
                        trk.center_mm[0] - det.center_mm[0],
                        trk.center_mm[1] - det.center_mm[1],
                    )
                )
                if dist <= self.track_match_mm:
                    pairs.append((dist, tid, d_idx))

        pairs.sort(key=lambda x: x[0])
        matched_tracks: dict[int, int] = {}  # track_id -> det_idx
        matched_dets: set[int] = set()

        for _dist, tid, d_idx in pairs:
            if tid not in matched_tracks and d_idx not in matched_dets:
                matched_tracks[tid] = d_idx
                matched_dets.add(d_idx)

        # Update matched tracks
        for tid, d_idx in matched_tracks.items():
            trk = self._tracks[tid]
            det = detections[d_idx]
            trk.center_mm = det.center_mm
            trk.missing = 0
            trk.history.append((t, det.center_mm))

        # Unmatched existing tracks increment missing
        for tid in list(self._tracks.keys()):
            if tid not in matched_tracks:
                self._tracks[tid].missing += 1

        # Unmatched detections create new tracks
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                new_track = Track(
                    id=self._next_id,
                    center_mm=det.center_mm,
                    history=deque(
                        [(t, det.center_mm)],
                        maxlen=max(self.stable_frames * 2, 20),
                    ),
                    missing=0,
                    samples=[],
                    crops=[],
                    first_sample_t=None,
                    crossed_line=False,
                    finalized=False,
                )
                self._tracks[self._next_id] = new_track
                matched_tracks[self._next_id] = d_idx
                self._next_id += 1

        # Check triggers and sampling for matched tracks
        tracks_to_sample: list[tuple[Track, Detection]] = []
        for tid, d_idx in matched_tracks.items():
            trk = self._tracks[tid]
            if trk.finalized:
                continue

            det = detections[d_idx]

            # Merged detection handling: never sample, raise alert once per track
            if det.merged:
                if trk.id not in self._alerted_merged_tracks:
                    self._alerted_merged_tracks.add(trk.id)
                    self._pending_alerts.append(f"Track {trk.id}: Separate billets")
                continue

            # Check if trigger condition first holds
            if trk.first_sample_t is None:
                if self._check_trigger_condition(trk, det):
                    trk.first_sample_t = t

            # If sampling is active and detection is fully inside
            if trk.first_sample_t is not None and det.full_inside:
                tracks_to_sample.append((trk, det))

        # If measure_fn is provided, sample them immediately
        if measure_fn is not None:
            for trk, det in tracks_to_sample:
                measurement, crop = measure_fn(det)
                self.add_sample(trk.id, measurement, crop)

        # Check finalization conditions
        finalized_tracks: list[Track] = []
        for tid, trk in list(self._tracks.items()):
            if trk.finalized or trk.first_sample_t is None:
                continue

            # Find matching detection if any
            matched_det = detections[matched_tracks[tid]] if tid in matched_tracks else None

            # Determine whether any finalize condition is met:
            # 1. Target samples reached
            target_reached = len(trk.samples) >= self.samples_target

            # 2. Left line window after crossing line
            left_line_window = False
            if trk.crossed_line and matched_det is not None:
                left_line_window = not self._is_line(matched_det.center_mm)

            # 3. Track lost or left full_inside
            lost_or_left = (trk.missing > 0) or (matched_det is not None and not matched_det.full_inside)

            # 4. Timeout since first sample
            timeout = (t - trk.first_sample_t) >= self.sample_timeout_s

            should_finalize = (
                target_reached
                or (self.trigger_mode in ("line", "auto") and left_line_window)
                or lost_or_left
                or timeout
            )

            if should_finalize:
                # E-08: Require >= samples_min samples, else discard
                if len(trk.samples) >= self.samples_min:
                    trk.finalized = True
                    finalized_tracks.append(trk)
                else:
                    # Discard without logging
                    trk.finalized = True

        # Purge tracks that have been missing too long, or finalized tracks that left view
        for tid in list(self._tracks.keys()):
            trk = self._tracks[tid]
            if (trk.finalized and trk.missing > 0) or (trk.missing > self.track_max_missing):
                del self._tracks[tid]
                self._alerted_merged_tracks.discard(tid)

        return finalized_tracks
