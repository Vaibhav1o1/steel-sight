/**
 * Number and string formatting utilities for BilletVision.
 * Standards:
 * - mm values formatted to 1 decimal place.
 * - % values formatted to 2 decimal places.
 * - Deviations signed (+/-).
 */

export function formatMm(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(1)} mm`;
}

export function formatDevMm(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(1)} mm`;
}

export function formatPct(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(2)}%`;
}

export function formatSignedPct(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(2)}%`;
}

export function formatMs(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(1)} ms`;
}

export function formatFps(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) {
    return "—";
  }
  return `${val.toFixed(1)} fps`;
}

export function formatTime(ts: string | number | null | undefined): string {
  if (!ts) {
    return "—";
  }
  try {
    const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
    if (Number.isNaN(d.getTime())) {
      return "—";
    }
    return d.toLocaleTimeString([], { hour12: false });
  } catch {
    return "—";
  }
}

export function formatDateTime(ts: string | number | null | undefined): string {
  if (!ts) {
    return "—";
  }
  try {
    const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
    if (Number.isNaN(d.getTime())) {
      return "—";
    }
    return d.toLocaleString([], { hour12: false });
  } catch {
    return "—";
  }
}
