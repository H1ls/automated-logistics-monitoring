from dataclasses import dataclass
from typing import Optional

"""
    История изменения о ТС
"""
@dataclass(slots=True)
class NavigationSnapshot:
    id: Optional[int] = None

    task_index: int = 0          # связь с Task (пока через index)
    vehicle_plate: str = ""
    # vehicle_id: Optional[int] = None
    vehicle_monitoring_id: Optional[int] = None

    collected_at: str = ""       # "26.04.2026 14:32"

    geo_text: str = ""           # "Москва, склад"
    coordinates: str = ""        # "55.123, 37.456"
    speed_kmh: int | float | None = None

    gps_fix_text: str = ""
    gps_fix_age_seconds: int | None = None

    has_fresh_coordinates: bool = False
    is_navigation_stale: bool = False    # старая навигация (>1 часа)