from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NavigationReadResult:
    """
    Результат прямого чтения из NavigationBot/Wialon.
    Это не вся Task, а только результат одного чтения.
    """
    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None

    geo_text: str = ""
    geo_zona: str = ""
    coordinates: str | None = None
    speed_kmh: int | None = None

    has_fresh_coordinates: bool = False
    is_navigation_stale: bool = False