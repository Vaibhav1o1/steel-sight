import type { AlertLevel, DefectType, InspectionStatus, LogFileStatus } from "./types";

export interface StatusStyle {
  label: string;
  badgeClass: string;
  textClass: string;
  bgClass: string;
  borderClass: string;
  hex: string;
}

export const STATUS_STYLES: Record<InspectionStatus, StatusStyle> = {
  Pass: {
    label: "Pass",
    badgeClass: "bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 border-emerald-600/30",
    textClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-600",
    borderClass: "border-emerald-600",
    hex: "#059669",
  },
  Rework: {
    label: "Rework",
    badgeClass: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
    textClass: "text-amber-500 dark:text-amber-400",
    bgClass: "bg-amber-500",
    borderClass: "border-amber-500",
    hex: "#f59e0b",
  },
  Fail: {
    label: "Fail",
    badgeClass: "bg-red-600/15 text-red-700 dark:text-red-400 border-red-600/30",
    textClass: "text-red-600 dark:text-red-400",
    bgClass: "bg-red-600",
    borderClass: "border-red-600",
    hex: "#dc2626",
  },
};

export const ALERT_STYLES: Record<AlertLevel, StatusStyle> = {
  Fail: STATUS_STYLES.Fail,
  Rework: STATUS_STYLES.Rework,
  System: {
    label: "System",
    badgeClass: "bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30",
    textClass: "text-slate-500 dark:text-slate-400",
    bgClass: "bg-slate-500",
    borderClass: "border-slate-500",
    hex: "#64748b",
  },
};

export const LOG_STATUS_STYLES: Record<LogFileStatus, StatusStyle> = {
  ok: {
    label: "Excel OK",
    badgeClass: "bg-emerald-600/15 text-emerald-700 dark:text-emerald-400 border-emerald-600/30",
    textClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-600",
    borderClass: "border-emerald-600",
    hex: "#059669",
  },
  locked: {
    label: "Excel Locked",
    badgeClass: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
    textClass: "text-amber-500 dark:text-amber-400",
    bgClass: "bg-amber-500",
    borderClass: "border-amber-500",
    hex: "#f59e0b",
  },
  error: {
    label: "Excel Error",
    badgeClass: "bg-red-600/15 text-red-700 dark:text-red-400 border-red-600/30",
    textClass: "text-red-600 dark:text-red-400",
    bgClass: "bg-red-600",
    borderClass: "border-red-600",
    hex: "#dc2626",
  },
};

export function getStatusStyle(status: InspectionStatus): StatusStyle {
  return STATUS_STYLES[status];
}

export function getAlertStyle(level: AlertLevel): StatusStyle {
  return ALERT_STYLES[level];
}

export function getLogStatusStyle(status: LogFileStatus): StatusStyle {
  return LOG_STATUS_STYLES[status];
}

export const DEFECT_LABELS: Record<DefectType, string> = {
  notch: "Notch",
  taper: "Taper",
  bulge: "Bulge",
  camber: "Camber",
};

export function getDefectLabel(defect: DefectType): string {
  return DEFECT_LABELS[defect];
}
