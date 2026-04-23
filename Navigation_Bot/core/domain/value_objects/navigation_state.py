from dataclasses import dataclass


@dataclass(slots=True)
class NavigationState:
    geo_text: str = ""
    coordinates: str = ""
    speed_kmh: int | float | None = None
    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None
    has_fresh_coordinates: bool = False