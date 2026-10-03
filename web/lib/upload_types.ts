import type { InspectionStatus } from "./types";

export interface UploadCalibrationInfo {
  calibrated: boolean;
  source: "marker" | "station" | "uncalibrated";
  px_per_mm: number | null;
  warning: string | null;
}

export interface UploadResult {
  image_id: string;
  status: InspectionStatus;
  calibrated: boolean;
  calibration: UploadCalibrationInfo;
  billet_id: string | null;
  id_source: string;
  ocr_confidence: number | null;
  length_mm: number | null;
  width_mm: number | null;
  length_px: number | null;
  width_px: number | null;
  defects: string[];
  reasons: string[];
  annotated_url: string;
  processing_time_ms: number;
}
