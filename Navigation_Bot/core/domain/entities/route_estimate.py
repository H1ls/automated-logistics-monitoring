from dataclasses import dataclass
from typing import Optional

""" 
    ArrivalForecast — текущее состояние в Task
    RouteEstimate — история расчётов
"""


@dataclass(slots=True)
class RouteEstimate:
    id: Optional[int] = None

    trip_number: int = 0
    target_sequence: int = 0  # номер выгрузки

    calculated_at: str = ""

    distance_km: float = 0.0
    duration_minutes: int = 0

    arrival_time: str = ""
    on_time: bool = False

    buffer_minutes: int = 0
    time_buffer_text: str = ""
