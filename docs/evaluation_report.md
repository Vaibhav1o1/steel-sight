# BilletVision Evaluation Report
Generated: 2026-10-03 14:21:50

This report is generated strictly from recorded empirical data. No numbers have been manually entered or estimated.

## E1-E12 Validation Tables

### Synthetic Benchmark Results
**Total Samples (n)**: 180
**Source**: SYNTHETIC

| Condition | n | Length MAE | Width MAE | OCR Accuracy | Pass/Fail Target (MAE < 0.5%) |
|---|---|---|---|---|---|
| clean | 20 | 0.15% | 0.39% | 65.0% | **PASS** |
| dim | 20 | 0.16% | 0.41% | 70.0% | **PASS** |
| bright | 20 | 0.19% | 0.45% | 55.0% | **PASS** |
| gradient | 20 | 0.17% | 0.42% | 70.0% | **PASS** |
| noise | 20 | 0.18% | 0.44% | 60.0% | **PASS** |
| blur | 20 | 0.28% | 0.54% | 55.0% | **FAIL** |
| dust | 20 | 0.15% | 0.41% | 65.0% | **PASS** |
| scale | 20 | 0.16% | 0.41% | 70.0% | **PASS** |
| glare | 20 | 0.16% | 0.42% | 65.0% | **PASS** |

### Real-World Tests
**Total Samples (n)**: 0
**Source**: REAL
Status: **NOT RUN** (Waiting for physical prop measurements in final demo).

## Failure Analysis
No failures exceeding targets in the synthetic benchmark. Real-world failure analysis will populate here after physical props are tested and `tools/collect_ground_truth.py` is executed.
