from __future__ import annotations

import time

import cv2
import numpy as np
from rapidocr import RapidOCR


def run_smoke_test() -> tuple[str, float, float]:
    """Renders 'H24-1187' with cv2.putText on a grey image, runs RapidOCR,

    and returns (text, score, elapsed_ms).
    """
    # Create grey image (160 grey levels) and render text
    img = np.full((120, 400, 3), 160, dtype=np.uint8)
    cv2.putText(
        img,
        "H24-1187",
        (30, 75),
        cv2.FONT_HERSHEY_DUPLEX,
        1.5,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )

    t0 = time.perf_counter()
    engine = RapidOCR()
    result = engine(img)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    detected_text = ""
    score = 0.0

    if result is not None:
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if txts is None and isinstance(result, tuple) and len(result) > 0:
            first_elem = result[0]
            if first_elem and isinstance(first_elem, list):
                txts = [item[1] for item in first_elem]
                scores = [item[2] for item in first_elem]

        if txts and len(txts) > 0:
            detected_text = str(txts[0])
            score = float(scores[0]) if scores and len(scores) > 0 else 0.0

    return detected_text, score, elapsed_ms


def main() -> None:
    text, score, elapsed_ms = run_smoke_test()
    if text:
        print(f"H24-1187 detected as '{text}' | score={score:.4f} | elapsed={elapsed_ms:.1f}ms")
    else:
        print(f"FAILED: No text detected | elapsed={elapsed_ms:.1f}ms")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
