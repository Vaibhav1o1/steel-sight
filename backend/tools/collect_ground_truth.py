#!/usr/bin/env python3
"""Interactive tool to log physical ground-truth measurements fast and mistake-proof.

Prompts for object id, caliper values, instrument resolution, condition, and notes,
then appends to data/ground_truth.csv.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

COLUMNS: list[str] = [
    "object_id",
    "true_length_mm",
    "true_width_mm",
    "instrument_resolution_mm",
    "condition",
    "notes",
]


def prompt_float(prompt_text: str, default: float | None = None) -> float:
    while True:
        def_str = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt_text}{def_str}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = float(raw)
            if val > 0:
                return val
            print("Value must be positive.")
        except ValueError:
            print("Please enter a valid floating-point number.")


def prompt_string(prompt_text: str, default: str = "") -> str:
    def_str = f" [{default}]" if default else ""
    raw = input(f"{prompt_text}{def_str}: ").strip()
    return raw if raw else default


def append_ground_truth(
    csv_path: Path,
    obj_id: str,
    length_mm: float,
    width_mm: float,
    resolution_mm: float = 0.05,
    condition: str = "nominal",
    notes: str = "",
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not csv_path.is_file() or csv_path.stat().st_size == 0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow(
            {
                "object_id": obj_id,
                "true_length_mm": round(length_mm, 2),
                "true_width_mm": round(width_mm, 2),
                "instrument_resolution_mm": round(resolution_mm, 3),
                "condition": condition,
                "notes": notes,
            }
        )
    print(f"Logged {obj_id} ({length_mm:.1f}x{width_mm:.1f} mm) to {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Log physical ground truth measurements.")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "data" / "ground_truth.csv",
        help="Path to ground_truth.csv",
    )
    parser.add_argument("--id", type=str, help="Object ID (e.g. PROP-01, H24-1187)")
    parser.add_argument("--length", type=float, help="True length in mm")
    parser.add_argument("--width", type=float, help="True width in mm")
    parser.add_argument("--res", type=float, default=0.05, help="Instrument resolution in mm")
    parser.add_argument(
        "--condition",
        type=str,
        default="nominal",
        choices=["nominal", "notch", "camber", "taper", "bulge", "oversize", "undersize", "other"],
    )
    parser.add_argument("--notes", type=str, default="", help="Optional notes")

    args = parser.parse_args()

    # Non-interactive mode if required args provided
    if args.id and args.length and args.width:
        append_ground_truth(
            args.file,
            args.id,
            args.length,
            args.width,
            args.res,
            args.condition,
            args.notes,
        )
        return

    # Interactive mode
    print("\n--- BilletVision Ground Truth Data Logger ---")
    print(f"Target: {args.file}\n")

    try:
        while True:
            obj_id = prompt_string("Object ID (or 'q' to quit)")
            if not obj_id or obj_id.lower() == "q":
                break

            length_mm = prompt_float("True Length (mm) [caliper measurement]")
            width_mm = prompt_float("True Width (mm) [caliper measurement]")
            res_mm = prompt_float("Instrument resolution (mm)", default=0.05)
            condition = prompt_string("Condition (nominal/notch/camber/taper/etc.)", default="nominal")
            notes = prompt_string("Notes / orientation", default="")

            append_ground_truth(args.file, obj_id, length_mm, width_mm, res_mm, condition, notes)
            print("-" * 40)
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
