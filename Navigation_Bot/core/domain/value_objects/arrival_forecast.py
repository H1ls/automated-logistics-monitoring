from dataclasses import dataclass


@dataclass(slots=True)
class ArrivalForecast:
    distance_km: float = 0.0
    duration_minutes: int = 0
    arrival_time: str = ""
    on_time: bool = False
    time_buffer_text: str = ""
    buffer_minutes: int = 0

    def is_empty(self) -> bool:
        return (self.distance_km == 0.0
                and self.duration_minutes == 0
                and self.arrival_time == ""
                and self.buffer_minutes == 0
                )
