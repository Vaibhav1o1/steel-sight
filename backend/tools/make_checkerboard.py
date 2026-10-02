from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def generate_checkerboard(
    inner_corners: tuple[int, int] = (9, 6),
    square_mm: float = 25.0,
    dpi: int = 300,
) -> np.ndarray:
    px_per_mm = dpi / 25.4
    cols = inner_corners[0] + 1  # 10 squares
    rows = inner_corners[1] + 1  # 7 squares
    square_px = int(round(square_mm * px_per_mm))

    board_w_px = cols * square_px
    board_h_px = rows * square_px

    margin_px = int(round(20.0 * px_per_mm))
    scale_bar_h_px = int(round(4.0 * px_per_mm))
    scale_bar_len_px = int(round(100.0 * px_per_mm))
    text_h_px = int(round(20.0 * px_per_mm))

    canvas_w = board_w_px + 2 * margin_px
    canvas_h = board_h_px + 2 * margin_px + scale_bar_h_px + text_h_px + int(round(10.0 * px_per_mm))

    canvas = np.full((canvas_h, canvas_w), 255, dtype=np.uint8)

    # Draw checkerboard pattern
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 1:
                y0 = margin_px + r * square_px
                x0 = margin_px + c * square_px
                canvas[y0 : y0 + square_px, x0 : x0 + square_px] = 0

    # Scale bar
    bar_y = margin_px + board_h_px + int(round(12.0 * px_per_mm))
    bar_x = (canvas_w - scale_bar_len_px) // 2
    canvas[bar_y : bar_y + scale_bar_h_px, bar_x : bar_x + scale_bar_len_px] = 0

    tick_h = int(round(4.0 * px_per_mm))
    cv2.line(canvas, (bar_x, bar_y - tick_h), (bar_x, bar_y + scale_bar_h_px + tick_h), 0, 2)
    mid_x = bar_x + scale_bar_len_px // 2
    cv2.line(canvas, (mid_x, bar_y - tick_h), (mid_x, bar_y + scale_bar_h_px + tick_h), 0, 2)
    end_x = bar_x + scale_bar_len_px
    cv2.line(canvas, (end_x, bar_y - tick_h), (end_x, bar_y + scale_bar_h_px + tick_h), 0, 2)

    # Label text
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.75
    text_y = bar_y + scale_bar_h_px + int(round(12.0 * px_per_mm))
    label = (
        f"Checkerboard {inner_corners[0]}x{inner_corners[1]} "
        f"({square_mm:.0f} mm squares) — Measure scale bar (100 mm)"
    )
    cv2.putText(
        canvas,
        label,
        (bar_x - 120, text_y),
        font,
        font_scale,
        0,
        2,
        cv2.LINE_AA,
    )

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate printable checkerboard calibration pattern at 300 DPI"
    )
    parser.add_argument("--corners-x", type=int, default=9, help="Inner corners horizontally")
    parser.add_argument("--corners-y", type=int, default=6, help="Inner corners vertically")
    parser.add_argument("--square-mm", type=float, default=25.0, help="Square side in mm")
    parser.add_argument("--dpi", type=int, default=300, help="Print DPI")
    parser.add_argument(
        "--out", type=str, default="../print/checkerboard_9x6_25mm.png", help="Output PNG path"
    )
    args = parser.parse_args()

    img_arr = generate_checkerboard(
        inner_corners=(args.corners_x, args.corners_y),
        square_mm=args.square_mm,
        dpi=args.dpi,
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pil_img = Image.fromarray(img_arr)
    pil_img.save(str(out_path), dpi=(args.dpi, args.dpi))
    print(
        f"Generated printable checkerboard: {out_path.name} "
        f"({args.corners_x}x{args.corners_y}, {args.square_mm} mm)"
    )


if __name__ == "__main__":
    main()
