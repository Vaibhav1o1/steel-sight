"use client";

import { useEffect, useState } from "react";
import { getEval } from "@/lib/api";
import type { EvalResponse, EvalReal, SyntheticBench } from "@/lib/types";
import { formatPct } from "@/lib/format";

function Stat({ label, value, source, n }: { label: string; value: string; source: "REAL" | "SYNTHETIC" | null; n?: number }) {
  return (
    <div className="flex flex-col border rounded-lg p-4 bg-card">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-2xl font-bold font-mono">{value}</span>
      </div>
      <div className="mt-auto pt-4 flex items-center gap-2">
        <Badge source={source} n={n} />
      </div>
    </div>
  );
}

function Badge({ source, n }: { source: "REAL" | "SYNTHETIC" | null; n?: number }) {
  if (!source) return <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">Not measured</span>;
  
  const color = source === "REAL" 
    ? "bg-blue-500/10 text-blue-700 border border-blue-500/30" 
    : "bg-purple-500/10 text-purple-700 border border-purple-500/30";
    
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${color}`}>
      {source} {n !== undefined ? `(n=${n})` : ""}
    </span>
  );
}

export function AccuracyView() {
  const [data, setData] = useState<EvalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEval()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-center text-muted-foreground">Loading evaluation data...</div>;
  if (error) return <div className="p-8 text-center text-destructive">{error}</div>;
  if (!data) return null;

  const real = data.real;
  const synth = data.synthetic;

  // Derive top-line numbers prioritizing REAL over SYNTHETIC
  const L_mae = real ? formatPct(real.length_mae_pct) : synth ? formatPct(synth.overall.length_mae_pct) : "—";
  const L_src = real ? "REAL" : synth ? "SYNTHETIC" : null;
  const L_n = real ? real.n_inspections : synth ? synth.overall.n : undefined;

  const W_mae = real ? formatPct(real.width_mae_pct) : synth ? formatPct(synth.overall.width_mae_pct) : "—";
  
  const ocr_acc = real?.ocr_accuracy != null ? formatPct(real.ocr_accuracy) : synth?.overall.ocr_accuracy != null ? formatPct(synth.overall.ocr_accuracy) : "—";
  const ocr_src = real?.ocr_accuracy != null ? "REAL" : synth?.overall.ocr_accuracy != null ? "SYNTHETIC" : null;
  const ocr_n = real?.ocr_accuracy != null ? real.ocr_n : synth?.overall.ocr_accuracy != null ? synth.overall.n : undefined;

  return (
    <div className="p-4 max-w-5xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Accuracy & Evaluation</h1>
        <p className="text-muted-foreground mt-1">
          Metrics exactly as computed from recorded data. Honest numbers only.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Stat label="Length MAE" value={L_mae} source={L_src} n={L_n} />
        <Stat label="Width MAE" value={W_mae} source={L_src} n={L_n} />
        <Stat label="OCR Exact Match" value={ocr_acc} source={ocr_src} n={ocr_n} />
      </div>

      <div className="space-y-4">
        <h2 className="text-lg font-bold border-b pb-2">Real Validation (Target: MAE &lt; 0.5%)</h2>
        {real ? (
          <div className="border rounded-lg overflow-hidden bg-card text-sm">
            <table className="w-full text-left">
              <thead className="bg-muted/50 border-b">
                <tr>
                  <th className="px-4 py-2">Condition / Prop</th>
                  <th className="px-4 py-2">n</th>
                  <th className="px-4 py-2 text-right">Length MAE</th>
                  <th className="px-4 py-2 text-right">Width MAE</th>
                  <th className="px-4 py-2 text-right">OCR Accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {real.props.map((p, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2 font-medium">{p.prop_id}</td>
                    <td className="px-4 py-2 text-muted-foreground">{p.n}</td>
                    <td className="px-4 py-2 font-mono text-right">{formatPct(p.length_error_pct)}</td>
                    <td className="px-4 py-2 font-mono text-right">{formatPct(p.width_error_pct)}</td>
                    <td className="px-4 py-2 font-mono text-right">{p.ocr_correct_rate != null ? formatPct(p.ocr_correct_rate) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 border rounded-lg bg-card text-center text-muted-foreground">
            No real measurements have been recorded yet. 
            <br/>Run <code className="text-xs bg-muted px-1 rounded">tools/collect_ground_truth.py</code> to log tests.
          </div>
        )}
      </div>

      <div className="space-y-4 opacity-80 hover:opacity-100 transition-opacity">
        <h2 className="text-lg font-bold border-b pb-2">Synthetic Benchmark</h2>
        {synth ? (
          <div className="border rounded-lg overflow-hidden bg-card text-sm">
            <table className="w-full text-left">
              <thead className="bg-muted/50 border-b">
                <tr>
                  <th className="px-4 py-2">Variant</th>
                  <th className="px-4 py-2">n</th>
                  <th className="px-4 py-2 text-right">Length MAE</th>
                  <th className="px-4 py-2 text-right">Width MAE</th>
                  <th className="px-4 py-2 text-right">OCR Accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {Object.entries(synth.variants).map(([name, v]) => (
                  <tr key={name}>
                    <td className="px-4 py-2 font-medium capitalize">{name}</td>
                    <td className="px-4 py-2 text-muted-foreground">{v.n}</td>
                    <td className="px-4 py-2 font-mono text-right">{formatPct(v.length_mae_pct)}</td>
                    <td className="px-4 py-2 font-mono text-right">{formatPct(v.width_mae_pct)}</td>
                    <td className="px-4 py-2 font-mono text-right">{v.ocr_accuracy != null ? formatPct(v.ocr_accuracy) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 border rounded-lg bg-card text-center text-muted-foreground">
            Synthetic benchmark not run.
          </div>
        )}
      </div>
    </div>
  );
}
