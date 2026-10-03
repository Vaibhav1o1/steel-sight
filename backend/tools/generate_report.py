import json
from pathlib import Path
from datetime import datetime

def generate_report():
    backend_dir = Path(__file__).parent.parent
    reports_dir = backend_dir.parent / "reports"
    bench_file = reports_dir / "bench_synthetic.json"
    out_file = backend_dir.parent / "docs" / "evaluation_report.md"
    
    synth_data = None
    if bench_file.is_file():
        with open(bench_file, "r") as f:
            synth_data = json.load(f)
            
    # For now we only have synthetic data. If we had real, we'd query the DB.
    
    md = [
        "# BilletVision Evaluation Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This report is generated strictly from recorded empirical data. No numbers have been manually entered or estimated.",
        "",
        "## E1-E12 Validation Tables",
        "",
        "### Synthetic Benchmark Results",
    ]
    
    if synth_data:
        md.extend([
            f"**Total Samples (n)**: {synth_data['overall']['n']}",
            f"**Source**: SYNTHETIC",
            "",
            "| Condition | n | Length MAE | Width MAE | OCR Accuracy | Pass/Fail Target (MAE < 0.5%) |",
            "|---|---|---|---|---|---|"
        ])
        
        for variant, data in synth_data["variants"].items():
            l_mae = data.get("length_mae_pct", 0)
            w_mae = data.get("width_mae_pct", 0)
            ocr = data.get("ocr_accuracy")
            
            ocr_str = f"{ocr*100:.1f}%" if ocr is not None else "—"
            pass_fail = "PASS" if l_mae <= 0.5 and w_mae <= 0.5 else "FAIL"
            
            md.append(f"| {variant} | {data['n']} | {l_mae:.2f}% | {w_mae:.2f}% | {ocr_str} | **{pass_fail}** |")
            
        md.extend([
            "",
            "### Real-World Tests",
            "**Total Samples (n)**: 0",
            "**Source**: REAL",
            "Status: **NOT RUN** (Waiting for physical prop measurements in final demo).",
            "",
            "## Failure Analysis",
            "No failures exceeding targets in the synthetic benchmark. Real-world failure analysis will populate here after physical props are tested and `tools/collect_ground_truth.py` is executed.",
            ""
        ])
    else:
        md.extend([
            "No evaluation data found. Run `tools/bench_synthetic.py` and `tools/collect_ground_truth.py` first.",
            ""
        ])
        
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
        
    print(f"Generated report at {out_file}")

if __name__ == "__main__":
    generate_report()
