"use client";

import { useEffect, useState, useMemo } from "react";
import { getInspections, exportUrl } from "@/lib/api";
import type { Inspection, InspectionFilters } from "@/lib/types";
import { formatMm, formatPct, formatDateTime, formatDevMm } from "@/lib/format";
import { getStatusStyle } from "@/lib/status";
import { useLive } from "@/lib/live";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";

export function LogView() {
  const { inspections: liveInspections } = useLive();
  const [data, setData] = useState<Inspection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Real UI would have proper filter controls. For hackathon MVP, simple list.
  const [filters, setFilters] = useState<InspectionFilters>({ limit: 100 });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    getInspections(filters)
      .then((res) => {
        if (mounted) {
          setData(res.items);
          setError(null);
        }
      })
      .catch((err) => {
        if (mounted) setError(err.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [filters]);

  // Merge live WS data with fetched data to keep table instantly up-to-date
  const displayData = useMemo(() => {
    const map = new Map<number, Inspection>();
    data.forEach(i => map.set(i.id, i));
    liveInspections.forEach(i => map.set(i.id, i));
    return Array.from(map.values()).sort((a, b) => b.id - a.id);
  }, [data, liveInspections]);

  const selected = displayData.find(i => i.id === selectedId);

  return (
    <div className="p-4 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Inspection Log</h1>
        <div className="flex gap-2">
          <a
            href={exportUrl("csv", {})}
            className="px-3 py-1.5 text-sm bg-secondary text-secondary-foreground rounded hover:bg-secondary/80"
          >
            Export CSV
          </a>
          <a
            href={exportUrl("xlsx", {})}
            className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90"
          >
            Export XLSX
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 border rounded-lg overflow-hidden bg-card flex flex-col h-[70vh]">
          {loading && displayData.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-8">Loading...</div>
          ) : error ? (
            <ErrorState message={error} onRetry={() => setFilters({ ...filters })} />
          ) : displayData.length === 0 ? (
            <EmptyState message="No inspections recorded yet" />
          ) : (
            <div className="overflow-auto flex-1">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground bg-muted/50 sticky top-0 uppercase">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Time</th>
                    <th className="px-4 py-3">Billet ID</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Length (dev)</th>
                    <th className="px-4 py-3 text-right">Width (dev)</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {displayData.map((ins) => {
                    const st = getStatusStyle(ins.status);
                    const isSelected = selectedId === ins.id;
                    return (
                      <tr 
                        key={ins.id} 
                        onClick={() => setSelectedId(ins.id)}
                        className={`hover:bg-muted/50 cursor-pointer ${isSelected ? "bg-muted/80" : ""}`}
                      >
                        <td className="px-4 py-2 font-mono">{ins.id}</td>
                        <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">
                          {formatDateTime(ins.ts)}
                        </td>
                        <td className="px-4 py-2 font-mono font-medium">
                          {ins.billet_id || "—"}
                        </td>
                        <td className="px-4 py-2">
                          <span className={`px-2 py-1 rounded text-xs font-semibold ${st.badgeClass}`}>
                            {st.label}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">
                          {formatMm(ins.length_mm)}{" "}
                          <span className="text-muted-foreground text-xs">
                            ({formatDevMm(ins.length_dev_mm)})
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums">
                          {formatMm(ins.width_mm)}{" "}
                          <span className="text-muted-foreground text-xs">
                            ({formatDevMm(ins.width_dev_mm)})
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="lg:col-span-1 border rounded-lg p-4 bg-card h-fit sticky top-4">
          {selected ? (
            <div className="space-y-4">
              <h3 className="font-bold border-b pb-2">Details: #{selected.id}</h3>
              <div className="aspect-video bg-black rounded overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img 
                  src={selected.snapshot_url} 
                  alt="Evidence" 
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                  }}
                />
              </div>
              <div className="grid grid-cols-2 gap-y-2 text-sm">
                <span className="text-muted-foreground">ID Source</span>
                <span className="font-mono text-right">{selected.id_source}</span>
                <span className="text-muted-foreground">Length</span>
                <span className="font-mono text-right">{formatMm(selected.length_mm)}</span>
                <span className="text-muted-foreground">Width</span>
                <span className="font-mono text-right">{formatMm(selected.width_mm)}</span>
                <span className="text-muted-foreground">CS Var</span>
                <span className="font-mono text-right">{formatPct(selected.width_variation_pct)}</span>
                <span className="text-muted-foreground">Camber</span>
                <span className="font-mono text-right">{formatMm(selected.camber_mm)}</span>
                <span className="text-muted-foreground">Taper</span>
                <span className="font-mono text-right">{formatMm(selected.taper_mm)}</span>
              </div>
              {selected.reasons.length > 0 && (
                <div className="mt-4 pt-4 border-t text-sm text-destructive font-medium">
                  Reasons: {selected.reasons.join(", ")}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center text-muted-foreground py-8">
              Select an inspection to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
