from __future__ import annotations

from enum import StrEnum


class InspectionStatus(StrEnum):
    Pass = "Pass"
    Rework = "Rework"
    Fail = "Fail"


class IdSource(StrEnum):
    ocr = "ocr"
    qr = "qr"
    none = "none"


class DefectType(StrEnum):
    notch = "notch"
    taper = "taper"
    bulge = "bulge"
    camber = "camber"


class SourceType(StrEnum):
    webcam = "webcam"
    url = "url"
    file = "file"
    synthetic = "synthetic"


class TriggerMode(StrEnum):
    auto = "auto"
    stable = "stable"
    line = "line"


class AlertLevel(StrEnum):
    Fail = "Fail"
    Rework = "Rework"
    System = "System"


class LogFileStatus(StrEnum):
    ok = "ok"
    locked = "locked"
    error = "error"


class StreamView(StrEnum):
    annotated = "annotated"
    rectified = "rectified"
    raw = "raw"
