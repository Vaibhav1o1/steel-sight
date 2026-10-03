"use client";

import * as React from "react";
import { useState, useEffect, useRef } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  SlidersHorizontal,
  Bot,
  Layers,
} from "lucide-react";
import { getStatusSeries, ApiError } from "@/lib/api";
import { useLive } from "@/lib/live";
import type { StatusSeriesResponse } from "@/lib/analytics_types";
import { cn } from "cn";

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    color: string;
    payload: {
      label: string;
      total_count: number;
      evaluated_count: number;
      nonconforming_count: number;
      p_rate: number | null;
      ucl: number | null;
      lcl: number | null;
      centerline: number | null;
      reliable: boolean;
      pass_count: number;
      rework_count: number;
      fail_count: number;
      review_count: number;
    };
  }>;
  label?: string;
}

function StatusTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  return (
    <div className="bg-popover text-popover-foreground border border-border shadow-md rounded-lg p-3 text-xs space-y-1.5 min-w-[190px]">
      <p className="font-semibold border-b pb-1 text-foreground">{data.label}</p>
      <div className="space-y-0.5">
        <div className="flex justify-between items-center text-emerald-600 dark:text-emerald-400">
          <span>Pass:</span>
          <span className="font-mono font-medium">{data.pass_count}</span>
        </div>
        <div className="flex justify-between items-center text-amber-600 dark:text-amber-400">
          <span>Rework:</span>
          <span className="font-mono font-medium">{data.rework_count}</span>
        </div>
        <div className="flex justify-between items-center text-red-600 dark:text-red-400">
          <span>Fail:</span>
          <span className="font-mono font-medium">{data.fail_count}</span>
        </div>
        <div className="flex justify-between items-center text-blue-600 dark:text-blue-400">
          <span>Review:</span>
          <span className="font-mono font-medium">{data.review_count}</span>
        </div>
      </div>
      <div className="border-t pt-1 flex justify-between font-semibold text-foreground">
        <span>Total:</span>
        <span className="font-mono">{data.total_count}</span>
      </div>
    </div>
  );
}

function PChartTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0]?.payload;
  if (!data) return null;

  return (
    <div className="bg-popover text-popover-foreground border border-border shadow-md rounded-lg p-3 text-xs space-y-2 min-w-[210px]">
      <div className="flex items-center justify-between border-b pb-1">
        <span className="font-semibold text-foreground">{data.label}</span>
        {!data.reliable && (
          <span className="inline-flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
            <AlertTriangle className="h-3 w-3" />
            n &lt; 20 (Unreliable)
          </span>
        )}
      </div>

      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground">Evaluated (n):</span>
          <span className="font-mono font-medium">{data.evaluated_count}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-muted-foreground">Nonconforming:</span>
          <span className="font-mono font-medium">{data.nonconforming_count}</span>
        </div>
        <div className="flex justify-between items-center text-primary font-semibold">
          <span>p (Rate):</span>
          <span className="font-mono">
            {data.p_rate !== null ? `${(data.p_rate * 100).toFixed(2)}%` : "—"}
          </span>
        </div>
        <div className="flex justify-between items-center text-red-500 text-[11px]">
          <span>UCL (Upper Limit):</span>
          <span className="font-mono">{data.ucl !== null ? `${(data.ucl * 100).toFixed(2)}%` : "—"}</span>
        </div>
        <div className="flex justify-between items-center text-muted-foreground text-[11px]">
          <span>Centerline (p̄):</span>
          <span className="font-mono">{data.centerline !== null ? `${(data.centerline * 100).toFixed(2)}%` : "—"}</span>
        </div>
        <div className="flex justify-between items-center text-red-500 text-[11px]">
          <span>LCL (Lower Limit):</span>
          <span className="font-mono">{data.lcl !== null ? `${(data.lcl * 100).toFixed(2)}%` : "—"}</span>
        </div>
      </div>
    </div>
  );
}

export function AnalyticsView() {
  const [mode, setMode] = useState<"count" | "time">("count");
  const [bucketSize, setBucketSize] = useState<number>(20);
  const [interval, setInterval] = useState<string>("5m");
  const [basis, setBasis] = useState<"final" | "auto">("final");
  const [source, setSource] = useState<"all" | "synthetic" | "real">("all");

  const [data, setData] = useState<StatusSeriesResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Initial and parameter change fetch
  useEffect(() => {
    let active = true;
    getStatusSeries({
      mode,
      basis,
      source,
      bucket_size: mode === "count" ? bucketSize : undefined,
      interval: mode === "time" ? interval : undefined,
    })
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          if (err instanceof ApiError) {
            setError(`${err.code}: ${err.message}`);
          } else if (err instanceof Error) {
            setError(err.message);
          } else {
            setError("Failed to load analytics");
          }
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [mode, basis, source, bucketSize, interval]);

  // Live WebSocket inspection event subscription with >= 1s debounce
  const { latestInspection } = useLive();
  useEffect(() => {
    if (latestInspection) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        getStatusSeries({
          mode,
          basis,
          source,
          bucket_size: mode === "count" ? bucketSize : undefined,
          interval: mode === "time" ? interval : undefined,
        })
          .then((res) => {
            setData(res);
            setError(null);
          })
          .catch(() => {});
      }, 1000);
    }
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [latestInspection, mode, basis, source, bucketSize, interval]);

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight">Quality Analytics &amp; Control</h1>
            {data?.has_synthetic && (
              <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                <Bot className="h-3 w-3" />
                SYNTHETIC DATA
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Status time-series and Shewhart p-chart for statistical process control (Review excluded from nonconforming rate).
          </p>
        </div>

        <button
          onClick={() => fetchData(false)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border bg-card hover:bg-muted text-foreground transition-colors self-start sm:self-auto"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Filter Controls Bar */}
      <div className="p-4 rounded-xl border bg-card/60 backdrop-blur-sm shadow-sm grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Mode & Bucket */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
            <Layers className="h-3 w-3" /> Grouping Mode
          </label>
          <div className="flex gap-2">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "count" | "time")}
              className="flex-1 text-xs bg-background border border-border rounded-md px-2.5 py-1.5 focus:ring-1 focus:ring-primary"
            >
              <option value="count">By Inspection Count</option>
              <option value="time">By Time Interval</option>
            </select>
            {mode === "count" ? (
              <select
                value={bucketSize}
                onChange={(e) => setBucketSize(Number(e.target.value))}
                className="w-20 text-xs bg-background border border-border rounded-md px-2 py-1.5 focus:ring-1 focus:ring-primary"
              >
                <option value={10}>10 pcs</option>
                <option value={20}>20 pcs</option>
                <option value={50}>50 pcs</option>
              </select>
            ) : (
              <select
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                className="w-20 text-xs bg-background border border-border rounded-md px-2 py-1.5 focus:ring-1 focus:ring-primary"
              >
                <option value="1m">1 min</option>
                <option value="5m">5 min</option>
                <option value="15m">15 min</option>
                <option value="1h">1 hour</option>
              </select>
            )}
          </div>
        </div>

        {/* Basis */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
            <SlidersHorizontal className="h-3 w-3" /> Status Basis
          </label>
          <select
            value={basis}
            onChange={(e) => setBasis(e.target.value as "final" | "auto")}
            className="w-full text-xs bg-background border border-border rounded-md px-2.5 py-1.5 focus:ring-1 focus:ring-primary"
          >
            <option value="final">Final Status (With QA Overrides)</option>
            <option value="auto">Auto Decided Status (Pure CV)</option>
          </select>
        </div>

        {/* Source Filter */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
            <Bot className="h-3 w-3" /> Source Filter
          </label>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as "all" | "synthetic" | "real")}
            className="w-full text-xs bg-background border border-border rounded-md px-2.5 py-1.5 focus:ring-1 focus:ring-primary"
          >
            <option value="all">All Sources (Real + Synthetic)</option>
            <option value="synthetic">Synthetic Stream Only</option>
            <option value="real">Real Station Only (Webcam/File)</option>
          </select>
        </div>

        {/* Summary Info Pill */}
        <div className="space-y-1.5 flex flex-col justify-end">
          <div className="p-2 rounded-md bg-muted/40 border border-border text-[11px] text-muted-foreground">
            <span>Process Centerline (p̄): </span>
            <strong className="font-mono text-foreground">
              {data?.overall_p_bar !== null && data?.overall_p_bar !== undefined
                ? `${(data.overall_p_bar * 100).toFixed(2)}% nonconforming`
                : "—"}
            </strong>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-xs flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="p-3.5 rounded-xl border bg-card">
            <p className="text-xs text-muted-foreground">Total Inspected</p>
            <p className="text-lg font-bold font-mono mt-0.5">{data.total_inspections}</p>
          </div>
          <div className="p-3.5 rounded-xl border bg-card">
            <p className="text-xs text-muted-foreground">Evaluated (n)</p>
            <p className="text-lg font-bold font-mono mt-0.5">{data.total_evaluated}</p>
            <p className="text-[10px] text-muted-foreground">Excl. Review</p>
          </div>
          <div className="p-3.5 rounded-xl border bg-card">
            <p className="text-xs text-muted-foreground">Nonconforming</p>
            <p className="text-lg font-bold font-mono mt-0.5 text-amber-500">
              {data.total_nonconforming}
            </p>
            <p className="text-[10px] text-muted-foreground">Rework + Fail</p>
          </div>
          <div className="p-3.5 rounded-xl border bg-emerald-500/5 border-emerald-500/20">
            <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Pass</p>
            <p className="text-lg font-bold font-mono mt-0.5 text-emerald-600 dark:text-emerald-400">
              {data.pass_count}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border bg-amber-500/5 border-amber-500/20">
            <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">Rework</p>
            <p className="text-lg font-bold font-mono mt-0.5 text-amber-600 dark:text-amber-400">
              {data.rework_count}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border bg-red-500/5 border-red-500/20">
            <p className="text-xs text-red-600 dark:text-red-400 font-medium">Fail</p>
            <p className="text-lg font-bold font-mono mt-0.5 text-red-600 dark:text-red-400">
              {data.fail_count}
            </p>
          </div>
          <div className="p-3.5 rounded-xl border bg-blue-500/5 border-blue-500/20">
            <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">Review</p>
            <p className="text-lg font-bold font-mono mt-0.5 text-blue-600 dark:text-blue-400">
              {data.review_count}
            </p>
          </div>
        </div>
      )}

      {/* Main Charts */}
      {data && data.buckets.length > 0 ? (
        <div className="space-y-6">
          {/* Chart 1: Stacked Bar Chart */}
          <div className="p-5 rounded-xl border bg-card shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold">Inspection Status Composition</h2>
              </div>
              <span className="text-xs text-muted-foreground font-mono">
                {data.buckets.length} buckets
              </span>
            </div>

            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.buckets} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                  <Tooltip content={<StatusTooltip />} />
                  <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                  <Bar dataKey="pass_count" name="Pass" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="rework_count" name="Rework" stackId="a" fill="#f59e0b" />
                  <Bar dataKey="fail_count" name="Fail" stackId="a" fill="#ef4444" />
                  <Bar dataKey="review_count" name="Review" stackId="a" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Chart 2: Shewhart p-Chart */}
          <div className="p-5 rounded-xl border bg-card shadow-sm space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold">Shewhart p-Chart (Fraction Nonconforming)</h2>
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-red-500"></span> UCL / LCL
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-primary"></span> p-rate
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-500">
                  <AlertTriangle className="h-3 w-3" /> Flagged if n &lt; 20
                </span>
              </div>
            </div>

            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.buckets} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    domain={[0, (dataMax: number) => Math.max(0.2, Math.min(1.0, dataMax * 1.25))]}
                    tickFormatter={(val: number) => `${(val * 100).toFixed(0)}%`}
                  />
                  <Tooltip content={<PChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                  <Line
                    type="monotone"
                    dataKey="ucl"
                    name="Upper Control Limit (UCL)"
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    dot={false}
                    strokeWidth={1.5}
                  />
                  <Line
                    type="monotone"
                    dataKey="centerline"
                    name="Centerline (p̄)"
                    stroke="#94a3b8"
                    strokeDasharray="2 2"
                    dot={false}
                    strokeWidth={1.5}
                  />
                  <Line
                    type="monotone"
                    dataKey="lcl"
                    name="Lower Control Limit (LCL)"
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    dot={false}
                    strokeWidth={1.5}
                  />
                  <Line
                    type="monotone"
                    dataKey="p_rate"
                    name="Nonconforming Rate (p)"
                    stroke="#0284c7"
                    strokeWidth={2.5}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      ) : (
        <div className="h-[320px] border border-dashed rounded-xl flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
          <BarChart3 className="h-10 w-10 stroke-1 mb-2 opacity-50" />
          <p className="text-sm font-medium">No inspection data matching current filters</p>
          <p className="text-xs mt-1">
            Start the inspection station pipeline or select a different filter to see quality control analytics.
          </p>
        </div>
      )}
    </div>
  );
}
