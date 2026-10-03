"use client";

import * as React from "react";
import { useState, useRef } from "react";
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  FileImage,
  Loader2,
  HelpCircle,
} from "lucide-react";
import { uploadImage, uploadedImageUrl, ApiError } from "@/lib/api";
import type { UploadResult } from "@/lib/upload_types";
import { STATUS_STYLES } from "@/lib/status";
import { cn } from "cn";

export function UploadView() {
  const [file, setFile] = useState<File | null>(null);
  const [stationCamera, setStationCamera] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (selectedFile: File) => {
    setFile(selectedFile);
    setResult(null);
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

  const handleInspect = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);
    try {
      const res = await uploadImage(file, stationCamera);
      setResult(res);
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

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Upload Inspection</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Inspect arbitrary static billet images with automatic marker calibration, station calibration, or uncalibrated review.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Upload Form */}
        <div className="lg:col-span-5 space-y-4">
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors bg-card hover:bg-muted/40 flex flex-col items-center justify-center min-h-[260px]",
              isDragOver ? "border-primary bg-primary/5" : "border-border",
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFileSelect(f);
              }}
            />
            <div className="h-12 w-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mb-4">
              <UploadCloud className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium">
              {file ? file.name : "Click or drag image to upload"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              JPEG or PNG up to 15 MB
            </p>
            {file && (
              <p className="text-xs font-mono text-muted-foreground mt-2">
                {(file.size / (1024 * 1024)).toFixed(2)} MB
              </p>
            )}
          </div>

          <div className="space-y-2 p-3 bg-muted/40 rounded-lg border border-border">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="stationCamera"
                checked={stationCamera}
                onChange={(e) => setStationCamera(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="stationCamera" className="text-sm font-medium cursor-pointer select-none">
                Use station camera calibration
              </label>
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed pl-6">
              Use only if this photo was taken by the station camera in the same position; otherwise millimetres would be wrong.
            </p>
          </div>

          <div className="p-3 bg-muted/20 rounded-lg border border-dashed border-border text-[11px] text-muted-foreground space-y-1">
            <p>
              <strong>Marker Note:</strong> Marker assumed 80 mm, DICT_4X4_50, lying in the same plane as the billet top face.
            </p>
            <p className="text-primary/80 font-medium">
              Single-image result. Not stored in the station log.
            </p>
          </div>

          <button
            onClick={handleInspect}
            disabled={!file || loading}
            className={cn(
              "w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2",
              file && !loading
                ? "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing inspection...</span>
              </>
            ) : (
              <>
                <FileImage className="h-4 w-4" />
                <span>Inspect Billet</span>
              </>
            )}
          </button>

          {error && (
            <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Inspection Failed</p>
                <p className="mt-0.5 text-xs font-mono">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Result Details */}
        <div className="lg:col-span-7">
          {result ? (
            <div className="border rounded-xl bg-card overflow-hidden shadow-sm space-y-4 p-5">
              {/* Header: Status and Calibration Source */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "px-3 py-1 text-sm font-semibold rounded-md border",
                      STATUS_STYLES[result.status]?.badgeClass,
                    )}
                  >
                    {STATUS_STYLES[result.status]?.label ?? result.status}
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">
                    {result.processing_time_ms} ms
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {result.calibrated ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                      <CheckCircle2 className="h-3 w-3" />
                      {result.calibration.source === "marker" ? "Marker Calibrated" : "Station Calibrated"}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                      <HelpCircle className="h-3 w-3" />
                      UNCALIBRATED (pixels only)
                    </span>
                  )}
                </div>
              </div>

              {result.calibration.warning && (
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs">
                  <strong>Note:</strong> {result.calibration.warning}
                </div>
              )}

              {/* Annotated Image Preview */}
              <div className="rounded-lg overflow-hidden border bg-black/40 flex items-center justify-center max-h-[380px]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={uploadedImageUrl(result.image_id)}
                  alt="Annotated Inspection"
                  className="max-h-[380px] w-auto object-contain"
                />
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="p-3 rounded-lg bg-muted/30 border">
                  <p className="text-xs text-muted-foreground">Billet ID</p>
                  <p className="text-base font-semibold font-mono mt-0.5">
                    {result.billet_id ?? "—"}
                  </p>
                  <p className="text-[10px] text-muted-foreground capitalize">
                    {result.id_source !== "none" ? `${result.id_source}` : "Not read"}
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-muted/30 border">
                  <p className="text-xs text-muted-foreground">Length</p>
                  <p className="text-base font-semibold font-mono mt-0.5">
                    {result.calibrated && result.length_mm !== null
                      ? `${result.length_mm.toFixed(1)} mm`
                      : result.length_px !== null
                        ? `${result.length_px.toFixed(0)} px`
                        : "—"}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {result.calibrated ? "Calibrated mm" : "Raw pixels (uncalibrated)"}
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-muted/30 border">
                  <p className="text-xs text-muted-foreground">Width</p>
                  <p className="text-base font-semibold font-mono mt-0.5">
                    {result.calibrated && result.width_mm !== null
                      ? `${result.width_mm.toFixed(1)} mm`
                      : result.width_px !== null
                        ? `${result.width_px.toFixed(0)} px`
                        : "—"}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {result.calibrated ? "Calibrated mm" : "Raw pixels (uncalibrated)"}
                  </p>
                </div>

                <div className="p-3 rounded-lg bg-muted/30 border">
                  <p className="text-xs text-muted-foreground">Defects</p>
                  <p className="text-base font-semibold font-mono mt-0.5">
                    {result.defects.length > 0 ? result.defects.length : "None"}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {result.defects.join(", ") || "Clear"}
                  </p>
                </div>
              </div>

              {/* Reasons list */}
              {result.reasons.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-xs font-semibold text-muted-foreground">Review & Status Reasons:</p>
                  <ul className="text-xs list-disc pl-4 space-y-1 text-muted-foreground">
                    {result.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-[11px] text-muted-foreground/80 italic pt-2 border-t">
                Single-image result. Not stored in the station log.
              </p>
            </div>
          ) : (
            <div className="h-full min-h-[360px] border border-dashed rounded-xl flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
              <FileImage className="h-10 w-10 stroke-1 mb-2 opacity-50" />
              <p className="text-sm font-medium">No inspection results yet</p>
              <p className="text-xs mt-1">
                Upload an image on the left and click Inspect Billet to see dimensions and defects.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
