from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from billetvision.vision.synth import render_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic demo video and ground-truth JSON sidecar."
    )
    parser.add_argument(
        "--out",
        type=str,
        default="../data/videos/synth_demo.mp4",
        help="Path to output MP4 file (default: ../data/videos/synth_demo.mp4)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["station", "conveyor"],
        default="station",
        help="Inspection mode: 'station' or 'conveyor' (default: station)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=3,
        help="Number of billets to generate (default: 3)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Video frame rate in fps (default: 30)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )

    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_path.with_suffix(".json")

    logger.info(
        "Generating synthetic video (%s mode, %d billets, %d fps) to %s",
        args.mode,
        args.n,
        args.fps,
        out_path,
    )
    rng = np.random.default_rng(args.seed)

    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    writer: cv2.VideoWriter | None = None
    frame_count = 0

    seen_billets: dict[str, dict[str, Any]] = {}

    for frame, gt_billets in render_video(rng, mode=args.mode, n_billets=args.n, fps=args.fps):
        if writer is None:
            h, w = frame.shape[:2]
            writer = cv2.VideoWriter(str(out_path), fourcc, float(args.fps), (w, h))

        writer.write(frame)
        frame_count += 1

        for gb in gt_billets:
            key = f"{gb.id_text}_{gb.length_mm:.1f}_{gb.width_mm:.1f}"
            if key not in seen_billets:
                seen_billets[key] = {
                    "id_text": gb.id_text,
                    "length_mm": round(gb.length_mm, 2),
                    "width_mm": round(gb.width_mm, 2),
                    "angle_deg": round(gb.angle_deg, 2),
                    "qr": gb.qr,
                    "defect": gb.defect,
                    "defect_size_mm": round(gb.defect_size_mm, 2),
                }

    if writer is not None:
        writer.release()

    billets_data = list(seen_billets.values())
    sidecar_data = {
        "mode": args.mode,
        "fps": args.fps,
        "n_frames": frame_count,
        "n_billets": len(billets_data),
        "billets": billets_data,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sidecar_data, f, indent=2)

    logger.info(
        "Successfully wrote %d frames to %s and ground truth (%d billets) to %s",
        frame_count,
        out_path,
        len(billets_data),
        json_path,
    )


if __name__ == "__main__":
    main()
