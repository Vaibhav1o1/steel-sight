from __future__ import annotations

import logging
import queue
import threading
import time

from billetvision.logging_io import InspectionLogger
from billetvision.schemas import Inspection
from billetvision.vision.decide import decide
from billetvision.vision.idparse import read_id
from billetvision.vision.types import FinalizeJob

logger = logging.getLogger(__name__)


class OcrWorkerThread(threading.Thread):
    def __init__(
        self,
        job_queue: queue.Queue[FinalizeJob],
        system_alerts: queue.Queue[str],
        event_bus,
        runtime_state,
        db_logger: InspectionLogger,
    ):
        super().__init__(name="ocr-worker", daemon=True)
        self._queue = job_queue
        self._system_alerts = system_alerts
        self._bus = event_bus
        self._state = runtime_state
        self._db_logger = db_logger
        self.stop_event = threading.Event()

    def run(self) -> None:
        logger.info("OCR worker thread started")
        while not self.stop_event.is_set():
            self._drain_system_alerts()
            try:
                job = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._process_job(job)
            except Exception:
                logger.exception(
                    "Error processing FinalizeJob for track %d",
                    job.track_id,
                )

        logger.info("OCR worker thread stopped")

    def _drain_system_alerts(self) -> None:
        """Drain system alerts from the processing thread."""
        while True:
            try:
                message = self._system_alerts.get_nowait()
            except queue.Empty:
                return
            # Publish as a contract-shaped alert event
            alert_event = {
                "type": "alert",
                "alert": {
                    "level": "System",
                    "message": message,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "inspection_id": None,
                },
            }
            self._bus.publish(alert_event)
            logger.info("System alert: %s", message)

    def _process_job(self, job: FinalizeJob) -> None:
        logger.debug("Worker received track %d", job.track_id)

        # 1. Measurement aggregate
        from billetvision.vision.track import aggregate_measurements

        agg_meas = aggregate_measurements(job.samples)

        # 2. Defects check
        from billetvision.vision.defects import detect_defects

        defects = detect_defects(agg_meas, job.spec)

        # 3. OCR and QR on best crops
        from billetvision.vision.ocr import read as ocr_read
        from billetvision.vision.qr import read_qr

        t_id_start = time.monotonic()
        id_res = read_id(
            list(job.crops),
            ocr_fn=ocr_read,
            qr_fn=read_qr,
            template=job.spec.id_template,
        )
        t_id = (time.monotonic() - t_id_start) * 1000.0

        # 4. Decide final status
        calib_drift = self._state.calib_drift_alert
        borderline = False

        t_decide_start = time.monotonic()
        decision = decide(
            measurement=agg_meas,
            defects=defects,
            spec=job.spec,
            id_result=id_res,
            id_mismatch=id_res.id_mismatch,
            ocr_text=id_res.ocr_text,
            qr_text=id_res.qr_text,
            calib_drift=calib_drift,
            borderline=borderline,
        )
        t_decide = (time.monotonic() - t_decide_start) * 1000.0

        # 5. Build Inspection record
        now = time.time()
        ts_str = (
            time.strftime("%Y-%m-%dT%H:%M:%S")
            + f".{int((now % 1) * 1000):03d}Z"
        )
        inspection_id = int(now * 1000) % 2147483647
        latency = (time.monotonic() - job.first_sample_t) * 1000.0

        inspection = Inspection(
            id=inspection_id,
            ts=ts_str,
            billet_id=id_res.billet_id,
            id_source=id_res.id_source,
            ocr_text=id_res.ocr_text,
            ocr_confidence=id_res.ocr_confidence,
            ocr_agreement=id_res.ocr_agreement,
            qr_text=id_res.qr_text,
            id_mismatch=id_res.id_mismatch,
            length_mm=agg_meas.length_mm,
            width_mm=agg_meas.width_mm,
            height_mm=None,
            length_dev_mm=(
                agg_meas.length_mm - job.spec.nominal_length_mm
            ),
            width_dev_mm=(
                agg_meas.width_mm - job.spec.nominal_width_mm
            ),
            width_variation_pct=defects.cs_var_pct,
            taper_mm=defects.taper_mm,
            camber_mm=defects.camber_mm,
            min_width_mm=defects.min_width_mm,
            max_width_mm=defects.max_width_mm,
            width_profile_mm=list(agg_meas.width_profile_mm),
            defects=list(defects.defects),
            status=decision.status,
            auto_status=decision.status,
            reasons=list(decision.reasons),
            spec_id=job.spec.id,
            n_samples=len(job.samples),
            angle_deg=agg_meas.angle_deg,
            latency_ms=latency,
            snapshot_url=f"/inspections/{inspection_id}/snapshot.jpg",
            source=job.source,
            track_id=job.track_id,
            override=None,
            created_at=now,
        )

        # T21 Evidence Generation
        from billetvision.runtime.evidence import generate_evidence

        if job.crops:
            evidence_url = generate_evidence(inspection, job.crops[0])
            if evidence_url:
                # Prompt says: "Saved under evidence/<record_id>.jpg and referenced in the record."
                inspection.snapshot_url = evidence_url
        else:
            # If we somehow have no crops but it failed, fallback logic
            pass

        # Also save the original full snapshot jpeg just in case the API needs it?
        # Let's save the raw snapshot to disk so /inspections/{id}/snapshot.jpg works.
        import os

        from billetvision import config
        snap_dir = os.path.join(config.SNAPSHOT_DIR)
        os.makedirs(snap_dir, exist_ok=True)
        with open(os.path.join(snap_dir, f"{inspection_id}.jpg"), "wb") as f:
            f.write(job.snapshot_jpeg)

        # Enqueue for DB/Excel write
        t_write_start = time.monotonic()
        self._db_logger.log_inspection(inspection.model_dump())
        t_write = (time.monotonic() - t_write_start) * 1000.0

        with self._state.lock:
            self._state.stage_timings["id"] = t_id
            self._state.stage_timings["decide"] = t_decide
            self._state.stage_timings["write"] = t_write

        # Publish event
        self._bus.publish(
            {
                "type": "inspection",
                "inspection": inspection.model_dump(),
            }
        )
