from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NavigationReadResult:
    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None

    geo_text: str = ""
    coordinates: str | None = None
    speed_kmh: int | None = None

    has_fresh_coordinates: bool = False
    is_navigation_stale: bool = False