from __future__ import annotations

import pytest

from billetvision.vision.idparse import normalize, resolve_id, vote

TEMPLATE = "A99-9999"


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        # Exact nominal
        ("H24-1187", "H24-1187"),
        # Missing hyphen / whitespace variations
        ("H24 1187", "H24-1187"),
        ("H241187", "H24-1187"),
        ("  H24   1187  ", "H24-1187"),
        ("h24-1187", "H24-1187"),
        ("h24 1187", "H24-1187"),
        # Punctuation / delimiter substitutions
        ("H24_1187", "H24-1187"),
        ("H24.1187", "H24-1187"),
        ("H24–1187", "H24-1187"),  # En-dash
        ("H24—1187", "H24-1187"),  # Em-dash
        ("H24~1187", "H24-1187"),
        ("H24/1187", "H24-1187"),
        ("H24:1187", "H24-1187"),
        # Letter/Digit confusion - A vs 4
        ("H2A-1I87", "H24-1187"),
        ("424-1187", "A24-1187"),
        # Letter/Digit confusion - O, D, Q vs 0
        ("H24-118O", "H24-1180"),
        ("H24-118D", "H24-1180"),
        ("H24-118Q", "H24-1180"),
        ("024-1187", "O24-1187"),
        # Letter/Digit confusion - I, L, | vs 1
        ("H24-II87", "H24-1187"),
        ("H24-LL87", "H24-1187"),
        ("H24-|187", "H24-1187"),
        ("124-1187", "I24-1187"),
        # Letter/Digit confusion - Z vs 2
        ("HZ4-1187", "H24-1187"),
        ("224-1187", "Z24-1187"),
        # Letter/Digit confusion - S vs 5
        ("H24-11S7", "H24-1157"),
        ("524-1187", "S24-1187"),
        # Letter/Digit confusion - G vs 6
        ("H24-11G7", "H24-1167"),
        ("624-1187", "G24-1187"),
        # Letter/Digit confusion - T vs 7
        ("H24-118T", "H24-1187"),
        ("724-1187", "T24-1187"),
        # Letter/Digit confusion - B vs 8
        ("H24-11B7", "H24-1187"),
        ("824-1187", "B24-1187"),
        # Combined multiple confusions
        ("BZA 1ISO", "B24-1150"),
        # Invalid cases -> None
        ("H24-118", None),  # Too short
        ("H24-11879", None),  # Too long
        ("H24-11#7", None),  # Invalid symbol in digit position
        ("#24-1187", None),  # Invalid symbol in letter position
        ("", None),  # Empty string
        ("UNKNOWN", None),  # Wrong format
    ],
)
def test_normalize_table_cases(raw_text: str, expected: str | None) -> None:
    result = normalize(raw_text, TEMPLATE)
    assert result == expected, f"normalize({raw_text!r}, {TEMPLATE!r}) = {result!r}, expected {expected!r}"


def test_vote_unanimous() -> None:
    crops = [
        [("H24-1187", 0.90)],
        [("H24 1187", 0.94)],
        [("H24-1187", 0.98)],
    ]
    winner, conf, agree, raw = vote(crops, TEMPLATE)
    assert winner == "H24-1187"
    assert conf is not None and abs(conf - (0.90 + 0.94 + 0.98) / 3.0) < 1e-4
    assert agree == 1.0
    assert raw == "H24-1187"


def test_vote_majority() -> None:
    crops = [
        [("H24-1187", 0.90)],
        [("H24-1188", 0.85)],
        [("H24-1187", 0.92)],
    ]
    winner, conf, agree, raw = vote(crops, TEMPLATE)
    assert winner == "H24-1187"
    assert conf is not None and abs(conf - (0.90 + 0.92) / 2.0) < 1e-4
    assert agree is not None and abs(agree - 2.0 / 3.0) < 1e-4
    assert raw == "H24-1187"


def test_vote_tie_break_by_score() -> None:
    crops = [
        [("H24-1187", 0.95)],
        [("H24-1188", 0.80)],
    ]
    winner, conf, agree, raw = vote(crops, TEMPLATE)
    assert winner == "H24-1187"
    assert conf == 0.95
    assert agree == 0.5


def test_vote_all_invalid_fallback_to_best_raw() -> None:
    crops = [
        [("SOME NOISE", 0.40)],
        [("GARBAGE TEXT", 0.75)],
    ]
    winner, conf, agree, raw = vote(crops, TEMPLATE)
    assert winner is None
    assert conf == 0.75
    assert agree is None
    assert raw == "GARBAGE TEXT"


def test_vote_empty_crops() -> None:
    winner, conf, agree, raw = vote([], TEMPLATE)
    assert winner is None
    assert conf is None
    assert agree is None
    assert raw is None


def test_vote_flat_list_input() -> None:
    flat = [("H24-1187", 0.91), ("H24 1187", 0.95)]
    winner, conf, agree, raw = vote(flat, TEMPLATE)
    assert winner == "H24-1187"
    assert agree == 1.0


def test_resolve_id_ocr_only() -> None:
    res = resolve_id(
        ocr_winner="H24-1187",
        ocr_confidence=0.92,
        ocr_agreement=1.0,
        ocr_raw="H24-1187",
        qr_text=None,
    )
    assert res.billet_id == "H24-1187"
    assert res.id_source == "ocr"
    assert not res.id_mismatch
    assert res.ocr_confidence == 0.92
    assert res.ocr_agreement == 1.0
    assert res.qr_text is None


def test_resolve_id_qr_only() -> None:
    res = resolve_id(
        ocr_winner=None,
        ocr_confidence=0.60,
        ocr_agreement=None,
        ocr_raw="GARBAGE",
        qr_text="H24-1187",
    )
    assert res.billet_id == "H24-1187"
    assert res.id_source == "qr"
    assert not res.id_mismatch
    assert res.qr_text == "H24-1187"
    assert res.ocr_text == "GARBAGE"


def test_resolve_id_ocr_and_qr_matching() -> None:
    res = resolve_id(
        ocr_winner="H24-1187",
        ocr_confidence=0.95,
        ocr_agreement=1.0,
        ocr_raw="H24-1187",
        qr_text="H24-1187",
    )
    assert res.billet_id == "H24-1187"
    assert res.id_source == "ocr"
    assert not res.id_mismatch


def test_resolve_id_mismatch_flag() -> None:
    res = resolve_id(
        ocr_winner="H24-1187",
        ocr_confidence=0.91,
        ocr_agreement=0.8,
        ocr_raw="H24-1187",
        qr_text="H24-9999",
    )
    assert res.billet_id == "H24-1187"
    assert res.id_source == "ocr"
    assert res.id_mismatch is True
    assert res.qr_text == "H24-9999"


def test_resolve_id_neither() -> None:
    res = resolve_id(
        ocr_winner=None,
        ocr_confidence=None,
        ocr_agreement=None,
        ocr_raw=None,
        qr_text=None,
    )
    assert res.billet_id is None
    assert res.id_source == "none"
    assert not res.id_mismatch
