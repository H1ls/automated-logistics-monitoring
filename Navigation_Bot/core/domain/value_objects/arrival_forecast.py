from dataclasses import dataclass


@dataclass(slots=True)
class ArrivalForecast:
    distance_km: float = 0.0
    duration_minutes: int = 0
    arrival_time: str = ""
    on_time: bool = False
    time_buffer_text: str = ""
    buffer_minutes: int = 0