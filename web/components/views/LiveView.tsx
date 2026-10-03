"use client";

import { useLive } from "@/lib/live";
import { streamUrl } from "@/lib/api";
import { formatMm, formatPct, formatMs } from "@/lib/format";
import { getStatusStyle } from "@/lib/status";
import type { Inspection, InspectionStatus } from "@/lib/types";

// ── Health Strip ─────────────────────────────────────
function HealthStrip() {
  const { stats, writer, connected } = useLive();

  if (!connected || !stats) {
    return (
      <div className="flex items-center gap-4 px-4 py-2 text-xs bg-muted/50 border-b">
        <span className="text-muted-foreground">⏳ Connecting to backend…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-4 px-4 py-2 text-xs bg-muted/50 border-b font-mono">
      <Chip label="FPS (cap)" value={stats.fps_capture.toFixed(1)} />
      <Chip label="FPS (proc)" value={stats.fps_process.toFixed(1)} />
      <Chip label="p95 ms" value={stats.process_ms_p95.toFixed(0)} />
      <Chip label="Tracks" value={String(stats.tracks)} />
      <Chip label="Drift" value={stats.drift_mm != null ? `${stats.drift_mm.toFixed(1)} mm` : "—"} />
      <Chip label="Queue" value={String(stats.queue_length ?? 0)} />
      <Chip
        label="Writer"
        value={writer.blocked ? "BLOCKED" : `${writer.pendingCount} pending`}
        alert={writer.blocked}
      />
      <Chip
        label="Calib"
        value={stats.calibrated ? "OK" : "NO"}
        alert={!stats.calibrated}
      />
      {!stats.camera_ok && (
        <span className="text-destructive font-semibold">⚠ Camera</span>
      )}
    </div>
  );
}

function Chip({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <span className={alert ? "text-destructive font-semibold" : "text-muted-foreground"}>
      {label}: <span className="text-foreground font-medium">{value}</span>
    </span>
  );
}

// ── Live Feed ─────────────────────────────────────────
function LiveFeed() {
  return (
    <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={streamUrl("annotated")}
        alt="Live MJPEG stream"
        className="w-full h-full object-contain"
      />
    </div>
  );
}

// ── Latest Result Card ────────────────────────────────
function LatestResultCard() {
  const { latestInspection } = useLive();

  if (!latestInspection) {
    return (
      <div className="rounded-lg border p-6 flex items-center justify-center text-muted-foreground min-h-[200px]">
        No inspections yet
      </div>
    );
  }

  const ins = latestInspection;
  const color = getStatusStyle(ins.status as InspectionStatus).hex;

  return (
    <div className={`rounded-lg border-2 p-4 space-y-3`} style={{ borderColor: color }}>
      <div className="flex items-center justify-between">
        <span className="text-lg font-bold" style={{ color }}>
          {ins.status}
        </span>
        <span className="text-sm text-muted-foreground font-mono">
          #{ins.id}
        </span>
      </div>

      <div className="text-sm font-mono">
        ID: {ins.billet_id ?? "—"}{" "}
        <span className="text-muted-foreground">({ins.id_source})</span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <Field label="Length" value={formatMm(ins.length_mm)} />
        <Field label="Width" value={formatMm(ins.width_mm)} />
        <Field label="L dev" value={`${ins.length_dev_mm > 0 ? "+" : ""}${formatMm(ins.length_dev_mm)}`} />
        <Field label="W dev" value={`${ins.width_dev_mm > 0 ? "+" : ""}${formatMm(ins.width_dev_mm)}`} />
        <Field label="CS Var" value={formatPct(ins.width_variation_pct)} />
        <Field label="Taper" value={formatMm(ins.taper_mm)} />
        <Field label="Camber" value={formatMm(ins.camber_mm)} />
        <Field label="Latency" value={formatMs(ins.latency_ms)} />
      </div>

      {ins.defects.length > 0 && (
        <div className="text-xs text-destructive">
          Defects: {ins.defects.join(", ")}
        </div>
      )}
      {ins.reasons.length > 0 && (
        <div className="text-xs text-muted-foreground">
          Reasons: {ins.reasons.join(", ")}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground">{label}: </span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

// ── Recent Strip ──────────────────────────────────────
function RecentStrip() {
  const { inspections } = useLive();
  const recent = inspections.slice(0, 20);

  if (recent.length === 0) {
    return null;
  }

  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold text-muted-foreground">Recent</h3>
      <div className="flex gap-1 overflow-x-auto pb-1">
        {recent.map((ins) => (
          <div
            key={ins.id}
            className="shrink-0 w-16 h-8 rounded text-xs flex items-center justify-center font-semibold text-white"
            style={{ backgroundColor: getStatusStyle(ins.status as InspectionStatus).hex }}
            title={`#${ins.id} ${ins.billet_id ?? "—"} ${formatMm(ins.length_mm)}×${formatMm(ins.width_mm)}`}
          >
            {ins.status[0]}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Alert Banner ──────────────────────────────────────
function AlertBanner() {
  const { latestAlert, stats } = useLive();

  const messages: string[] = [];

  if (stats && !stats.calibrated) {
    messages.push("⚠ Not calibrated — inspect results will be REVIEW");
  }
  if (stats && !stats.camera_ok) {
    messages.push("⚠ Camera unavailable");
  }
  if (latestAlert && !latestAlert.acknowledged) {
    messages.push(`🔔 ${latestAlert.level}: ${latestAlert.message}`);
  }

  if (messages.length === 0) return null;

  return (
    <div className="bg-destructive/10 border-l-4 border-destructive px-4 py-2 space-y-1">
      {messages.map((m, i) => (
        <div key={i} className="text-sm text-destructive font-medium">{m}</div>
      ))}
    </div>
  );
}

// ── Main Live View ────────────────────────────────────
function LiveView() {
  return (
    <div className="space-y-4 p-4 max-w-7xl mx-auto">
      <HealthStrip />
      <AlertBanner />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <LiveFeed />
        </div>
        <div className="space-y-4">
          <LatestResultCard />
          <RecentStrip />
        </div>
      </div>
    </div>
  );
}

export { LiveView };
