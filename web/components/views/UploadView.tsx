"use client";

import * as React from "react";
import { useState, useRef, useEffect, useMemo } from "react";
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  FileImage,
  Loader2,
  Maximize2,
  Eye,
  Layers,
  Sparkles,
  Check,
  Sliders,
  ShieldAlert,
  Cpu,
  Hash,
  QrCode,
  Ruler,
} from "lucide-react";
import {
  uploadImage,
  uploadedImageUrl,
  getTestDataset,
  inspectTestDatasetImage,
  ApiError,
} from "@/lib/api";
import type {
  UploadResult,
  TestDatasetImageItem,
  TestInspectResponse,
} from "@/lib/upload_types";
import { STATUS_STYLES } from "@/lib/status";
import { cn } from "cn";

type InspectionTab = "manual" | "dataset";

export function UploadView() {
  const [activeTab, setActiveTab] = useState<InspectionTab>("manual");

  // Manual Upload State
  const [file, setFile] = useState<File | null>(null);
  const [stationCamera, setStationCamera] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [testInspectResponse, setTestInspectResponse] = useState<TestInspectResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // View state
  const [imageViewMode, setImageViewMode] = useState<"annotated" | "raw">("annotated");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Test Dataset State
  const [datasetImages, setDatasetImages] = useState<TestDatasetImageItem[]>([]);
  const [selectedVariant, setSelectedVariant] = useState<string>("all");
  const [selectedDatasetImage, setSelectedDatasetImage] = useState<string | null>(null);

  // Derive raw preview object URL
  const rawPreviewUrl = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  // Clean raw image object URL on change
  useEffect(() => {
    return () => {
      if (rawPreviewUrl) URL.revokeObjectURL(rawPreviewUrl);
    };
  }, [rawPreviewUrl]);

  // Load dataset list on tab switch
  useEffect(() => {
    let isMounted = true;
    if (activeTab === "dataset" && datasetImages.length === 0) {
      getTestDataset()
        .then((items) => {
          if (isMounted) {
            setDatasetImages(items);
            if (items.length > 0 && !selectedDatasetImage) {
              setSelectedDatasetImage(items[0]?.filename ?? null);
            }
          }
        })
        .catch((err) => {
          console.error("Failed to load test dataset:", err);
        });
    }
    return () => {
      isMounted = false;
    };
  }, [activeTab, datasetImages.length, selectedDatasetImage]);

  const handleFileSelect = (selectedFile: File) => {
    setFile(selectedFile);
    setResult(null);
    setTestInspectResponse(null);
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const dropped = e.dataTransfer.files[0];
      if (dropped) {
        handleFileSelect(dropped);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleInspectManual = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);
    setTestInspectResponse(null);
    try {
      const res = await uploadImage(file, stationCamera);
      setResult(res);
      setImageViewMode("annotated");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}${err.hint ? ` (${err.hint})` : ""}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to process image");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleInspectDatasetImage = async (imgName: string) => {
    setSelectedDatasetImage(imgName);
    setLoading(true);
    setError(null);
    try {
      const res = await inspectTestDatasetImage(imgName);
      setTestInspectResponse(res);
      setResult(res.system_result);
      setImageViewMode("annotated");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`${err.code}: ${err.message}${err.hint ? ` (${err.hint})` : ""}`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to inspect test dataset image");
      }
    } finally {
      setLoading(false);
    }
  };

  // Variants list
  const variants = useMemo(() => {
    const set = new Set<string>();
    datasetImages.forEach((img) => set.add(img.variant));
    return ["all", ...Array.from(set)];
  }, [datasetImages]);

  const filteredDatasetImages = useMemo(() => {
    if (selectedVariant === "all") return datasetImages;
    return datasetImages.filter((img) => img.variant === selectedVariant);
  }, [datasetImages, selectedVariant]);

  const statusStyle = result ? STATUS_STYLES[result.status] : null;

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
      {/* ── Top Header & Mode Bar ────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              OPTICAL QA INSPECTION CONSOLE
            </h1>
            <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary font-mono font-medium border border-primary/20">
              STATION UPLOAD
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Sub-pixel metric measurement, defect profiling, and ground-truth validation workstation.
          </p>
        </div>

        {/* Tab Selector */}
        <div className="flex items-center bg-muted p-1 rounded-lg border">
          <button
            onClick={() => {
              setActiveTab("manual");
              setError(null);
            }}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5",
              activeTab === "manual"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <UploadCloud className="w-3.5 h-3.5" />
            Manual Upload
          </button>
          <button
            onClick={() => {
              setActiveTab("dataset");
              setError(null);
            }}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5",
              activeTab === "dataset"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Layers className="w-3.5 h-3.5" />
            Test Dataset (Code_Utsava)
          </button>
        </div>
      </div>

      {/* ── Test Dataset Selector Drawer (if active) ───────────────────── */}
      {activeTab === "dataset" && (
        <div className="bg-card border rounded-xl p-4 space-y-3 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                TEST DATASET MODE
              </span>
              <span className="text-xs text-muted-foreground">
                Authoritative dataset with ground-truth verification (scenes.json / camera.json).
              </span>
            </div>
            {datasetImages.length === 0 && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading scenes...
              </div>
            )}
          </div>

          {/* Variant Filter Buttons */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-xs text-muted-foreground font-mono mr-1">Variant:</span>
            {variants.map((v) => (
              <button
                key={v}
                onClick={() => setSelectedVariant(v)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded-md font-mono transition-colors uppercase",
                  selectedVariant === v
                    ? "bg-primary text-primary-foreground font-semibold"
                    : "bg-muted text-muted-foreground hover:bg-muted/80",
                )}
              >
                {v}
              </button>
            ))}
          </div>

          {/* Image Horizontal List / Carousel */}
          <div className="flex gap-2 overflow-x-auto pb-2 pt-1 scrollbar-thin">
            {filteredDatasetImages.map((img) => {
              const isSelected = selectedDatasetImage === img.filename;
              const expectedStyle = STATUS_STYLES[img.expected_status as keyof typeof STATUS_STYLES] || STATUS_STYLES.Review;
              return (
                <button
                  key={img.filename}
                  onClick={() => handleInspectDatasetImage(img.filename)}
                  disabled={loading}
                  className={cn(
                    "shrink-0 w-44 text-left p-2.5 rounded-lg border transition-all flex flex-col justify-between text-xs space-y-1.5",
                    isSelected
                      ? "border-primary bg-primary/5 ring-1 ring-primary shadow-sm"
                      : "border-border bg-background hover:border-muted-foreground/30",
                    loading && "opacity-60 cursor-not-allowed",
                  )}
                >
                  <div className="flex items-center justify-between w-full">
                    <span className="font-mono font-bold truncate max-w-[90px]">{img.filename}</span>
                    <span
                      className="px-1.5 py-0.2 rounded font-mono text-[10px] font-semibold uppercase"
                      style={{ color: expectedStyle.hex, backgroundColor: `${expectedStyle.hex}15` }}
                    >
                      {img.expected_status}
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono">
                    <div>ID: {img.billet_id ?? "None"}</div>
                    <div className="flex items-center justify-between">
                      <span>{img.length_mm.toFixed(1)}×{img.width_mm.toFixed(1)}mm</span>
                      {img.defect && (
                        <span className="text-destructive font-medium uppercase text-[10px]">
                          {img.defect}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Main Workstation Layout ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ── LEFT COLUMN: Image Evidence & Controls ───────────────────── */}
        <div className="lg:col-span-6 space-y-4">
          {/* Upload Dropzone (if manual tab) */}
          {activeTab === "manual" && (
            <div className="bg-card border rounded-xl p-4 space-y-3">
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors flex flex-col items-center justify-center min-h-[140px]",
                  isDragOver ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40",
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      const f = e.target.files[0];
                      if (f) handleFileSelect(f);
                    }
                  }}
                />
                <UploadCloud className="w-8 h-8 text-muted-foreground mb-2" />
                <div className="text-xs font-medium">
                  {file ? (
                    <span className="text-primary font-mono">{file.name}</span>
                  ) : (
                    <span>Drag & drop billet inspection image, or <span className="text-primary underline">browse</span></span>
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">JPEG/PNG up to 15 MB</p>
              </div>

              {/* Station Camera Toggle & Inspect Trigger */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground select-none">
                  <input
                    type="checkbox"
                    checked={stationCamera}
                    onChange={(e) => setStationCamera(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary w-4 h-4"
                  />
                  <span>Station camera geometry (use active homography if marker absent)</span>
                </label>

                <button
                  onClick={handleInspectManual}
                  disabled={!file || loading}
                  className={cn(
                    "px-4 py-2 text-xs font-semibold rounded-lg font-mono flex items-center justify-center gap-2 shadow-sm transition-all",
                    file && !loading
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-muted text-muted-foreground cursor-not-allowed",
                  )}
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      INSPECTING...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      RUN INSPECTION
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="bg-destructive/15 border-l-4 border-destructive p-3 rounded-md text-xs text-destructive flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span className="font-mono">{error}</span>
            </div>
          )}

          {/* Image Evidence Canvas */}
          <div className="bg-card border rounded-xl overflow-hidden shadow-sm">
            {/* Image Header & View Toggles */}
            <div className="px-4 py-2.5 bg-muted/40 border-b flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 font-semibold">
                <FileImage className="w-4 h-4 text-muted-foreground" />
                <span>IMAGE EVIDENCE</span>
                {result && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-normal">
                    {result.image_id.slice(0, 8)}...
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {result && (
                  <div className="flex items-center bg-background rounded-md border p-0.5">
                    <button
                      onClick={() => setImageViewMode("annotated")}
                      className={cn(
                        "px-2 py-1 text-[11px] rounded transition-all flex items-center gap-1",
                        imageViewMode === "annotated"
                          ? "bg-muted font-bold text-foreground"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <Eye className="w-3 h-3" /> Annotated
                    </button>
                    <button
                      onClick={() => setImageViewMode("raw")}
                      className={cn(
                        "px-2 py-1 text-[11px] rounded transition-all flex items-center gap-1",
                        imageViewMode === "raw"
                          ? "bg-muted font-bold text-foreground"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <Layers className="w-3 h-3" /> Raw
                    </button>
                  </div>
                )}
                {result && (
                  <button
                    onClick={() => setIsFullscreen(!isFullscreen)}
                    title="Toggle Expanded View"
                    className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                  >
                    <Maximize2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Image Display */}
            <div className={cn("relative bg-black flex items-center justify-center min-h-[300px]", isFullscreen && "min-h-[500px]")}>
              {loading ? (
                <div className="flex flex-col items-center gap-2 text-muted-foreground text-xs font-mono py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-primary" />
                  <span>MEASURING & PROFILING IMAGE...</span>
                </div>
              ) : result ? (
                <img
                  src={
                    imageViewMode === "annotated"
                      ? uploadedImageUrl(result.image_id)
                      : (rawPreviewUrl || (selectedDatasetImage ? `/inspect/image/${result.image_id}.jpg` : uploadedImageUrl(result.image_id)))
                  }
                  alt="Billet Inspection Evidence"
                  className="max-h-[540px] w-full object-contain"
                />
              ) : rawPreviewUrl ? (
                <img
                  src={rawPreviewUrl}
                  alt="Raw upload preview"
                  className="max-h-[360px] w-full object-contain opacity-75"
                />
              ) : (
                <div className="text-center p-8 text-muted-foreground text-xs space-y-2">
                  <FileImage className="w-10 h-10 mx-auto opacity-30" />
                  <p>No inspection image loaded</p>
                  <p className="text-[11px] text-muted-foreground/70">
                    Upload an image or select a test scene to begin QA analysis
                  </p>
                </div>
              )}
            </div>

            {/* Technical Calibration & Latency Metadata Bar */}
            {result && (
              <div className="px-4 py-2 bg-muted/30 border-t flex flex-wrap items-center justify-between text-[11px] font-mono text-muted-foreground gap-2">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1">
                    <Cpu className="w-3 h-3" />
                    Calibration:
                    <strong className={cn("font-medium", result.calibrated ? "text-emerald-500" : "text-amber-500")}>
                      {result.calibration.source === "marker"
                        ? `Marker Calibrated (${result.calibration.px_per_mm?.toFixed(2)} px/mm)`
                        : result.calibration.source === "station"
                        ? "Station Active Geometry"
                        : "Uncalibrated (Pixel Only)"}
                    </strong>
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span>Latency: <strong>{result.processing_time_ms.toFixed(0)} ms</strong></span>
                  {result.calibration.warning && (
                    <span className="text-amber-500/90 text-[10px]" title={result.calibration.warning}>
                      ⚠ Plane notice
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT COLUMN: Industrial QA Decision Console ─────────────── */}
        <div className="lg:col-span-6 space-y-4">
          {result ? (
            <>
              {/* 1. Decision Status Card */}
              <div
                className="bg-card border-2 rounded-xl p-4 space-y-3 shadow-sm transition-all"
                style={{ borderColor: statusStyle?.hex }}
              >
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <span className="text-[10px] uppercase font-mono font-bold tracking-wider text-muted-foreground">
                      FINAL INSPECTION DECISION
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        className="text-2xl font-black font-mono tracking-tight"
                        style={{ color: statusStyle?.hex }}
                      >
                        {result.status.toUpperCase()}
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded font-mono font-bold uppercase"
                        style={{ backgroundColor: `${statusStyle?.hex}20`, color: statusStyle?.hex }}
                      >
                        {result.calibrated ? "METRIC VALIDATED" : "MANUAL REVIEW REQ"}
                      </span>
                    </div>
                  </div>

                  <div className="text-right font-mono text-xs text-muted-foreground">
                    <div>SPEC: <strong className="text-foreground">FLAT-500x100</strong></div>
                    <div>CLASS: <strong className="text-foreground">OPTICAL-AUTO</strong></div>
                  </div>
                </div>

                {/* Primary Reasons Strip */}
                <div className="bg-muted/50 rounded-lg p-2.5 text-xs font-mono space-y-1">
                  <div className="text-muted-foreground font-semibold text-[10px] uppercase">
                    DECISION RATIONALE:
                  </div>
                  {result.reasons.length > 0 ? (
                    <ul className="space-y-0.5">
                      {result.reasons.map((r, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-foreground">
                          <span className="text-primary font-bold">›</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="text-foreground flex items-center gap-1.5">
                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                      <span>All geometric tolerances and surface defect thresholds passed</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 2. Billet Identity Card */}
              <div className="bg-card border rounded-xl p-3.5 space-y-2.5 shadow-sm">
                <div className="flex items-center justify-between text-xs border-b pb-2">
                  <span className="font-mono font-bold flex items-center gap-1.5 text-muted-foreground">
                    <Hash className="w-3.5 h-3.5 text-primary" />
                    BILLET IDENTIFICATION
                  </span>
                  <div className="flex items-center gap-2 text-[11px] font-mono">
                    <span className="text-muted-foreground">Source:</span>
                    <span className="px-1.5 py-0.5 rounded bg-muted font-bold uppercase text-foreground">
                      {result.id_source}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs font-mono">
                  <div className="bg-muted/30 p-2 rounded-lg border">
                    <div className="text-[10px] text-muted-foreground">DECODED ID</div>
                    <div className="text-sm font-bold font-mono text-foreground mt-0.5 truncate">
                      {result.billet_id ?? "UNRESOLVED"}
                    </div>
                  </div>

                  <div className="bg-muted/30 p-2 rounded-lg border">
                    <div className="text-[10px] text-muted-foreground">QR CODE</div>
                    <div className={cn("text-xs font-bold font-mono mt-1 flex items-center gap-1", result.qr_detected ? "text-emerald-500" : "text-muted-foreground")}>
                      <QrCode className="w-3.5 h-3.5" />
                      {result.qr_detected ? "DETECTED" : "ABSENT"}
                    </div>
                  </div>

                  <div className="bg-muted/30 p-2 rounded-lg border col-span-2 sm:col-span-1">
                    <div className="text-[10px] text-muted-foreground">OCR CONFIDENCE</div>
                    <div className="text-xs font-bold font-mono text-foreground mt-1">
                      {result.ocr_confidence != null ? `${(result.ocr_confidence * 100).toFixed(0)}%` : "—"}
                    </div>
                  </div>
                </div>
              </div>

              {/* 3. Dimensional Tolerance Audit Table */}
              <div className="bg-card border rounded-xl overflow-hidden shadow-sm space-y-0">
                <div className="px-4 py-2.5 bg-muted/40 border-b flex items-center justify-between text-xs font-mono font-bold">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <Ruler className="w-3.5 h-3.5 text-primary" />
                    DIMENSIONAL TOLERANCE AUDIT
                  </span>
                  <span className="text-[10px] text-muted-foreground font-normal">
                    NOMINAL: 500.0×100.0 mm
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono text-left border-collapse">
                    <thead>
                      <tr className="border-b bg-muted/20 text-muted-foreground text-[10px] uppercase">
                        <th className="p-2.5 pl-4">Parameter</th>
                        <th className="p-2.5">Measured</th>
                        <th className="p-2.5">Target</th>
                        <th className="p-2.5">Deviation (Δ)</th>
                        <th className="p-2.5">Tolerance</th>
                        <th className="p-2.5 pr-4 text-right">Result</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y text-[11px]">
                      {/* Length Row */}
                      <tr className="hover:bg-muted/10">
                        <td className="p-2.5 pl-4 font-semibold text-foreground">Length</td>
                        <td className="p-2.5 font-bold">
                          {result.length_mm != null ? `${result.length_mm.toFixed(1)} mm` : `${result.length_px?.toFixed(0)} px`}
                        </td>
                        <td className="p-2.5 text-muted-foreground">
                          {result.nominal_length_mm != null ? `${result.nominal_length_mm.toFixed(1)} mm` : "500.0 mm"}
                        </td>
                        <td className="p-2.5">
                          {result.length_dev_mm != null ? (
                            <span className={cn("font-semibold", result.length_passed ? "text-emerald-500" : "text-destructive")}>
                              {result.length_dev_mm > 0 ? `+${result.length_dev_mm.toFixed(1)}` : result.length_dev_mm.toFixed(1)} mm
                              <span className="text-muted-foreground text-[10px] ml-1 font-normal">
                                (|{result.length_abs_dev_mm?.toFixed(1)}|)
                              </span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="p-2.5 text-muted-foreground">
                          {result.tol_length_mm != null ? `±${result.tol_length_mm.toFixed(1)} mm` : "±5.0 mm"}
                        </td>
                        <td className="p-2.5 pr-4 text-right">
                          {result.length_passed != null ? (
                            <span
                              className={cn(
                                "px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
                                result.length_passed
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                                  : "bg-red-500/15 text-red-600 dark:text-red-400",
                              )}
                            >
                              {result.length_passed ? "PASS" : "FAIL"}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>

                      {/* Width Row */}
                      <tr className="hover:bg-muted/10">
                        <td className="p-2.5 pl-4 font-semibold text-foreground">Width</td>
                        <td className="p-2.5 font-bold">
                          {result.width_mm != null ? `${result.width_mm.toFixed(1)} mm` : `${result.width_px?.toFixed(0)} px`}
                        </td>
                        <td className="p-2.5 text-muted-foreground">
                          {result.nominal_width_mm != null ? `${result.nominal_width_mm.toFixed(1)} mm` : "100.0 mm"}
                        </td>
                        <td className="p-2.5">
                          {result.width_dev_mm != null ? (
                            <span className={cn("font-semibold", result.width_passed ? "text-emerald-500" : "text-destructive")}>
                              {result.width_dev_mm > 0 ? `+${result.width_dev_mm.toFixed(1)}` : result.width_dev_mm.toFixed(1)} mm
                              <span className="text-muted-foreground text-[10px] ml-1 font-normal">
                                (|{result.width_abs_dev_mm?.toFixed(1)}|)
                              </span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="p-2.5 text-muted-foreground">
                          {result.tol_width_mm != null ? `±${result.tol_width_mm.toFixed(1)} mm` : "±2.0 mm"}
                        </td>
                        <td className="p-2.5 pr-4 text-right">
                          {result.width_passed != null ? (
                            <span
                              className={cn(
                                "px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
                                result.width_passed
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                                  : "bg-red-500/15 text-red-600 dark:text-red-400",
                              )}
                            >
                              {result.width_passed ? "PASS" : "FAIL"}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 4. Surface Defect Breakdown Card */}
              <div className="bg-card border rounded-xl p-3.5 space-y-2.5 shadow-sm">
                <div className="flex items-center justify-between text-xs border-b pb-2">
                  <span className="font-mono font-bold flex items-center gap-1.5 text-muted-foreground">
                    <ShieldAlert className="w-3.5 h-3.5 text-primary" />
                    SURFACE GEOMETRY DEFECT BREAKDOWN
                  </span>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    CATEGORIES: BULGE · CAMBER · TAPER · NOTCH
                  </span>
                </div>

                {result.defects.length > 0 || result.defect_type ? (
                  <div className="bg-destructive/10 border border-destructive/30 rounded-lg p-3 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-destructive font-mono uppercase flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4" />
                        DEFECT: {result.defect_type ?? result.defects[0]}
                      </span>
                      {result.defect_size_mm != null && (
                        <span className="font-mono font-bold text-destructive text-xs bg-destructive/15 px-2 py-0.5 rounded">
                          MAGNITUDE: {result.defect_size_mm.toFixed(2)} mm
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground font-mono">
                      Surface geometry exceeds maximum allowable cross-section / straightness tolerance.
                    </p>
                  </div>
                ) : (
                  <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2.5 text-xs text-emerald-600 dark:text-emerald-400 font-mono flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>No surface geometry defect detected</span>
                  </div>
                )}
              </div>

              {/* 5. Ground-Truth Benchmark Card (in Test Dataset Mode) */}
              {testInspectResponse?.ground_truth && (
                <div className="bg-card border-2 border-primary/30 rounded-xl overflow-hidden shadow-sm space-y-0">
                  <div className="px-4 py-2 bg-primary/10 border-b flex items-center justify-between text-xs font-mono font-bold text-primary">
                    <span className="flex items-center gap-1.5">
                      <Layers className="w-3.5 h-3.5" />
                      DATASET GROUND-TRUTH BENCHMARK
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-primary/20 text-primary uppercase">
                      VERIFICATION SUITE
                    </span>
                  </div>

                  <div className="p-3 space-y-2">
                    <table className="w-full text-xs font-mono border-collapse">
                      <thead>
                        <tr className="text-[10px] uppercase text-muted-foreground border-b pb-1">
                          <th className="text-left py-1">Attribute</th>
                          <th className="text-left py-1">System</th>
                          <th className="text-left py-1">Ground Truth</th>
                          <th className="text-right py-1">Verification</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y text-[11px]">
                        {/* Status Match */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">Status</td>
                          <td className="py-1.5 font-bold uppercase" style={{ color: statusStyle?.hex }}>
                            {result.status}
                          </td>
                          <td className="py-1.5 font-bold text-muted-foreground uppercase">
                            {testInspectResponse.ground_truth.expected_status}
                          </td>
                          <td className="py-1.5 text-right font-bold">
                            {testInspectResponse.comparison?.status_match ? (
                              <span className="text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded text-[10px]">
                                MATCH
                              </span>
                            ) : (
                              <span className="text-destructive bg-destructive/10 px-1.5 py-0.5 rounded text-[10px]">
                                MISMATCH
                              </span>
                            )}
                          </td>
                        </tr>

                        {/* Length Delta */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">Length</td>
                          <td className="py-1.5">{result.length_mm?.toFixed(1) ?? "—"} mm</td>
                          <td className="py-1.5 text-muted-foreground">{testInspectResponse.ground_truth.length_mm?.toFixed(2)} mm</td>
                          <td className="py-1.5 text-right font-mono">
                            {testInspectResponse.comparison?.length_delta_mm != null ? (
                              <span className="text-foreground">
                                Δ {testInspectResponse.comparison.length_delta_mm > 0 ? `+${testInspectResponse.comparison.length_delta_mm.toFixed(2)}` : testInspectResponse.comparison.length_delta_mm.toFixed(2)} mm
                              </span>
                            ) : "—"}
                          </td>
                        </tr>

                        {/* Width Delta */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">Width</td>
                          <td className="py-1.5">{result.width_mm?.toFixed(1) ?? "—"} mm</td>
                          <td className="py-1.5 text-muted-foreground">{testInspectResponse.ground_truth.width_mm?.toFixed(2)} mm</td>
                          <td className="py-1.5 text-right font-mono">
                            {testInspectResponse.comparison?.width_delta_mm != null ? (
                              <span className="text-foreground">
                                Δ {testInspectResponse.comparison.width_delta_mm > 0 ? `+${testInspectResponse.comparison.width_delta_mm.toFixed(2)}` : testInspectResponse.comparison.width_delta_mm.toFixed(2)} mm
                              </span>
                            ) : "—"}
                          </td>
                        </tr>

                        {/* Defect Match */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">Defect</td>
                          <td className="py-1.5 uppercase font-medium">{result.defect_type ?? "None"}</td>
                          <td className="py-1.5 text-muted-foreground uppercase">{testInspectResponse.ground_truth.defect ?? "None"}</td>
                          <td className="py-1.5 text-right font-bold">
                            {testInspectResponse.comparison?.defect_type_match ? (
                              <span className="text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded text-[10px]">
                                MATCH
                              </span>
                            ) : (
                              <span className="text-destructive bg-destructive/10 px-1.5 py-0.5 rounded text-[10px]">
                                MISMATCH
                              </span>
                            )}
                          </td>
                        </tr>

                        {/* Defect Size Delta */}
                        {testInspectResponse.ground_truth.defect_size_mm && testInspectResponse.ground_truth.defect_size_mm > 0 ? (
                          <tr>
                            <td className="py-1.5 font-semibold text-muted-foreground">Defect Size</td>
                            <td className="py-1.5">{result.defect_size_mm?.toFixed(2) ?? "—"} mm</td>
                            <td className="py-1.5 text-muted-foreground">{testInspectResponse.ground_truth.defect_size_mm.toFixed(2)} mm</td>
                            <td className="py-1.5 text-right font-mono">
                              {testInspectResponse.comparison?.defect_size_delta_mm != null ? (
                                <span>Δ {testInspectResponse.comparison.defect_size_delta_mm > 0 ? `+${testInspectResponse.comparison.defect_size_delta_mm.toFixed(2)}` : testInspectResponse.comparison.defect_size_delta_mm.toFixed(2)} mm</span>
                              ) : "—"}
                            </td>
                          </tr>
                        ) : null}

                        {/* ID Match */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">Billet ID</td>
                          <td className="py-1.5">{result.billet_id ?? "None"}</td>
                          <td className="py-1.5 text-muted-foreground">{testInspectResponse.ground_truth.id_text ?? "None"}</td>
                          <td className="py-1.5 text-right font-bold">
                            {testInspectResponse.comparison?.id_match != null ? (
                              testInspectResponse.comparison.id_match ? (
                                <span className="text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded text-[10px]">
                                  MATCH
                                </span>
                              ) : (
                                <span className="text-destructive bg-destructive/10 px-1.5 py-0.5 rounded text-[10px]">
                                  MISMATCH
                                </span>
                              )
                            ) : (
                              <span className="text-muted-foreground text-[10px]">N/A</span>
                            )}
                          </td>
                        </tr>

                        {/* QR Match */}
                        <tr>
                          <td className="py-1.5 font-semibold text-muted-foreground">QR Present</td>
                          <td className="py-1.5">{result.qr_detected ? "YES" : "NO"}</td>
                          <td className="py-1.5 text-muted-foreground">{testInspectResponse.ground_truth.qr ? "YES" : "NO"}</td>
                          <td className="py-1.5 text-right font-bold">
                            {testInspectResponse.comparison?.qr_match ? (
                              <span className="text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded text-[10px]">
                                MATCH
                              </span>
                            ) : (
                              <span className="text-destructive bg-destructive/10 px-1.5 py-0.5 rounded text-[10px]">
                                MISMATCH
                              </span>
                            )}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Empty Prompt */
            <div className="bg-card border-2 border-dashed rounded-xl p-12 text-center text-muted-foreground space-y-3">
              <Sliders className="w-12 h-12 mx-auto text-muted-foreground/30" />
              <h3 className="text-sm font-bold text-foreground font-mono">AWAITING INSPECTION TARGET</h3>
              <p className="text-xs max-w-sm mx-auto">
                Select an image from the <strong>Test Dataset</strong> or upload a static file to inspect dimensional tolerances, surface defects, and identity.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
