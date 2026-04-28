from dataclasses import dataclass


@dataclass(slots=True)
class NavigationState:
    geo_text: str = ""
    coordinates: str = ""
    speed_kmh: int | float | None = None
    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None
    has_fresh_coordinates: bool = False

    def clear_coordinates(self) -> None:
        self.coordinates = ""
        self.has_fresh_coordinates = False

    def mark_no_navigation(self) -> None:
        self.geo_text = "нет навигации"
        self.coordinates = ""
        self.speed_kmh = 0
        self.has_fresh_coordinates = False
