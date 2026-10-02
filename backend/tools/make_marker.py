from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def generate_marker_image(
    marker_mm: float = 80.0,
    border_mm: float = 10.0,
    dpi: int = 300,
    marker_id: int = 0,
    dict_name: str = "DICT_4X4_50",
) -> np.ndarray:
    px_per_mm = dpi / 25.4

    marker_px = int(round(marker_mm * px_per_mm))
    border_px = int(round(border_mm * px_per_mm))
    bar_len_px = int(round(100.0 * px_per_mm))  # 100 mm scale bar
    bar_h_px = int(round(4.0 * px_per_mm))

    # Generate ArUco marker
    dict_attr = getattr(cv2.aruco, dict_name, cv2.aruco.DICT_4X4_50)
    aruco_dict = cv2.aruco.getPredefinedDictionary(dict_attr)
    marker_core = cv2.aruco.generateImageMarker(aruco_dict, marker_id, marker_px)

    # Marker with white border
    total_marker_w = marker_px + 2 * border_px
    total_marker_h = marker_px + 2 * border_px

    # Layout:
    # Top margin: 20 mm
    # Marker block
    # Gap: 15 mm
    # Scale bar + text
    # Bottom margin: 20 mm
    margin_top_px = int(round(15.0 * px_per_mm))
    gap_px = int(round(12.0 * px_per_mm))
    margin_bottom_px = int(round(20.0 * px_per_mm))
    text_area_h_px = int(round(25.0 * px_per_mm))

    canvas_w = max(total_marker_w + 2 * border_px, bar_len_px + 2 * border_px) + int(round(20.0 * px_per_mm))
    canvas_h = margin_top_px + total_marker_h + gap_px + bar_h_px + text_area_h_px + margin_bottom_px

    canvas = np.full((canvas_h, canvas_w), 255, dtype=np.uint8)

    # Place marker
    mx = (canvas_w - marker_px) // 2
    my = margin_top_px + border_px
    canvas[my : my + marker_px, mx : mx + marker_px] = marker_core

    # Draw thin black outline around the 10mm white border so cut-out is visible
    bx0 = (canvas_w - total_marker_w) // 2
    by0 = margin_top_px
    cv2.rectangle(canvas, (bx0, by0), (bx0 + total_marker_w, by0 + total_marker_h), 180, 1)

    # Scale bar (100 mm)
    bar_y = by0 + total_marker_h + gap_px
    bar_x = (canvas_w - bar_len_px) // 2
    canvas[bar_y : bar_y + bar_h_px, bar_x : bar_x + bar_len_px] = 0

    # Draw scale bar ticks (start, 50mm, 100mm)
    tick_h = int(round(4.0 * px_per_mm))
    cv2.line(canvas, (bar_x, bar_y - tick_h), (bar_x, bar_y + bar_h_px + tick_h), 0, 2)
    mid_x = bar_x + bar_len_px // 2
    cv2.line(canvas, (mid_x, bar_y - tick_h), (mid_x, bar_y + bar_h_px + tick_h), 0, 2)
    end_x = bar_x + bar_len_px
    cv2.line(canvas, (end_x, bar_y - tick_h), (end_x, bar_y + bar_h_px + tick_h), 0, 2)

    # Text
    label1 = "Print at 100% — measure the bar (100 mm)"
    label2 = f"Marker: {marker_mm:.0f} mm ({dict_name}, ID {marker_id})"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    y_text1 = bar_y + bar_h_px + int(round(12.0 * px_per_mm))
    y_text2 = bar_y + bar_h_px + int(round(22.0 * px_per_mm))
    cv2.putText(canvas, label1, (bar_x - 30, y_text1), font, font_scale, 0, 2, cv2.LINE_AA)
    cv2.putText(canvas, label2, (bar_x + 60, y_text2), font, font_scale * 0.8, 80, 1, cv2.LINE_AA)

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate printable ArUco marker PNG at 300 DPI")
    parser.add_argument("--mm", type=float, default=80.0, help="Marker side length in mm")
    parser.add_argument("--border-mm", type=float, default=10.0, help="White border in mm")
    parser.add_argument("--dpi", type=int, default=300, help="Print DPI")
    parser.add_argument("--id", type=int, default=0, help="Marker ID")
    parser.add_argument("--dict", type=str, default="DICT_4X4_50", help="ArUco dictionary name")
    parser.add_argument("--out", type=str, default="../print/marker_80mm.png", help="Output PNG path")
    args = parser.parse_args()

    img_arr = generate_marker_image(
        marker_mm=args.mm,
        border_mm=args.border_mm,
        dpi=args.dpi,
        marker_id=args.id,
        dict_name=args.dict,
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pil_img = Image.fromarray(img_arr)
    pil_img.save(str(out_path), dpi=(args.dpi, args.dpi))
    print(f"Generated printable marker: {out_path} ({args.mm} mm, {args.dpi} DPI)")


if __name__ == "__main__":
    main()
