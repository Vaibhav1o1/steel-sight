from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

from billetvision.vision.types import IdResult

DIGIT_FIXES: dict[str, str] = {
    "O": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "L": "1",
    "|": "1",
    "Z": "2",
    "A": "4",
    "@": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
}

LETTER_FIXES: dict[str, str] = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "7": "T",
    "8": "B",
}

DELIM_MAP: dict[str, str] = {
    "_": "-",
    ".": "-",
    "—": "-",
    "–": "-",
    "~": "-",
    "/": "-",
    ":": "-",
}


def normalize(text: str, template: str) -> str | None:
    """Normalize and validate an OCR string against a template.

    Template characters:
      - 'A': letter (A-Z)
      - '9': digit (0-9)
      - anything else: literal character (e.g. '-')

    Steps per SPEC §12.1:
      1. Uppercase, remove spaces, map punctuation to '-' if template expects '-'.
      2. If len == len(template) - n_literals, insert literals at their positions.
      3. If len != len(template) -> None.
      4. Position-wise confusion fixes for digits and letters.
      5. Strict character validation for every position.
    """
    if not text or not template:
        return None

    cleaned = "".join(text.strip().upper().split())

    # Map delimiters to '-' if '-' is present in template
    if "-" in template:
        for delim, target in DELIM_MAP.items():
            cleaned = cleaned.replace(delim, target)

    literals = [(idx, char) for idx, char in enumerate(template) if char not in ("A", "9")]
    n_literals = len(literals)

    # Missing literals insertion (e.g. 'H241187' -> 'H24-1187')
    if len(cleaned) == len(template) - n_literals:
        chars = list(cleaned)
        for idx, lit_char in literals:
            if idx <= len(chars):
                chars.insert(idx, lit_char)
            else:
                return None
        cleaned = "".join(chars)

    if len(cleaned) != len(template):
        return None

    # Position-wise confusion fixes
    fixed_chars: list[str] = []
    for char, expected in zip(cleaned, template, strict=True):
        if expected == "9":
            # Digit position
            fixed = DIGIT_FIXES.get(char, char)
            if not fixed.isdigit():
                return None
            fixed_chars.append(fixed)
        elif expected == "A":
            # Letter position
            fixed = LETTER_FIXES.get(char, char)
            if not (fixed.isalpha() and fixed.isascii()):
                return None
            fixed_chars.append(fixed)
        else:
            # Literal position
            if char != expected:
                return None
            fixed_chars.append(char)

    return "".join(fixed_chars)


def vote(
    crop_candidates: Sequence[Sequence[tuple[str, float]]] | Sequence[tuple[str, float]],
    template: str,
) -> tuple[str | None, float | None, float | None, str | None]:
    """Vote across multi-crop OCR outputs per SPEC §12.3.

    Args:
        crop_candidates: List of crops, where each crop is a list of (line_text, score) tuples,
                         or a single flat list of (line_text, score) tuples.
        template: Spec ID template (e.g. 'A99-9999').

    Returns:
        tuple of (winner, ocr_confidence, ocr_agreement, ocr_text):
          - winner: Winning valid candidate string or None if none valid.
          - ocr_confidence: Mean score of winning lines (or best raw line score if no winner).
          - ocr_agreement: Fraction of crops with any text that contained the winner.
          - ocr_text: Winner string, or best raw uppercase text if no valid candidate.
    """
    if not crop_candidates:
        return None, None, None, None

    # Normalize structure to Sequence[Sequence[tuple[str, float]]]
    first_elem = crop_candidates[0]
    crops: list[list[tuple[str, float]]]
    if isinstance(first_elem, tuple) and len(first_elem) == 2 and isinstance(first_elem[0], str):
        crops = [list(crop_candidates)]  # type: ignore[list-item]
    else:
        crops = [list(c) for c in crop_candidates]  # type: ignore[union-attr]

    crops_with_any_text = 0
    all_raw_lines: list[tuple[str, float]] = []

    # Map candidate -> list of crop occurrences and scores
    candidate_crop_counts: dict[str, int] = {}
    candidate_scores: dict[str, list[float]] = {}

    for crop in crops:
        if not crop:
            continue
        crops_with_any_text += 1
        all_raw_lines.extend(crop)

        # Unique normalized candidates within this single crop
        crop_candidates_seen: set[str] = set()
        for text, score in crop:
            norm = normalize(text, template)
            if norm is not None:
                candidate_scores.setdefault(norm, []).append(float(score))
                crop_candidates_seen.add(norm)

        for norm in crop_candidates_seen:
            candidate_crop_counts[norm] = candidate_crop_counts.get(norm, 0) + 1

    if not candidate_crop_counts:
        # No valid candidate found
        best_raw: str | None = None
        best_score: float | None = None
        if all_raw_lines:
            raw_text, score = max(all_raw_lines, key=lambda x: x[1])
            best_raw = re.sub(r"\s+", " ", raw_text.strip().upper())
            best_score = float(score)
        return None, best_score, None, best_raw

    # Winner = most frequent valid candidate across crops; tie-break by higher mean score
    def sort_key(cand: str) -> tuple[int, float]:
        mean_score = float(np.mean(candidate_scores[cand]))
        return (candidate_crop_counts[cand], mean_score)

    winner = max(candidate_crop_counts.keys(), key=sort_key)
    confidence = float(np.mean(candidate_scores[winner]))
    agreement = float(candidate_crop_counts[winner] / max(crops_with_any_text, 1))

    return winner, confidence, agreement, winner


def resolve_id(
    ocr_winner: str | None,
    ocr_confidence: float | None = None,
    ocr_agreement: float | None = None,
    ocr_raw: str | None = None,
    qr_text: str | None = None,
) -> IdResult:
    """Resolve final billet ID and source per SPEC §12.5.

    Rules:
      - billet_id: valid OCR winner, else QR text, else None.
      - id_source: 'ocr' | 'qr' | 'none'.
      - id_mismatch: True when valid OCR and QR are both present and different.
    """
    clean_ocr = ocr_winner.strip() if ocr_winner and ocr_winner.strip() else None
    clean_qr = qr_text.strip() if qr_text and qr_text.strip() else None
    clean_raw = ocr_raw.strip() if ocr_raw and ocr_raw.strip() else None

    if clean_ocr is not None:
        billet_id = clean_ocr
        id_source = "ocr"
    elif clean_qr is not None:
        billet_id = clean_qr
        id_source = "qr"
    else:
        billet_id = None
        id_source = "none"

    id_mismatch = bool(clean_ocr is not None and clean_qr is not None and clean_ocr != clean_qr)

    return IdResult(
        billet_id=billet_id,
        id_source=id_source,
        ocr_text=clean_ocr or clean_raw,
        ocr_confidence=ocr_confidence,
        ocr_agreement=ocr_agreement,
        qr_text=clean_qr,
        id_mismatch=id_mismatch,
    )


def read_id(
    crops: list[NDArray[np.uint8]],
    ocr_fn: Callable[[NDArray[np.uint8]], list[tuple[str, float]]],
    qr_fn: Callable[[list[NDArray[np.uint8]]], str | None],
    template: str,
) -> IdResult:
    """Pure end-to-end ID reading per SPEC §12.3 and §12.5.

    1. Run OCR on each crop and collect (text, score) lines.
    2. Vote for the best valid candidate; if none, retry on 180°-rotated crops.
    3. Read QR from all crops.
    4. Resolve billet_id, id_source, id_mismatch.

    Args:
        crops: Upright BGR billet crop images.
        ocr_fn: Function that takes a single BGR crop and returns (text, score) list.
        qr_fn: Function that takes a list of BGR crops and returns the decoded QR string or None.
        template: ID template string (e.g. 'A99-9999').

    Returns:
        IdResult with all fields populated.
    """
    import cv2  # local import to keep module pure at top-level without cv2 dependency

    # Collect OCR results for each crop
    crop_lines: list[list[tuple[str, float]]] = [ocr_fn(c) for c in crops]

    # Vote — first pass
    winner, confidence, agreement, raw_text = vote(crop_lines, template)

    # Retry on 180°-rotated crops if no valid winner (SPEC §12.3)
    if winner is None and crops:
        rotated_lines: list[list[tuple[str, float]]] = [ocr_fn(cv2.rotate(c, cv2.ROTATE_180)) for c in crops]
        winner, confidence, agreement, raw_text = vote(rotated_lines, template)

    # QR decode
    qr_text = qr_fn(crops)

    return resolve_id(
        ocr_winner=winner,
        ocr_confidence=confidence,
        ocr_agreement=agreement,
        ocr_raw=raw_text,
        qr_text=qr_text,
    )
