from __future__ import annotations

import re
from typing import Any

COORDINATE_RE = re.compile(r"(?<!\d)"
                           r"(?P<lat>[+-]?(?:[1-8]?\d(?:[.,]\d+)?|90(?:[.,]0+)?))"
                           r"\s*[,;]\s*"
                           r"(?P<lon>[+-]?(?:(?:1[0-7]\d|[1-9]?\d)(?:[.,]\d+)?|180(?:[.,]0+)?))"
                           r"(?!\d)"
                           )


def parse_coordinate_pair(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if not text:
        return None, None

    match = COORDINATE_RE.search(text)
    if not match:
        return None, None

    try:
        latitude = float(match.group("lat").replace(",", "."))
        longitude = float(match.group("lon").replace(",", "."))
    except ValueError:
        return None, None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, None

    return latitude, longitude


def format_coordinate_pair(latitude: float | None, longitude: float | None) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"{latitude:.6f}, {longitude:.6f}".rstrip("0").rstrip(".")
