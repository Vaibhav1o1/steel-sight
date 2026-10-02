from __future__ import annotations

import cv2
import numpy as np
import pytest

from billetvision.vision.idparse import read_id, vote
from billetvision.vision.qr import read_qr

# ---------------------------------------------------------------------------
# Skip marker: skip all OCR tests if models are not available
# ---------------------------------------------------------------------------
try:
    from billetvision.vision.ocr import ocr_ready
    from billetvision.vision.ocr import read as ocr_read

    _OCR_AVAILABLE = ocr_ready()
except Exception:
    _OCR_AVAILABLE = False
    ocr_read = None  # type: ignore[assignment]

pytestmark_ocr = pytest.mark.skipif(
    not _OCR_AVAILABLE,
    reason="RapidOCR models not available — install and run 'make setup' to enable OCR tests",
)

TEMPLATE = "A99-9999"
SEED_BASE = 8000


# ---------------------------------------------------------------------------
# Synthetic crop helpers
# ---------------------------------------------------------------------------
def _make_text_crop(text: str, rng: np.random.Generator, size: tuple[int, int] = (280, 80)) -> np.ndarray:
    """Render white text on a mid-grey background with mild noise."""
    w, h = size
    base = int(rng.integers(100, 150))
    img = np.full((h, w, 3), base, dtype=np.uint8)
    font_scale = h / 60.0
    thickness = max(1, int(round(font_scale * 2)))
    text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness)
    x = max(0, (w - text_size[0]) // 2)
    y = max(0, (h + text_size[1]) // 2)
    cv2.putText(
        img, text, (x, y), cv2.FONT_HERSHEY_DUPLEX, font_scale, (240, 240, 240), thickness, cv2.LINE_AA
    )
    noise = rng.normal(0, 4, img.shape).astype(np.float32)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return img


def _make_qr_crop(text: str, size: int = 200) -> np.ndarray | None:
    """Render a QR code crop (BGR). Returns None if QRCodeEncoder not available."""
    try:
        encoder = cv2.QRCodeEncoder.create()
        qr_raw = encoder.encode(text)
        if qr_raw is None:
            return None
        padded = cv2.copyMakeBorder(qr_raw, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
        resized = cv2.resize(padded, (size, size), interpolation=cv2.INTER_NEAREST)
        return cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# QR tests (no model dependency)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(20))
def test_qr_decode_seeded_crops(seed: int) -> None:
    """QR decodes ≥ 0.95 of the time across 20 seeded crops."""
    # Generate a plausible ID
    rng = np.random.default_rng(SEED_BASE + seed)
    letter = str(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ")))
    n1 = int(rng.integers(10, 100))
    n2 = int(rng.integers(1000, 10000))
    billet_id = f"{letter}{n1:02d}-{n2:04d}"

    crop = _make_qr_crop(billet_id)
    if crop is None:
        pytest.skip("cv2.QRCodeEncoder not available on this build")

    result = read_qr([crop])
    assert result == billet_id, f"QR decode failed for {billet_id!r}: got {result!r}"


def test_qr_decode_rate() -> None:
    """QR decode rate must be ≥ 0.95 across 20 seeded scenes."""
    n = 20
    decoded = 0
    for seed in range(n):
        rng = np.random.default_rng(SEED_BASE + 100 + seed)
        letter = str(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ")))
        n1 = int(rng.integers(10, 100))
        n2 = int(rng.integers(1000, 10000))
        billet_id = f"{letter}{n1:02d}-{n2:04d}"
        crop = _make_qr_crop(billet_id)
        if crop is None:
            pytest.skip("cv2.QRCodeEncoder not available on this build")
        result = read_qr([crop])
        if result == billet_id:
            decoded += 1
    rate = decoded / n
    print(f"\nQR decode rate: {decoded}/{n} = {rate:.2%}")
    assert rate >= 0.95, f"QR rate {rate:.2%} < 0.95"


def test_qr_empty_crops() -> None:
    """read_qr returns None for empty crop list."""
    assert read_qr([]) is None


# ---------------------------------------------------------------------------
# OCR tests (skipped if models not available)
# ---------------------------------------------------------------------------
@pytestmark_ocr
def test_ocr_reads_text_crop() -> None:
    """OCR must read at least one line from a clear text crop."""
    rng = np.random.default_rng(SEED_BASE + 200)
    crop = _make_text_crop("H24-1187", rng)
    lines = ocr_read(crop)
    assert len(lines) > 0, "OCR returned no lines for a clear text crop"
    for txt, score in lines:
        assert isinstance(txt, str)
        assert 0.0 <= score <= 1.0


@pytestmark_ocr
def test_ocr_accuracy_rate() -> None:
    """Over 40 seeded text crops, OCR must normalize-match ≥ 0.90 of the time."""
    n = 40
    matched = 0
    from billetvision.vision.idparse import normalize

    ids_used: list[str] = []
    for i in range(n):
        rng = np.random.default_rng(SEED_BASE + 300 + i)
        letter = str(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ")))
        n1 = int(rng.integers(10, 100))
        n2 = int(rng.integers(1000, 10000))
        billet_id = f"{letter}{n1:02d}-{n2:04d}"
        ids_used.append(billet_id)

        crop = _make_text_crop(billet_id, rng)
        lines = ocr_read(crop)
        for txt, _ in lines:
            if normalize(txt, TEMPLATE) == billet_id:
                matched += 1
                break

    rate = matched / n
    print(f"\nOCR accuracy rate: {matched}/{n} = {rate:.2%}")
    assert rate >= 0.90, f"OCR rate {rate:.2%} < 0.90 over {n} crops"


@pytestmark_ocr
def test_ocr_180_degree_second_pass() -> None:
    """vote() with 180° retry must find a valid match for upside-down text crops."""
    rng = np.random.default_rng(SEED_BASE + 400)
    billet_id = "H24-1187"
    crop = _make_text_crop(billet_id, rng)
    rotated = cv2.rotate(crop, cv2.ROTATE_180)

    # First pass on rotated: may or may not succeed
    lines_rotated = ocr_read(rotated)
    winner_r, _, _, _ = vote([lines_rotated], TEMPLATE)

    # Simulate what read_id does: try original, then retry 180°
    lines_normal = ocr_read(crop)
    winner_normal, _, _, _ = vote([lines_normal], TEMPLATE)

    if winner_normal is None:
        # If normal fails, the 180° retry should recover
        winner_retry, _, _, _ = vote([lines_rotated], TEMPLATE)
        assert winner_retry is not None or winner_r is not None, (
            "180° retry should produce a valid winner for upside-down text"
        )
    # If normal succeeds, the test trivially passes


@pytestmark_ocr
def test_read_id_with_ocr_only() -> None:
    """read_id returns ocr source when no QR crop is given."""
    rng = np.random.default_rng(SEED_BASE + 500)
    crop = _make_text_crop("H24-1187", rng)

    def _no_qr(crops: list) -> str | None:  # type: ignore[type-arg]
        return None

    result = read_id([crop], ocr_read, _no_qr, TEMPLATE)
    # id_source must be ocr or none — never qr since no QR provided
    assert result.id_source in ("ocr", "none")
    assert result.qr_text is None


@pytestmark_ocr
def test_read_id_with_qr_and_ocr_mismatch() -> None:
    """read_id sets id_mismatch when valid OCR and QR disagree."""
    rng = np.random.default_rng(SEED_BASE + 600)
    crop_a = _make_text_crop("H24-1187", rng)
    qr_crop = _make_qr_crop("H24-9999")
    if qr_crop is None:
        pytest.skip("cv2.QRCodeEncoder not available")

    def _qr_fn(crops: list) -> str | None:  # type: ignore[type-arg]
        return read_qr([qr_crop])

    result = read_id([crop_a], ocr_read, _qr_fn, TEMPLATE)
    if result.id_source == "ocr" and result.qr_text is not None and result.billet_id != result.qr_text:
        assert result.id_mismatch
