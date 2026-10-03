import type {
  Alert,
  CalibrationState,
  EvalResponse,
  Health,
  Inspection,
  InspectionFilters,
  InspectionList,
  InspectionPatch,
  InspectionStatus,
  MarkerResult,
  Metrics,
  Roi,
  SourceRequest,
  Spec,
  SpecUpsert,
  StationStatus,
  StreamView,
  TriggerModeRequest,
  VerifyRequest,
  VerifyResult,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly hint: string | null;

  constructor(code: string, message: string, status: number, hint: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.hint = hint;
  }
}

function isRecord(val: unknown): val is Record<string, unknown> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    throw new ApiError("CAMERA_UNAVAILABLE", msg, 503, null);
  }

  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null);
    if (isRecord(data)) {
      const detail = data["detail"];
      if (isRecord(detail)) {
        const code = typeof detail["code"] === "string" ? detail["code"] : "INTERNAL";
        const message =
          typeof detail["message"] === "string" ? detail["message"] : res.statusText || "Request failed";
        const hint = typeof detail["hint"] === "string" ? detail["hint"] : null;
        throw new ApiError(code, message, res.status, hint);
      }
      if (typeof detail === "string") {
        throw new ApiError("BAD_REQUEST", detail, res.status, null);
      }
    }
    throw new ApiError("INTERNAL", res.statusText || "Request failed", res.status, null);
  }

  const result: T = await res.json();
  return result;
}

// ── URL Helpers ─────────────────────────────────────
export function streamUrl(view: StreamView = "annotated"): string {
  return `${API_BASE}/stream.mjpg?view=${encodeURIComponent(view)}`;
}

export function snapshotUrl(view: StreamView = "annotated"): string {
  return `${API_BASE}/snapshot.jpg?view=${encodeURIComponent(view)}`;
}

export function exportUrl(
  format: "xlsx" | "csv" | "json",
  filters?: { status?: InspectionStatus; since?: string },
): string {
  const params = new URLSearchParams();
  if (filters?.status) {
    params.set("status", filters.status);
  }
  if (filters?.since) {
    params.set("since", filters.since);
  }
  const query = params.toString();
  return `${API_BASE}/export/${format}${query ? `?${query}` : ""}`;
}

export function inspectionSnapshotUrl(id: number): string {
  return `${API_BASE}/inspections/${id}/snapshot.jpg`;
}

export function wsUrl(): string {
  return WS_BASE;
}

// ── Endpoints (03 §5 rows 1–2, 4–22) ────────────────

// Row 1: GET /health
export function getHealth(): Promise<Health> {
  return requestJson<Health>("/health");
}

// Row 2: GET /status
export function getStatus(): Promise<StationStatus> {
  return requestJson<StationStatus>("/status");
}

// Row 4: GET /snapshot.jpg
export async function getSnapshot(view: StreamView = "annotated"): Promise<Blob> {
  const res = await fetch(snapshotUrl(view));
  if (!res.ok) {
    throw new ApiError("CAMERA_UNAVAILABLE", "Failed to retrieve snapshot", res.status, null);
  }
  return res.blob();
}

// Row 5: POST /source
export function setSource(body: SourceRequest): Promise<StationStatus> {
  return requestJson<StationStatus>("/source", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Row 6: POST /control/pause & POST /control/resume
export function pauseStation(): Promise<StationStatus> {
  return requestJson<StationStatus>("/control/pause", {
    method: "POST",
  });
}

export function resumeStation(): Promise<StationStatus> {
  return requestJson<StationStatus>("/control/resume", {
    method: "POST",
  });
}

// Row 7: POST /control/trigger-mode
export function setTriggerMode(body: TriggerModeRequest): Promise<StationStatus> {
  return requestJson<StationStatus>("/control/trigger-mode", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Row 8: GET /calibration
export function getCalibration(): Promise<CalibrationState> {
  return requestJson<CalibrationState>("/calibration");
}

// Row 9: POST /calibration/marker
export function detectMarker(): Promise<MarkerResult> {
  return requestJson<MarkerResult>("/calibration/marker", {
    method: "POST",
  });
}

// Row 10: POST /calibration/background
export function captureBackground(): Promise<CalibrationState> {
  return requestJson<CalibrationState>("/calibration/background", {
    method: "POST",
  });
}

// Row 11: POST /calibration/verify
export function verifyCalibration(body: VerifyRequest): Promise<VerifyResult> {
  return requestJson<VerifyResult>("/calibration/verify", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// Row 12: PUT /calibration/roi
export function setRoi(body: Roi): Promise<CalibrationState> {
  return requestJson<CalibrationState>("/calibration/roi", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// Row 13: DELETE /calibration
export function resetCalibration(): Promise<CalibrationState> {
  return requestJson<CalibrationState>("/calibration", {
    method: "DELETE",
  });
}

// Row 14: GET /specs, POST /specs, PUT /specs/{id}, POST /specs/{id}/activate
export function getSpecs(): Promise<Spec[]> {
  return requestJson<Spec[]>("/specs");
}

export function createSpec(body: SpecUpsert): Promise<Spec> {
  return requestJson<Spec>("/specs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSpec(id: string, body: SpecUpsert): Promise<Spec> {
  return requestJson<Spec>(`/specs/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function activateSpec(id: string): Promise<Spec> {
  return requestJson<Spec>(`/specs/${encodeURIComponent(id)}/activate`, {
    method: "POST",
  });
}

// Row 15: GET /inspections
export function getInspections(filters?: InspectionFilters): Promise<InspectionList> {
  const params = new URLSearchParams();
  if (filters?.status) {
    params.set("status", filters.status);
  }
  if (filters?.billet_id) {
    params.set("billet_id", filters.billet_id);
  }
  if (filters?.spec_id) {
    params.set("spec_id", filters.spec_id);
  }
  if (filters?.since) {
    params.set("since", filters.since);
  }
  if (typeof filters?.limit === "number") {
    params.set("limit", filters.limit.toString());
  }
  if (typeof filters?.offset === "number") {
    params.set("offset", filters.offset.toString());
  }
  const query = params.toString();
  return requestJson<InspectionList>(query ? `/inspections?${query}` : "/inspections");
}

// Row 16: GET /inspections/{id}
export function getInspection(id: number): Promise<Inspection> {
  return requestJson<Inspection>(`/inspections/${id}`);
}

// Row 18: PATCH /inspections/{id}
export function patchInspection(id: number, body: InspectionPatch): Promise<Inspection> {
  return requestJson<Inspection>(`/inspections/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// Row 19: GET /alerts, POST /alerts/{id}/ack
export function getAlerts(limit: number = 50): Promise<Alert[]> {
  return requestJson<Alert[]>(`/alerts?limit=${limit}`);
}

export function ackAlert(id: number): Promise<Alert> {
  return requestJson<Alert>(`/alerts/${id}/ack`, {
    method: "POST",
  });
}

// Row 20: GET /export
export async function exportInspections(
  format: "xlsx" | "csv" | "json",
  filters?: { status?: InspectionStatus; since?: string },
): Promise<Blob> {
  const url = exportUrl(format, filters);
  const res = await fetch(url);
  if (!res.ok) {
    throw new ApiError("BAD_REQUEST", "Failed to export inspections", res.status, null);
  }
  return res.blob();
}

// Row 21: GET /metrics
export function getMetrics(): Promise<Metrics> {
  return requestJson<Metrics>("/metrics");
}

// Row 22: GET /eval
export function getEval(): Promise<EvalResponse> {
  return requestJson<EvalResponse>("/eval");
}

// ── Upload Inspection ──────────────────────────────
export async function uploadImage(
  file: File,
  stationCamera: boolean = false,
): Promise<import("./upload_types").UploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const url = `${API_BASE}/inspect/image${stationCamera ? "?station_camera=true" : ""}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      body: formData,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    throw new ApiError("CAMERA_UNAVAILABLE", msg, 503, null);
  }

  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null);
    if (isRecord(data)) {
      const detail = data["detail"];
      if (isRecord(detail)) {
        const code = typeof detail["code"] === "string" ? detail["code"] : "INTERNAL";
        const message =
          typeof detail["message"] === "string" ? detail["message"] : res.statusText;
        const hint = typeof detail["hint"] === "string" ? detail["hint"] : null;
        throw new ApiError(code, message, res.status, hint);
      }
    }
    throw new ApiError("BAD_REQUEST", "Failed to upload image", res.status, null);
  }

  return res.json();
}

export function uploadedImageUrl(imageId: string): string {
  return `${API_BASE}/inspect/image/${imageId}.jpg`;
}

export function getTestDataset(): Promise<import("./upload_types").TestDatasetImageItem[]> {
  return requestJson<import("./upload_types").TestDatasetImageItem[]>("/inspect/test-dataset");
}

export function inspectTestDatasetImage(
  imageName: string,
): Promise<import("./upload_types").TestInspectResponse> {
  return requestJson<import("./upload_types").TestInspectResponse>(
    `/inspect/test-dataset/${encodeURIComponent(imageName)}`,
    { method: "POST" },
  );
}

// ── Analytics ──────────────────────────────────────
export function getStatusSeries(
  params?: import("./analytics_types").StatusSeriesParams,
): Promise<import("./analytics_types").StatusSeriesResponse> {
  const q = new URLSearchParams();
  if (params?.mode) q.set("mode", params.mode);
  if (params?.basis) q.set("basis", params.basis);
  if (params?.source) q.set("source", params.source);
  if (typeof params?.bucket_size === "number") q.set("bucket_size", params.bucket_size.toString());
  if (params?.interval) q.set("interval", params.interval);
  if (params?.since) q.set("since", params.since);
  const query = q.toString();
  return requestJson<import("./analytics_types").StatusSeriesResponse>(
    query ? `/analytics/status-series?${query}` : "/analytics/status-series",
  );
}

