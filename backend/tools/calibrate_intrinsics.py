from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import cv2
import numpy as np


def calibrate_camera_from_images(
    image_paths: list[str],
    inner_corners: tuple[int, int] = (9, 6),
    square_mm: float = 25.0,
) -> tuple[np.ndarray, np.ndarray, float, tuple[int, int], int] | None:
    objp = np.zeros((inner_corners[0] * inner_corners[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0 : inner_corners[0], 0 : inner_corners[1]].T.reshape(-1, 2) * square_mm

    obj_points: list[np.ndarray] = []
    img_points: list[np.ndarray] = []

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    img_size: tuple[int, int] | None = None

    for p in image_paths:
        img = cv2.imread(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        if img_size is None:
            img_size = (w, h)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, inner_corners, None)

        if found and corners is not None:
            obj_points.append(objp)
            refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            img_points.append(refined)

    if not obj_points or img_size is None:
        return None

    ret, mtx, dist, _, _ = cv2.calibrateCamera(obj_points, img_points, img_size, None, None)

    return mtx, dist, float(ret), img_size, len(obj_points)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate camera intrinsics from checkerboard images")
    parser.add_argument(
        "--images", type=str, default="../data/calib/*.jpg", help="Glob pattern for calibration images"
    )
    parser.add_argument("--corners-x", type=int, default=9, help="Inner corners horizontally")
    parser.add_argument("--corners-y", type=int, default=6, help="Inner corners vertically")
    parser.add_argument("--square-mm", type=float, default=25.0, help="Square side in mm")
    parser.add_argument("--out", type=str, default="calibration/intrinsics.json", help="Output JSON path")
    args = parser.parse_args()

    paths = sorted(glob.glob(args.images))
    if not paths:
        print(f"No calibration images found matching: {args.images}")
        return

    print(f"Found {len(paths)} images. Detecting {args.corners_x}x{args.corners_y} checkerboard corners...")
    result = calibrate_camera_from_images(
        image_paths=paths,
        inner_corners=(args.corners_x, args.corners_y),
        square_mm=args.square_mm,
    )

    if result is None:
        print("Error: Could not detect checkerboards in provided images.")
        return

    mtx, dist, rms, size, valid_count = result
    out_data = {
        "camera_matrix": mtx.tolist(),
        "dist_coeffs": dist.tolist(),
        "rms": rms,
        "image_size": list(size),
        "n_images": valid_count,
    }

    out_file = Path(args.out).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out_data, indent=2), encoding="utf-8")
    print(f"Intrinsics saved to {out_file} (RMS: {rms:.4f} px across {valid_count} images)")


if __name__ == "__main__":
    main()
