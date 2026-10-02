from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def generate_prop_label(
    prop_id: str,
    width_mm: float = 100.0,
    height_mm: float = 40.0,
    dpi: int = 300,
) -> np.ndarray:
    px_per_mm = dpi / 25.4

    label_w_px = int(round(width_mm * px_per_mm))
    label_h_px = int(round(height_mm * px_per_mm))

    canvas = np.full((label_h_px, label_w_px, 3), 255, dtype=np.uint8)

    # Thin cut border
    cv2.rectangle(canvas, (0, 0), (label_w_px - 1, label_h_px - 1), (180, 180, 180), 1)

    # Generate QR Code
    qr_side_mm = min(30.0, height_mm - 8.0)
    qr_side_px = int(round(qr_side_mm * px_per_mm))

    qr_enc = cv2.QRCodeEncoder.create()
    raw_qr = qr_enc.encode(prop_id)
    if raw_qr is not None:
        qr_with_border = cv2.copyMakeBorder(raw_qr, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=255)
        qr_resized = cv2.resize(qr_with_border, (qr_side_px, qr_side_px), interpolation=cv2.INTER_NEAREST)
        qr_bgr = cv2.cvtColor(qr_resized, cv2.COLOR_GRAY2BGR)

        margin_x = int(round(4.0 * px_per_mm))
        margin_y = (label_h_px - qr_side_px) // 2
        canvas[margin_y : margin_y + qr_side_px, margin_x : margin_x + qr_side_px] = qr_bgr
    else:
        margin_x = 0
        qr_side_px = 0

    # Draw large bold ID text
    text_x = margin_x + qr_side_px + int(round(6.0 * px_per_mm))
    text_y = int(label_h_px * 0.62)

    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = 1.4 * (dpi / 300.0)
    thickness = max(2, int(round(3.0 * (dpi / 300.0))))

    cv2.putText(canvas, prop_id, (text_x, text_y), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)

    # Subtitle
    sub_y = int(label_h_px * 0.85)
    cv2.putText(
        canvas,
        "BILLET VISION ID",
        (text_x, sub_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale * 0.45,
        (100, 100, 100),
        1,
        cv2.LINE_AA,
    )

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate printable ID labels with QR code at 300 DPI")
    parser.add_argument("--ids", type=str, required=True, help="Path to props CSV file")
    parser.add_argument("--out", type=str, default="../print/", help="Output directory for label PNGs")
    parser.add_argument("--dpi", type=int, default=300, help="Print DPI")
    args = parser.parse_args()

    csv_path = Path(args.ids).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not csv_path.is_file():
        print(f"Error: CSV file not found: {csv_path}")
        return

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            prop_id = row.get("prop_id", "").strip()
            if not prop_id:
                continue

            try:
                width_mm = float(row.get("width_mm", 100.0))
            except (ValueError, TypeError):
                width_mm = 100.0

            img_arr = generate_prop_label(
                prop_id=prop_id,
                width_mm=max(80.0, width_mm),
                height_mm=40.0,
                dpi=args.dpi,
            )

            out_file = out_dir / f"label_{prop_id}.png"
            pil_img = Image.fromarray(img_arr)
            pil_img.save(str(out_file), dpi=(args.dpi, args.dpi))
            print(f"Generated label: {out_file} (Prop {prop_id})")
            count += 1

        print(f"Done: {count} labels generated in {out_dir}")


if __name__ == "__main__":
    main()
