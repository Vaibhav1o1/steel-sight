#!/usr/bin/env python3
"""Record video from camera, synthetic, or stream for testing or demo backup.

Usage:
    python -m tools.record_video --seconds 60 --out ../data/videos/real_demo.mp4
    python -m tools.record_video --seconds 5 --out ../data/videos/check.mp4 --source synthetic
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from billetvision import config
from billetvision.runtime.sources import make_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("record_video")


def record_video(
    out_file: Path,
    seconds: float = 5.0,
    source_type: str = "webcam",
    source_value: str = "0",
    target_fps: int = config.CAPTURE_FPS,
) -> Path:
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    src = make_source(source_type, source_value)
    if not src.open():
        raise RuntimeError(f"Could not open source {source_type} ({source_value})")

    info = src.info()
    width = info.frame_width or config.FRAME_WIDTH
    height = info.frame_height or config.FRAME_HEIGHT
    logger.info("Source opened: %dx%d @ %s fps", width, height, target_fps)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_file), fourcc, float(target_fps), (width, height))

    frames_written = 0
    start_t = time.monotonic()
    try:
        while time.monotonic() - start_t < seconds:
            res = src.read()
            if res is None:
                time.sleep(0.01)
                continue
            frame, _ = res
            writer.write(frame)
            frames_written += 1
    finally:
        writer.release()
        src.close()

    actual_duration = time.monotonic() - start_t
    actual_fps = frames_written / max(actual_duration, 1e-6)
    logger.info(
        "Recorded %d frames in %.1f s (%.1f fps) -> %s",
        frames_written,
        actual_duration,
        actual_fps,
        out_file,
    )
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Record video from camera or synthetic source.")
    parser.add_argument("--seconds", type=float, default=5.0, help="Duration in seconds")
    parser.add_argument("--out", type=str, default="../data/videos/check.mp4", help="Output video file path")
    parser.add_argument(
        "--source",
        type=str,
        default="webcam",
        choices=["webcam", "synthetic", "url", "file"],
        help="Input source type",
    )
    parser.add_argument("--device", type=str, default="0", help="Webcam device index or URL/path")
    args = parser.parse_args()

    record_video(
        out_file=Path(args.out),
        seconds=args.seconds,
        source_type=args.source,
        source_value=args.device,
    )


if __name__ == "__main__":
    main()
