import * as React from "react";
import { cn } from "cn";
import {
  ALERT_STYLES,
  LOG_STATUS_STYLES,
  STATUS_STYLES,
  type StatusStyle,
} from "@/lib/status";
import type { AlertLevel, InspectionStatus, LogFileStatus } from "@/lib/types";

export interface StatusBadgeProps {
  status: InspectionStatus | AlertLevel | LogFileStatus;
  className?: string;
}

function resolveStyle(status: InspectionStatus | AlertLevel | LogFileStatus): StatusStyle {
  if (status === "Pass" || status === "Rework" || status === "Fail") {
    return STATUS_STYLES[status];
  }
  if (status === "System") {
    return ALERT_STYLES[status];
  }
  if (status === "ok" || status === "locked" || status === "error") {
    return LOG_STATUS_STYLES[status];
  }
  return {
    label: String(status),
    badgeClass: "bg-muted text-muted-foreground border-border",
    textClass: "text-muted-foreground",
    bgClass: "bg-muted-foreground",
    borderClass: "border-border",
    hex: "#64748b",
  };
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const style = resolveStyle(status);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide",
        style.badgeClass,
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", style.bgClass)} />
      {style.label}
    </span>
  );
}
