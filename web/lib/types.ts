export const STATUSES = ["Pass", "Rework", "Fail", "Review"] as const;
export type InspectionStatus = (typeof STATUSES)[number];
export type IdSource = "ocr" | "qr" | "none";
export type DefectType = "notch" | "taper" | "bulge" | "camber";
export type SourceType = "webcam" | "url" | "file" | "synthetic";
export type TriggerMode = "auto" | "stable" | "line";
export type AlertLevel = "Fail" | "Rework" | "System" | "Review" | "CALIB_DRIFT";
export type LogFileStatus = "ok" | "locked" | "error";
export type StreamView = "annotated" | "rectified" | "raw";
export type UnixSeconds = number;

export interface Spec {
  id: string;
  name: string;
  nominal_length_mm: number;
  nominal_width_mm: number;
  nominal_height_mm: number | null;
  tol_length_mm: number;
  tol_width_mm: number;
  cs_var_warn_pct: number;
  cs_var_fail_pct: number;
  notch_min_mm: number;
  camber_max_mm: number;
  taper_max_mm: number;
  id_template: string;
  min_area_factor: number;
  max_area_factor: number;
  active: boolean;
}
export type SpecUpsert = Omit<Spec, "active">;

export interface Override {
  billet_id: string | null;
  status: InspectionStatus | null;
  note: string;
  at: UnixSeconds;
}

export interface Inspection {
  id: number;
  ts: string;
  billet_id: string | null;
  id_source: IdSource;
  ocr_text: string | null;
  ocr_confidence: number | null;
  ocr_agreement: number | null;
  qr_text: string | null;
  id_mismatch: boolean;
  length_mm: number;
  width_mm: number;
  height_mm: number | null;
  length_dev_mm: number;
  width_dev_mm: number;
  width_variation_pct: number;
  cs_var_pct?: number;
  taper_mm: number;
  camber_mm: number;
  min_width_mm: number;
  max_width_mm: number;
  width_profile_mm: number[];
  defects: DefectType[];
  status: InspectionStatus;
  auto_status: InspectionStatus;
  reasons: string[];
  spec_id: string;
  n_samples: number;
  angle_deg: number;
  latency_ms: number;
  snapshot_url: string;
  source: SourceType;
  track_id: number;
  override: Override | null;
  created_at: UnixSeconds;
}
export interface InspectionPatch {
  billet_id?: string | null;
  status?: InspectionStatus | null;
  note: string;
}
export interface InspectionList {
  items: Inspection[];
  total: number;
}
export interface InspectionFilters {
  status?: InspectionStatus;
  billet_id?: string;
  spec_id?: string;
  since?: string;
  limit?: number;
  offset?: number;
}

export interface Alert {
  id: number;
  inspection_id: number | null;
  ts: string;
  level: AlertLevel;
  message: string;
  acknowledged: boolean;
  created_at: UnixSeconds;
}

export interface Roi {
  x0_mm: number;
  y0_mm: number;
  w_mm: number;
  h_mm: number;
}
export interface VerifyRequest {
  known_length_mm: number;
  known_width_mm?: number;
}
export interface VerifyResult {
  known_length_mm: number;
  measured_length_mm: number;
  length_error_pct: number;
  known_width_mm: number | null;
  measured_width_mm: number | null;
  width_error_pct: number | null;
  ok: boolean;
  at: UnixSeconds;
}
export interface CalibrationState {
  calibrated: boolean;
  has_background: boolean;
  has_intrinsics: boolean;
  marker_mm: number;
  image_px_per_mm: number | null;
  rect_px_per_mm: number;
  roi: Roi;
  reprojection_error_px: number | null;
  verify: VerifyResult | null;
  drift_mm: number | null;
  drift_ok: boolean;
  created_at: UnixSeconds | null;
}
export interface MarkerResult {
  found: boolean;
  marker_id: number;
  corners_px: number[][];
  image_px_per_mm: number;
  reprojection_error_px: number;
  calibration: CalibrationState;
}

export interface SourceRequest {
  type: SourceType;
  value: string;
}
export interface SourceInfo {
  type: SourceType;
  value: string;
  frame_width: number | null;
  frame_height: number | null;
}
export interface TriggerModeRequest {
  mode: TriggerMode;
}
export interface StationStatus {
  source: SourceInfo;
  camera_ok: boolean;
  calibrated: boolean;
  has_background: boolean;
  paused: boolean;
  trigger_mode: TriggerMode;
  active_spec: Spec;
  fps_capture: number;
  fps_process: number;
  log_status: LogFileStatus;
  ocr_ready: boolean;
}
export interface Health {
  ok: boolean;
  db: boolean;
  camera_ok: boolean;
  calibrated: boolean;
  ocr_ready: boolean;
}

export interface Metrics {
  fps_capture: number;
  fps_process: number;
  process_ms_p50: number;
  process_ms_p95: number;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  inspections_total: number;
  by_status: Record<InspectionStatus, number>;
  throughput_per_min: number;
  ocr_read_rate: number | null;
  queue_depth: number;
  dropped_jobs: number;
  uptime_s: number;
}
export interface PropAccuracy {
  prop_id: string;
  gt_length_mm: number;
  gt_width_mm: number;
  n: number;
  mean_length_mm: number;
  mean_width_mm: number;
  length_error_pct: number;
  width_error_pct: number;
  max_abs_error_pct: number;
  ocr_correct_rate: number | null;
}
export interface EvalReal {
  n_inspections: number;
  n_props_seen: number;
  length_mae_pct: number;
  length_p95_pct: number;
  width_mae_pct: number;
  width_p95_pct: number;
  within_1pct_rate: number;
  ocr_accuracy: number | null;
  ocr_n: number;
  read_rate: number;
  props: PropAccuracy[];
}
export interface SyntheticVariant {
  n: number;
  length_mae_pct: number;
  length_max_pct: number;
  width_mae_pct: number;
  width_max_pct: number;
  ocr_accuracy: number | null;
}
export interface SyntheticBench {
  n: number;
  generated_at: UnixSeconds;
  overall: SyntheticVariant;
  variants: Record<string, SyntheticVariant>;
  defect_accuracy: number;
  mean_process_ms: number;
}
export interface EvalResponse {
  real: EvalReal | null;
  synthetic: SyntheticBench | null;
}

export interface ApiErrorBody {
  code:
    | "NOT_FOUND"
    | "BAD_REQUEST"
    | "MARKER_NOT_FOUND"
    | "NO_OBJECT"
    | "NOT_CALIBRATED"
    | "CAMERA_UNAVAILABLE"
    | "INTERNAL";
  message: string;
  hint: string | null;
}

// ── WebSocket messages (server → client) ─────────────
export interface StatsMessage {
  type: "stats";
  fps_capture: number;
  fps_process: number;
  process_ms_p95: number;
  tracks: number;
  camera_ok: boolean;
  calibrated: boolean;
  paused: boolean;
  log_status: LogFileStatus;
  server_time: UnixSeconds;
}

export type WsMessage =
  | StatsMessage
  | { type: "inspection"; inspection: Inspection }
  | { type: "alert"; alert: Alert }
  | { type: "calibration"; calibration: CalibrationState }
  | { type: "status"; status: StationStatus };

function isRecord(val: unknown): val is Record<string, unknown> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

export function isWsMessage(x: unknown): x is WsMessage {
  if (!isRecord(x)) {
    return false;
  }
  const type = x["type"];
  if (typeof type !== "string") {
    return false;
  }

  if (type === "stats") {
    return (
      typeof x["fps_capture"] === "number" &&
      typeof x["fps_process"] === "number" &&
      typeof x["process_ms_p95"] === "number" &&
      typeof x["tracks"] === "number" &&
      typeof x["camera_ok"] === "boolean" &&
      typeof x["calibrated"] === "boolean" &&
      typeof x["paused"] === "boolean" &&
      typeof x["log_status"] === "string" &&
      typeof x["server_time"] === "number"
    );
  }

  if (type === "inspection") {
    return isRecord(x["inspection"]);
  }

  if (type === "alert") {
    return isRecord(x["alert"]);
  }

  if (type === "calibration") {
    return isRecord(x["calibration"]);
  }

  if (type === "status") {
    return isRecord(x["status"]);
  }

  return false;
}
