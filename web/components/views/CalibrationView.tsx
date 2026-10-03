"use client";

import { useEffect, useState } from "react";
import { useLive } from "@/lib/live";
import { getCalibration, detectMarker, captureBackground, verifyCalibration, resetCalibration, ApiError } from "@/lib/api";
import type { CalibrationState, VerifyResult } from "@/lib/types";
import { formatMm, formatPct, formatDateTime } from "@/lib/format";

export function CalibrationView() {
  const { stats, calibration: liveCalib } = useLive();
  const [calib, setCalib] = useState<CalibrationState | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCalibration()
      .then(setCalib)
      .catch(e => setError(e.message));
  }, []);

  // Update from live if new
  useEffect(() => {
    if (liveCalib) {
      setCalib(liveCalib);
      if (liveCalib.verify) setVerify(liveCalib.verify);
    }
  }, [liveCalib]);

  const handleDetect = async () => {
    try {
      setWorking(true);
      setError(null);
      const res = await detectMarker();
      if (!res.found) {
        setError("Marker not found in current frame. Ensure it is visible.");
      } else {
        setCalib(res.calibration);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  };

  const handleBackground = async () => {
    try {
      setWorking(true);
      setError(null);
      const res = await captureBackground();
      setCalib(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  };

  const handleReset = async () => {
    try {
      setWorking(true);
      setError(null);
      const res = await resetCalibration();
      setCalib(res);
      setVerify(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  };

  const handleVerify = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const l = Number(fd.get("length"));
    const w = fd.get("width") ? Number(fd.get("width")) : undefined;
    
    try {
      setWorking(true);
      setError(null);
      const res = await verifyCalibration({ known_length_mm: l, known_width_mm: w });
      setVerify(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  };

  const isCalibrated = calib?.calibrated;

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Calibration & Setup</h1>
      
      {error && (
        <div className="bg-destructive/10 border-l-4 border-destructive px-4 py-2 text-sm text-destructive font-medium">
          {error}
        </div>
      )}

      {/* Main Status */}
      <div className="border rounded-lg p-6 bg-card space-y-4">
        <div className="flex items-center gap-4">
          <div className={`w-4 h-4 rounded-full ${isCalibrated ? "bg-emerald-500" : "bg-destructive"}`} />
          <h2 className="text-xl font-bold">{isCalibrated ? "Calibrated" : "Not Calibrated"}</h2>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground block">Calibration Version</span>
            <span className="font-mono font-medium">{calib?.calib_version ?? "—"}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">Last Calibrated</span>
            <span className="font-mono">{formatDateTime(calib?.created_at)}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">px per mm (Rect)</span>
            <span className="font-mono">{calib?.rect_px_per_mm ? calib.rect_px_per_mm.toFixed(3) : "—"}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">Residual (Reprojection)</span>
            <span className="font-mono">{calib?.residual_mm ? `${calib.residual_mm.toFixed(3)} mm` : "—"}</span>
          </div>
        </div>
        
        {calib?.baseline === "reduced-baseline" && (
          <div className="bg-amber-500/10 text-amber-600 border border-amber-500/30 p-3 rounded text-sm">
            <strong>⚠ Reduced Baseline:</strong> Single marker homography detected. Accuracy may be reduced away from the marker. 
            Use a multi-marker plate for best results.
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="border rounded-lg p-6 bg-card space-y-6">
        <h3 className="font-bold border-b pb-2">Steps</h3>
        
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <h4 className="font-semibold">1. Detect Marker(s)</h4>
            <button 
              onClick={handleDetect} 
              disabled={working}
              className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
            >
              Detect
            </button>
          </div>
          <p className="text-sm text-muted-foreground">
            Place the ArUco marker plate at billet-top height and ensure it is fully visible.
          </p>
        </div>

        <div className="space-y-2 pt-4 border-t">
          <div className="flex justify-between items-center">
            <h4 className="font-semibold">2. Capture Background</h4>
            <button 
              onClick={handleBackground} 
              disabled={working || !calib?.has_intrinsics}
              className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
            >
              Capture
            </button>
          </div>
          <p className="text-sm text-muted-foreground">
            Clear the belt completely and capture the background for segmentation.
          </p>
        </div>
        
        <div className="pt-4 border-t flex justify-end">
          <button 
            onClick={handleReset} 
            disabled={working || !isCalibrated}
            className="px-4 py-2 border border-destructive text-destructive rounded hover:bg-destructive/10 disabled:opacity-50 text-sm font-medium"
          >
            Reset All Calibration
          </button>
        </div>
      </div>

      {/* Verification */}
      <div className="border rounded-lg p-6 bg-card space-y-4">
        <h3 className="font-bold border-b pb-2">Verification Step</h3>
        <p className="text-sm text-muted-foreground">
          Place an object of known dimensions on the belt and measure it.
        </p>
        
        <form onSubmit={handleVerify} className="flex gap-4 items-end">
          <div className="space-y-1">
            <label className="text-sm text-muted-foreground">Known Length (mm)</label>
            <input name="length" type="number" step="0.1" required className="w-full px-3 py-2 border rounded text-sm bg-background" />
          </div>
          <div className="space-y-1">
            <label className="text-sm text-muted-foreground">Known Width (mm, optional)</label>
            <input name="width" type="number" step="0.1" className="w-full px-3 py-2 border rounded text-sm bg-background" />
          </div>
          <button 
            type="submit" 
            disabled={working || !isCalibrated}
            className="px-4 py-2 bg-secondary text-secondary-foreground rounded hover:bg-secondary/80 disabled:opacity-50 text-sm font-medium"
          >
            Verify
          </button>
        </form>

        {verify && (
          <div className={`p-4 rounded-lg border text-sm grid grid-cols-2 gap-2 ${verify.ok ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-destructive/10 border-destructive/30'}`}>
            <span className="text-muted-foreground">Measured Length</span>
            <span className="font-mono">{formatMm(verify.measured_length_mm)} (Error: {formatPct(verify.length_error_pct)})</span>
            {verify.known_width_mm != null && (
              <>
                <span className="text-muted-foreground">Measured Width</span>
                <span className="font-mono">{formatMm(verify.measured_width_mm)} (Error: {formatPct(verify.width_error_pct)})</span>
              </>
            )}
            <div className="col-span-2 pt-2 font-bold flex gap-2 items-center">
              Result: <span className={verify.ok ? "text-emerald-600" : "text-destructive"}>{verify.ok ? "PASS" : "FAIL"}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
