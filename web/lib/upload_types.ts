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
  qr_detected: boolean;
  length_mm: number | null;
  width_mm: number | null;
  nominal_length_mm: number | null;
  nominal_width_mm: number | null;
  tol_length_mm: number | null;
  tol_width_mm: number | null;
  length_dev_mm: number | null;
  length_abs_dev_mm: number | null;
  length_passed: boolean | null;
  width_dev_mm: number | null;
  width_abs_dev_mm: number | null;
  width_passed: boolean | null;
  length_px: number | null;
  width_px: number | null;
  defects: string[];
  defect_type: string | null;
  defect_size_mm: number | null;
  reasons: string[];
  annotated_url: string;
  processing_time_ms: number;
}

export interface TestDatasetImageItem {
  filename: string;
  variant: string;
  expected_status: string;
  billet_id: string | null;
  length_mm: number;
  width_mm: number;
  defect: string | null;
  defect_size_mm: number;
  qr: boolean;
}

export interface GroundTruthBillet {
  id_text: string | null;
  length_mm: number | null;
  width_mm: number | null;
  qr: boolean | null;
  defect: string | null;
  defect_size_mm: number | null;
  expected_status: string | null;
}

export interface GroundTruthComparison {
  status_match: boolean | null;
  length_delta_mm: number | null;
  width_delta_mm: number | null;
  defect_type_match: boolean | null;
  defect_size_delta_mm: number | null;
  id_match: boolean | null;
  qr_match: boolean | null;
}

export interface TestInspectResponse {
  system_result: UploadResult;
  ground_truth: GroundTruthBillet | null;
  comparison: GroundTruthComparison | null;
  is_test_dataset: boolean;
}
