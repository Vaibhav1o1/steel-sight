"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "cn";
import { Camera, CheckCircle2, FileSpreadsheet, Gauge } from "lucide-react";
import { MuteToggle } from "./MuteToggle";
import { ThemeToggle } from "./ThemeToggle";

import { useLive } from "@/lib/live";

export interface TopBarProps {
  className?: string;
}

const NAV_ITEMS = [
  { href: "/", label: "Live" },
  { href: "/upload", label: "Upload" },
  { href: "/analytics", label: "Analytics" },
  { href: "/log", label: "Log" },
  { href: "/calibration", label: "Calibration" },
  { href: "/accuracy", label: "Accuracy" },
] as const;

export function TopBar({ className }: TopBarProps) {
  const pathname = usePathname();
  const { stats, writer } = useLive();

  const cameraOk = stats?.camera_ok ?? false;
  const calibrated = stats?.calibrated ?? false;
  const fps = stats?.fps_process ?? null;
  const latencyP95Ms = stats?.process_ms_p95 ?? null;
  const logStatus = stats?.log_status ?? "ok";

  return (
    <header
      className={cn(
        "sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60",
        className,
      )}
    >
      <div className="flex h-14 items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 font-bold tracking-tight text-lg">
            <span className="h-2 w-2 rounded-full bg-emerald-600 animate-pulse" />
            <span>BilletVision</span>
          </Link>

          <nav className="flex items-center gap-1 sm:gap-2">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {/* Status chips */}
          <div className="hidden md:flex items-center gap-2 text-xs font-mono">
            <div
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5",
                cameraOk
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
              )}
            >
              <Camera className="h-3 w-3" />
              <span>{cameraOk ? "Camera OK" : "Camera Down"}</span>
            </div>

            <div
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5",
                calibrated
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "border-slate-500/30 bg-slate-500/10 text-muted-foreground",
              )}
            >
              <CheckCircle2 className="h-3 w-3" />
              <span>{calibrated ? "Calibrated" : "Uncalibrated"}</span>
            </div>

            <div className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-muted-foreground border-border bg-muted/40">
              <Gauge className="h-3 w-3" />
              <span>{fps !== null ? `${fps.toFixed(1)} fps` : "— fps"}</span>
            </div>

            <div className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-muted-foreground border-border bg-muted/40">
              <span>{latencyP95Ms !== null ? `${latencyP95Ms.toFixed(0)} ms` : "— ms"}</span>
            </div>

            <div
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5",
                logStatus === "ok"
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : logStatus === "locked"
                    ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                    : "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
              )}
            >
              <FileSpreadsheet className="h-3 w-3" />
              <span>
                {logStatus === "ok"
                  ? "Excel OK"
                  : logStatus === "locked"
                    ? "Excel Locked"
                    : "Excel Error"}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1 border-l pl-2">
            <MuteToggle />
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
  );
}
