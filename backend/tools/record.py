#!/usr/bin/env python3
"""Record raw inspection station footage plus session manifest.

Usage:
    python -m tools.record --source synthetic --duration 10
    python -m tools.record --source webcam --device 0 --duration 30
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import cv2

from billetvision import config
from billetvision.runtime.sources import make_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("record")


def record_session(
    source_type: str = "synthetic",
    source_value: str = "",
    duration_s: float = 10.0,
    out_dir: Path | None = None,
    target_fps: int = config.CAPTURE_FPS,
) -> Path:
    out_path = out_dir or (Path(__file__).resolve().parent.parent.parent / "recordings")
    out_path.mkdir(parents=True, exist_ok=True)

    session_id = time.strftime("%Y%m%d_%H%M%S")
    video_filename = f"raw_{session_id}.mp4"
    video_path = out_path / video_filename
    manifest_path = out_path / "manifest.json"

    logger.info("Initializing source %s (%s)...", source_type, source_value)
    src = make_source(source_type, source_value)
    if not src.open():
        raise RuntimeError(f"Could not open source {source_type} ({source_value})")

    info = src.info()
    width = info.frame_width or config.FRAME_WIDTH
    height = info.frame_height or config.FRAME_HEIGHT

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, float(target_fps), (width, height))

    frames_written = 0
    start_t = time.monotonic()
    last_frame_t = start_t
    interval = 1.0 / max(target_fps, 1)

    logger.info("Recording to %s for %.1f s...", video_path, duration_s)

    try:
        while time.monotonic() - start_t < duration_s:
            now = time.monotonic()
            elapsed = now - last_frame_t
            if elapsed < interval:
                time.sleep(interval - elapsed)

            res = src.read()
            if res is None:
                time.sleep(0.01)
                continue

            frame, _ = res
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            writer.write(frame)
            frames_written += 1
            last_frame_t = time.monotonic()

    except KeyboardInterrupt:
        logger.info("Recording interrupted by user.")
    finally:
        writer.release()
        src.close()

    actual_duration = time.monotonic() - start_t
    actual_fps = frames_written / max(actual_duration, 0.001)

    session_entry = {
        "session_id": session_id,
        "video_file": video_filename,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_type": source_type,
        "source_value": source_value,
        "resolution": [width, height],
        "frames_recorded": frames_written,
        "duration_seconds": round(actual_duration, 2),
        "actual_fps": round(actual_fps, 1),
    }

    # Append to manifest list
    manifest_data: list[dict] = []
    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest_data, list):
                manifest_data = []
        except Exception:
            manifest_data = []

    manifest_data.append(session_entry)
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    logger.info(
        "Saved %d frames (%.1f s, %.1f FPS) to %s",
        frames_written,
        actual_duration,
        actual_fps,
        video_path,
    )
    return video_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Record raw video footage and session manifest.")
    parser.add_argument(
        "--source",
        type=str,
        default="synthetic",
        choices=["synthetic", "webcam", "url", "file"],
    )
    parser.add_argument("--value", type=str, default="", help="Device index, URL, or file path")
    parser.add_argument("--duration", type=float, default=5.0, help="Duration in seconds")
    parser.add_argument("--fps", type=int, default=30, help="Target recording FPS")
    args = parser.parse_args()

    record_session(
        source_type=args.source,
        source_value=args.value,
        duration_s=args.duration,
        target_fps=args.fps,
    )


if __name__ == "__main__":
    main()
